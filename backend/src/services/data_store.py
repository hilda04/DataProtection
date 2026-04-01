from __future__ import annotations

import logging
import os
from datetime import datetime, timezone
from decimal import Decimal
from typing import Any, Dict, List, Optional
from uuid import uuid4

from botocore.exceptions import ClientError

from models.types import FrameworkSummary, OrganisationSummary, UserSummary
from services.assessment_engine import calculate_assessment_score, normalize_response_value
from services.framework_registry import (
    build_framework_seed_items,
    canonical_framework_id,
    load_framework_catalog,
    load_framework_definition,
)
from services.report_builder import (
    build_assessment_report,
    build_assessment_report_pdf,
    map_maturity_level,
)


class DataStoreError(RuntimeError):
    pass


class NotAuthenticatedError(DataStoreError):
    pass


class ConflictError(DataStoreError):
    pass


class ValidationError(DataStoreError):
    pass


class ReportUnavailableError(DataStoreError):
    pass


logger = logging.getLogger(__name__)


TABLE_PK_ATTRIBUTE = 'pk'
TABLE_SK_ATTRIBUTE = 'sk'

REQUIRED_ORGANISATION_FIELDS = (
    'name',
    'sector',
    'size',
    'country',
    'primaryContactName',
    'primaryContactEmail',
)

VALID_ASSESSMENT_STATUSES = {'NOT_STARTED', 'IN_PROGRESS', 'COMPLETED'}
REMEDIATION_PRIORITY_ORDER = {'HIGH': 0, 'MEDIUM': 1}

CREATE_ORGANISATION_CONDITION_EXPRESSION = (
    'attribute_not_exists(pk) AND attribute_not_exists(sk)'
)


class DataStore:
    def __init__(self, table: Optional[Any] = None, table_name: Optional[str] = None):
        resolved_table_name = table_name or os.environ.get('DYNAMODB_TABLE_NAME')
        if table is None and not resolved_table_name:
            raise DataStoreError('DYNAMODB_TABLE_NAME is not configured.')

        if table is not None:
            self.table = table
        else:
            import boto3

            self.table = boto3.resource('dynamodb').Table(resolved_table_name)

    def ensure_framework_seed_data(self) -> None:
        catalog_items = build_framework_seed_items()
        catalog_by_id = {item['frameworkId']: item for item in catalog_items}
        key = _dynamodb_key()
        result = self.table.query(
            KeyConditionExpression=key('pk').eq('FRAMEWORKS') & key('sk').begins_with('FRAMEWORK#')
        )
        existing_items = result.get('Items', [])
        existing_by_id = {
            str(item.get('frameworkId') or '').strip(): item for item in existing_items
        }

        with self.table.batch_writer() as batch:
            for framework_id, item in catalog_by_id.items():
                existing = existing_by_id.get(framework_id)
                if existing is None:
                    batch.put_item(
                        Item=self._to_dynamodb(
                            {
                                'pk': 'FRAMEWORKS',
                                'sk': f"FRAMEWORK#{item['frameworkId']}",
                                'entityType': item['entityType'],
                                'frameworkId': item['frameworkId'],
                                'name': item['name'],
                                'version': item['version'],
                                'description': item['description'],
                                'sections': item['sections'],
                            }
                        ),
                    )
                    continue

                if (
                    existing.get('name') != item.get('name')
                    or existing.get('version') != item.get('version')
                    or existing.get('description') != item.get('description')
                ):
                    batch.put_item(
                        Item=self._to_dynamodb(
                            {
                                **existing,
                                'pk': 'FRAMEWORKS',
                                'sk': f"FRAMEWORK#{item['frameworkId']}",
                                'entityType': item['entityType'],
                                'frameworkId': item['frameworkId'],
                                'name': item['name'],
                                'version': item['version'],
                                'description': item['description'],
                            }
                        ),
                    )

    def list_frameworks(self) -> List[FrameworkSummary]:
        self.ensure_framework_seed_data()
        key = _dynamodb_key()
        result = self.table.query(
            KeyConditionExpression=key('pk').eq('FRAMEWORKS') & key('sk').begins_with('FRAMEWORK#')
        )
        items = result.get('Items', [])
        if not items:
            return load_framework_catalog()

        framework_map: Dict[str, FrameworkSummary] = {
            framework['frameworkId']: framework for framework in load_framework_catalog()
        }
        for item in items:
            framework_id = str(item.get('frameworkId') or '').strip()
            if not framework_id:
                continue
            if framework_id in framework_map:
                continue
            framework_map[framework_id] = {
                'frameworkId': framework_id,
                'id': framework_id,
                'name': str(item.get('name') or '').strip(),
                'version': str(item.get('version') or '').strip(),
                'description': str(item.get('description') or '').strip(),
                'sections': item.get('sections') if isinstance(item.get('sections'), list) else [],
            }

        return list(framework_map.values())

    def get_bootstrap(self, user: UserSummary) -> Dict[str, Any]:
        return self.get_bootstrap_for_framework(user=user, framework_id=None)

    def get_bootstrap_for_framework(
        self, user: UserSummary, framework_id: Optional[str]
    ) -> Dict[str, Any]:
        membership = self._get_user_membership(user['sub'])
        organisation = None
        if membership:
            organisation = self._get_organisation(membership['organisationId'])

        bootstrap_payload: Dict[str, Any] = {
            'user': user,
            'hasOrganisation': organisation is not None,
            'organisation': organisation,
            'frameworks': self.list_frameworks(),
        }
        if framework_id:
            framework = self._get_framework(framework_id)
            if framework is None:
                raise ValidationError(f'Framework not found: {framework_id}.')
            bootstrap_payload['selectedFramework'] = {
                'frameworkId': framework['frameworkId'],
                'framework_id': framework['frameworkId'],
                'name': framework['name'],
                'description': framework.get('description', ''),
                'sections': self._load_assessment_sections(framework),
            }
        return bootstrap_payload

    def create_or_resume_assessment(
        self, user: UserSummary, framework_id: str
    ) -> tuple[Dict[str, Any], bool]:
        membership = self._require_membership(user['sub'])
        organisation_id = membership['organisationId']
        framework = self._get_framework(framework_id)
        if framework is None:
            raise ValidationError(f'Framework not found: {framework_id}.')
        resolved_framework_id = framework['frameworkId']

        assessments = self._list_assessment_items(organisation_id, resolved_framework_id)
        in_progress = next(
            (
                item
                for item in assessments
                if self._normalise_status(item.get('status')) == 'IN_PROGRESS'
            ),
            None,
        )
        if in_progress:
            return self._serialize_assessment_summary(in_progress), True

        now = datetime.now(timezone.utc).isoformat()
        assessment_id = f'asm_{uuid4().hex[:12]}'
        sections = self._load_assessment_sections(framework)
        current_section_id = ''
        if sections:
            first_section = sections[0]
            if not isinstance(first_section, dict):
                raise ValidationError('Framework metadata is malformed: section must be an object.')
            current_section_id = str(
                first_section.get('sectionId') or ''
            ).strip()
            if not current_section_id:
                raise ValidationError(
                    'Framework metadata is malformed: sectionId is missing for the first section.'
                )
        assessment_item = {
            'pk': f'ORG#{organisation_id}',
            'sk': f'ASSESSMENT#{assessment_id}',
            'entityType': 'ASSESSMENT',
            'assessmentId': assessment_id,
            'frameworkId': resolved_framework_id,
            'frameworkVersion': str(framework.get('version') or ''),
            'organisationId': organisation_id,
            'createdBy': user['sub'],
            'createdAt': now,
            'updatedAt': now,
            'status': 'NOT_STARTED',
            'score': 0.0,
            'completedAt': None,
            'reportS3Key': None,
            'currentSectionId': current_section_id,
            'previousAssessmentId': None,
            'sectionScores': [],
            # Developer note:
            # Assessments persist a snapshot of framework sections/questions at creation time.
            # Existing assessments retain their original snapshot even if framework files are
            # updated later; create a new assessment/restart to use the latest framework version.
            'assessmentSections': sections,
        }
        self.table.put_item(Item=self._to_dynamodb(assessment_item))
        return self._serialize_assessment_summary(assessment_item), False

    def list_assessments(
        self, user: UserSummary, framework_id: Optional[str] = None
    ) -> list[Dict[str, Any]]:
        membership = self._require_membership(user['sub'])
        items = self._list_assessment_items(membership['organisationId'], framework_id)
        return [self._serialize_assessment_summary(item) for item in items]

    def get_assessment_detail(self, user: UserSummary, assessment_id: str) -> Dict[str, Any]:
        membership = self._require_membership(user['sub'])
        organisation_id = membership['organisationId']
        assessment = self._get_assessment_item(organisation_id, assessment_id)
        if not assessment:
            raise ValidationError('Assessment not found.')

        framework = self._get_framework(assessment['frameworkId'])
        if framework is None:
            raise DataStoreError(f"Framework metadata missing for {assessment['frameworkId']}.")

        sections = self._resolve_assessment_sections(assessment, framework)
        current_section = self._resolve_current_section(
            sections, assessment.get('currentSectionId', '')
        )
        responses = self._get_assessment_responses(assessment_id)
        return {
            **self._serialize_assessment_summary(assessment),
            'sections': sections,
            'currentSection': current_section,
            'framework': {
                'frameworkId': framework['frameworkId'],
                'name': framework['name'],
                'version': framework['version'],
                'description': framework['description'],
                'sections': sections,
            },
            'responses': responses,
        }

    def save_assessment_responses(
        self,
        user: UserSummary,
        assessment_id: str,
        section_id: str,
        responses: list[Dict[str, Any]],
    ) -> Dict[str, Any]:
        membership = self._require_membership(user['sub'])
        organisation_id = membership['organisationId']
        assessment = self._get_assessment_item(organisation_id, assessment_id)
        if not assessment:
            raise ValidationError('Assessment not found.')
        framework = self._get_framework(assessment['frameworkId'])
        if framework is None:
            raise DataStoreError(f"Framework metadata missing for {assessment['frameworkId']}.")

        sections = self._resolve_assessment_sections(assessment, framework)
        section_ids = [section['sectionId'] for section in sections]
        if section_id not in section_ids:
            raise ValidationError('sectionId is invalid for this assessment framework.')

        now = datetime.now(timezone.utc).isoformat()
        response_item = {
            'pk': f'ASSESSMENT#{assessment_id}',
            'sk': f'RESPONSE#{section_id}',
            'entityType': 'ASSESSMENT_SECTION_RESPONSE',
            'assessmentId': assessment_id,
            'sectionId': section_id,
            'responses': responses,
            'updatedBy': user['sub'],
            'updatedAt': now,
        }
        self.table.put_item(Item=self._to_dynamodb(response_item))

        next_status = 'IN_PROGRESS'
        next_section_id = section_id
        if section_id in section_ids:
            section_index = section_ids.index(section_id)
            has_next = section_index + 1 < len(section_ids)
            next_section_id = section_ids[section_index + 1] if has_next else section_id
            if not has_next:
                next_status = 'COMPLETED'

        all_responses = self._get_assessment_responses(assessment_id)
        scoring = calculate_assessment_score(all_responses)
        logger.info(
            'Assessment scoring calculated.',
            extra={
                'assessmentId': assessment_id,
                'status': next_status,
                'responseCount': sum(len(items) for items in all_responses.values()),
                'calculatedScore': scoring['score'],
            },
        )
        update_expression = (
            'SET #status = :status, currentSectionId = :section, '
            'updatedAt = :updatedAt, score = :score, sectionScores = :sectionScores'
        )
        expression_values: dict[str, Any] = {
            ':status': next_status,
            ':section': next_section_id,
            ':updatedAt': now,
            ':score': scoring['score'],
            ':sectionScores': scoring['sectionScores'],
        }
        completed_at: Optional[str] = None
        report_s3_key: Optional[str] = None
        if next_status == 'COMPLETED':
            logger.info(
                'Assessment completion started.',
                extra={'assessmentId': assessment_id, 'organisationId': organisation_id},
            )
            completed_at = now
            try:
                logger.info(
                    'Assessment report generation started.',
                    extra={
                        'assessmentId': assessment_id,
                        'organisationId': organisation_id,
                    },
                )
                report = self._build_assessment_report(
                    assessment, sections, all_responses, scoring
                )
                report_s3_key = self._save_report_to_s3(assessment_id, report)
            except Exception:
                logger.exception(
                    'Assessment report generation or upload failed.',
                    extra={
                        'assessmentId': assessment_id,
                        'organisationId': organisation_id,
                    },
                )
                report_s3_key = None
            update_expression += ', completedAt = :completedAt, reportS3Key = :reportS3Key'
            expression_values[':completedAt'] = completed_at
            expression_values[':reportS3Key'] = report_s3_key

        self.table.update_item(
            Key={'pk': f'ORG#{organisation_id}', 'sk': f'ASSESSMENT#{assessment_id}'},
            UpdateExpression=update_expression,
            ExpressionAttributeNames={'#status': 'status'},
            ExpressionAttributeValues=self._to_dynamodb(expression_values),
        )
        refreshed = self._get_assessment_item(organisation_id, assessment_id)
        if not refreshed:
            raise DataStoreError('Assessment update failed.')
        return self._serialize_assessment_summary(refreshed)

    def restart_assessment(self, user: UserSummary, assessment_id: str) -> Dict[str, Any]:
        membership = self._require_membership(user['sub'])
        organisation_id = membership['organisationId']
        previous = self._get_assessment_item(organisation_id, assessment_id)
        if not previous:
            raise ValidationError('Assessment not found.')
        if self._normalise_status(previous.get('status')) != 'COMPLETED':
            raise ValidationError('Only completed assessments can be restarted.')

        framework_id = str(previous.get('frameworkId') or '').strip()
        framework = self._get_framework(framework_id)
        if framework is None:
            raise ValidationError(f'Framework not found: {framework_id}.')

        now = datetime.now(timezone.utc).isoformat()
        new_assessment_id = f'asm_{uuid4().hex[:12]}'
        sections = self._load_assessment_sections(framework)
        current_section_id = sections[0]['sectionId'] if sections else ''
        assessment_item = {
            'pk': f'ORG#{organisation_id}',
            'sk': f'ASSESSMENT#{new_assessment_id}',
            'entityType': 'ASSESSMENT',
            'assessmentId': new_assessment_id,
            'frameworkId': framework_id,
            'frameworkVersion': str(framework.get('version') or ''),
            'organisationId': organisation_id,
            'createdBy': user['sub'],
            'createdAt': now,
            'updatedAt': now,
            'status': 'NOT_STARTED',
            'score': 0.0,
            'completedAt': None,
            'reportS3Key': None,
            'currentSectionId': current_section_id,
            'previousAssessmentId': assessment_id,
            'sectionScores': [],
            'assessmentSections': sections,
        }
        self.table.put_item(Item=self._to_dynamodb(assessment_item))
        return self._serialize_assessment_summary(assessment_item)

    def create_organisation(
        self, user: UserSummary, payload: Dict[str, Any]
    ) -> OrganisationSummary:
        self._validate_payload(payload)

        existing_membership = self._get_user_membership(user['sub'])
        if existing_membership:
            raise ConflictError('You already belong to an organisation.')

        created_at = datetime.now(timezone.utc).isoformat()
        organisation_id = f'org_{uuid4().hex[:12]}'
        organisation: OrganisationSummary = {
            'organisationId': organisation_id,
            'name': str(payload['name']).strip(),
            'sector': str(payload['sector']).strip(),
            'size': str(payload['size']).strip(),
            'country': str(payload['country']).strip(),
            'primaryContactName': str(payload['primaryContactName']).strip(),
            'primaryContactEmail': str(payload['primaryContactEmail']).strip(),
            'createdBy': user['sub'],
            'createdAt': created_at,
        }

        organisation_item = {
            TABLE_PK_ATTRIBUTE: f"ORG#{organisation_id}",
            TABLE_SK_ATTRIBUTE: 'META',
            'entityType': 'ORGANISATION',
            **organisation,
        }
        membership_item = {
            TABLE_PK_ATTRIBUTE: f"USER#{user['sub']}",
            TABLE_SK_ATTRIBUTE: f"MEMBERSHIP#ORG#{organisation_id}",
            'entityType': 'USER_ORGANISATION_MEMBERSHIP',
            'organisationId': organisation_id,
            'userSub': user['sub'],
            'role': 'owner',
            'createdAt': created_at,
        }

        user_email = str(user.get('email', '')).strip()
        if user_email:
            membership_item['email'] = user_email

        client = self.table.meta.client
        table_name = self.table.name

        self._validate_transaction_item_keys(organisation_item, item_name='organisation')
        self._validate_transaction_item_keys(membership_item, item_name='membership')

        logger.info(
            'Preparing DynamoDB transaction for organisation creation.',
            extra={
                'route': 'POST /organisations',
                'table_name': table_name,
                'table_key_schema': [TABLE_PK_ATTRIBUTE, TABLE_SK_ATTRIBUTE],
                'organisation_item_keys': {
                    TABLE_PK_ATTRIBUTE: organisation_item[TABLE_PK_ATTRIBUTE],
                    TABLE_SK_ATTRIBUTE: organisation_item[TABLE_SK_ATTRIBUTE],
                },
                'membership_item_keys': {
                    TABLE_PK_ATTRIBUTE: membership_item[TABLE_PK_ATTRIBUTE],
                    TABLE_SK_ATTRIBUTE: membership_item[TABLE_SK_ATTRIBUTE],
                },
            },
        )

        transact_items = [
            {
                'Put': {
                    'TableName': table_name,
                    'Item': organisation_item,
                    'ConditionExpression': CREATE_ORGANISATION_CONDITION_EXPRESSION,
                }
            },
            {
                'Put': {
                    'TableName': table_name,
                    'Item': membership_item,
                    'ConditionExpression': CREATE_ORGANISATION_CONDITION_EXPRESSION,
                }
            },
        ]

        transact_items = self._to_dynamodb(transact_items)
        self._validate_transact_items(transact_items)

        try:
            client.transact_write_items(TransactItems=transact_items)
        except Exception as error:
            cancellation_reasons: Optional[List[Any]] = None
            try:
                cancellation_reasons = (
                    error.response.get('CancellationReasons')  # type: ignore[attr-defined]
                    if hasattr(error, 'response')
                    else None
                )
            except Exception:
                cancellation_reasons = None

            def _run_diagnostic_put_item(
                item_name: str, item: Dict[str, Any]
            ) -> Optional[Exception]:
                logger.error(
                    'Diagnostic put_item attempt for %s item.',
                    item_name,
                    extra={
                        'route': 'POST /organisations',
                        'table_name': table_name,
                        'diagnostic_item_name': item_name,
                        'diagnostic_item': item,
                    },
                )
                try:
                    self.table.put_item(
                        Item=self._to_dynamodb(item),
                        ConditionExpression=CREATE_ORGANISATION_CONDITION_EXPRESSION,
                    )
                except Exception as diagnostic_error:
                    diagnostic_response = (
                        diagnostic_error.response  # type: ignore[attr-defined]
                        if hasattr(diagnostic_error, 'response')
                        else None
                    )
                    logger.exception(
                        'Diagnostic put_item failed for %s item.',
                        item_name,
                        extra={
                            'route': 'POST /organisations',
                            'table_name': table_name,
                            'diagnostic_item_name': item_name,
                            'diagnostic_item': item,
                            'diagnostic_exception_message': str(diagnostic_error),
                            'diagnostic_error_response': diagnostic_response,
                        },
                    )
                    return diagnostic_error

                logger.error(
                    'Diagnostic put_item unexpectedly succeeded for %s item.',
                    item_name,
                    extra={
                        'route': 'POST /organisations',
                        'table_name': table_name,
                        'diagnostic_item_name': item_name,
                        'diagnostic_item': item,
                    },
                )
                return None

            organisation_diagnostic_error = _run_diagnostic_put_item(
                item_name='organisation', item=organisation_item
            )
            if organisation_diagnostic_error is None or (
                hasattr(organisation_diagnostic_error, 'response')
                and organisation_diagnostic_error.response.get('Error', {}).get('Code')
                == 'ConditionalCheckFailedException'
            ):
                _run_diagnostic_put_item(item_name='membership', item=membership_item)

            logger.exception(
                'DynamoDB transaction failed while creating organisation and membership records.',
                extra={
                    'route': 'POST /organisations',
                    'table_name': table_name,
                    'table_key_schema': [TABLE_PK_ATTRIBUTE, TABLE_SK_ATTRIBUTE],
                    'organisation_item_keys': {
                        TABLE_PK_ATTRIBUTE: organisation_item[TABLE_PK_ATTRIBUTE],
                        TABLE_SK_ATTRIBUTE: organisation_item[TABLE_SK_ATTRIBUTE],
                    },
                    'membership_item_keys': {
                        TABLE_PK_ATTRIBUTE: membership_item[TABLE_PK_ATTRIBUTE],
                        TABLE_SK_ATTRIBUTE: membership_item[TABLE_SK_ATTRIBUTE],
                    },
                    'cancellation_reasons': cancellation_reasons,
                    'exception_message': str(error),
                },
            )
            raise DataStoreError('Failed to create organisation record.') from error
        return organisation

    def _get_user_membership(self, user_sub: str) -> Optional[Dict[str, Any]]:
        key = _dynamodb_key()
        result = self.table.query(
            KeyConditionExpression=(
                key('pk').eq(f'USER#{user_sub}')
                & key('sk').begins_with('MEMBERSHIP#ORG#')
            ),
            Limit=1,
        )
        items = result.get('Items', [])
        return items[0] if items else None

    def _get_organisation(self, organisation_id: str) -> Optional[OrganisationSummary]:
        result = self.table.get_item(Key={'pk': f'ORG#{organisation_id}', 'sk': 'META'})
        item = result.get('Item')
        if not item:
            return None
        return {
            'organisationId': item['organisationId'],
            'name': item['name'],
            'sector': item['sector'],
            'size': item['size'],
            'country': item['country'],
            'primaryContactName': item['primaryContactName'],
            'primaryContactEmail': item['primaryContactEmail'],
            'createdBy': item['createdBy'],
            'createdAt': item['createdAt'],
        }

    def _validate_payload(self, payload: Dict[str, Any]) -> None:
        for field_name in REQUIRED_ORGANISATION_FIELDS:
            value = payload.get(field_name)
            if not isinstance(value, str) or not value.strip():
                raise ValidationError(f'{field_name} is required.')

    def _require_membership(self, user_sub: str) -> Dict[str, Any]:
        membership = self._get_user_membership(user_sub)
        if not membership:
            raise ValidationError('You must create an organisation before starting an assessment.')
        return membership

    def _get_framework(self, framework_id: str) -> Optional[Dict[str, Any]]:
        resolved_framework_id = canonical_framework_id(framework_id)
        self.ensure_framework_seed_data()
        result = self.table.get_item(
            Key={'pk': 'FRAMEWORKS', 'sk': f'FRAMEWORK#{resolved_framework_id}'}
        )
        item = result.get('Item')
        framework = load_framework_definition(resolved_framework_id)
        logger.info(
            'Resolving framework metadata.',
            extra={
                'requestedFrameworkId': framework_id,
                'resolvedFrameworkId': resolved_framework_id,
                'seedItemFound': bool(item),
            },
        )
        local_sections = self._load_assessment_sections(framework)
        if (
            item
            and self._framework_contains_questions(item)
            and not self._assessment_sections_are_stale(
                self._normalise_framework_sections(item.get('sections', [])),
                local_sections,
            )
        ):
            return item

        if (
            canonical_framework_id(str(framework.get('frameworkId') or ''))
            == resolved_framework_id
        ):
            if item:
                self._refresh_framework_sections(item, framework)
            return framework

        if item:
            return item
        return None

    def _framework_contains_questions(self, framework: Dict[str, Any]) -> bool:
        sections = framework.get('sections', [])
        if not isinstance(sections, list):
            return False

        for section in sections:
            if not isinstance(section, dict):
                continue
            questions = section.get('questions') or section.get('controls') or []
            if not isinstance(questions, list):
                continue
            for question in questions:
                if not isinstance(question, dict):
                    continue
                question_id = str(
                    question.get('questionId')
                    or question.get('id')
                    or question.get('controlId')
                    or ''
                ).strip()
                if question_id:
                    return True
        return False

    def _sections_have_questions(self, sections: list[Dict[str, Any]]) -> bool:
        return any(section.get('questions') for section in sections if isinstance(section, dict))

    def _load_assessment_sections(self, framework: Dict[str, Any]) -> list[Dict[str, Any]]:
        sections = self._normalise_framework_sections(framework.get('sections', []))
        logger.info(
            'Loaded framework sections for assessment snapshot.',
            extra={
                'frameworkId': framework.get('frameworkId'),
                'frameworkVersion': framework.get('version'),
                'sectionCount': len(sections),
                'questionCountBySection': {
                    section.get('sectionId'): len(section.get('questions', []))
                    for section in sections
                },
            },
        )
        if not self._sections_have_questions(sections):
            logger.warning(
                'Assessment framework sections do not include questions.',
                extra={'frameworkId': framework.get('frameworkId')},
            )
        return sections

    def _resolve_assessment_sections(
        self, assessment: Dict[str, Any], framework: Dict[str, Any]
    ) -> list[Dict[str, Any]]:
        snapshot_sections = self._normalise_framework_sections(
            assessment.get('assessmentSections') or []
        )
        current_sections = self._load_assessment_sections(framework)
        if self._sections_have_questions(
            snapshot_sections
        ) and not self._assessment_sections_are_stale(
            snapshot_sections,
            current_sections,
        ):
            return snapshot_sections
        logger.info(
            'Assessment section snapshot is stale; using latest framework definition.',
            extra={
                'assessmentId': assessment.get('assessmentId'),
                'frameworkId': framework.get('frameworkId'),
                'frameworkVersion': framework.get('version'),
            },
        )
        return current_sections

    def _assessment_sections_are_stale(
        self, snapshot_sections: list[Dict[str, Any]], framework_sections: list[Dict[str, Any]]
    ) -> bool:
        # Developer note:
        # Framework freshness is enforced here by comparing each stored snapshot section/question
        # against the latest framework definition. If stale, callers must reload from framework.
        framework_section_lookup = {
            str(section.get('sectionId')): section for section in framework_sections
        }
        for snapshot_section in snapshot_sections:
            snapshot_section_id = str(snapshot_section.get('sectionId') or '').strip()
            if not snapshot_section_id:
                return True
            framework_section = framework_section_lookup.get(snapshot_section_id)
            if framework_section is None:
                return True
            if self._section_snapshot_is_stale(snapshot_section, framework_section):
                return True
        return False

    def _section_snapshot_is_stale(
        self, snapshot_section: Dict[str, Any], framework_section: Dict[str, Any]
    ) -> bool:
        snapshot_questions = snapshot_section.get('questions', [])
        framework_questions = framework_section.get('questions', [])
        if len(snapshot_questions) < len(framework_questions):
            return True
        return any(
            self._question_snapshot_is_stale(question) for question in snapshot_questions
        )

    def _question_snapshot_is_stale(self, question: Dict[str, Any]) -> bool:
        # Developer note:
        # Question snapshots are stale if guidance/compliance metadata used by report rendering
        # is incomplete (missing title/actions/evidence/compliance_relevance).
        guidance = question.get('guidance')
        if not isinstance(guidance, dict):
            return True
        if not str(question.get('compliance_relevance') or '').strip():
            return True
        actions = guidance.get('actions')
        evidence = guidance.get('evidence')
        return not (
            str(guidance.get('title') or '').strip()
            and isinstance(actions, list)
            and len([item for item in actions if str(item).strip()]) > 0
            and isinstance(evidence, list)
            and len([item for item in evidence if str(item).strip()]) > 0
        )

    def _refresh_framework_sections(
        self, existing_framework: Dict[str, Any], framework_definition: Dict[str, Any]
    ) -> None:
        try:
            self.table.update_item(
                Key={
                    'pk': 'FRAMEWORKS',
                    'sk': f"FRAMEWORK#{existing_framework['frameworkId']}",
                },
                UpdateExpression='SET #sections = :sections, updatedAt = :updatedAt',
                ExpressionAttributeNames={'#sections': 'sections'},
                ExpressionAttributeValues=self._to_dynamodb(
                    {
                        ':sections': framework_definition.get('sections', []),
                        ':updatedAt': datetime.now(timezone.utc).isoformat(),
                    }
                ),
            )
        except Exception:
            logger.warning(
                'Failed to refresh framework sections from local framework definition.',
                extra={'frameworkId': existing_framework.get('frameworkId')},
            )

    def _list_assessment_items(
        self, organisation_id: str, framework_id: Optional[str] = None
    ) -> list[Dict[str, Any]]:
        key = _dynamodb_key()
        result = self.table.query(
            KeyConditionExpression=(
                key('pk').eq(f'ORG#{organisation_id}') & key('sk').begins_with('ASSESSMENT#')
            )
        )
        items = result.get('Items', [])
        filtered_items = [
            item
            for item in items
            if item.get('entityType') == 'ASSESSMENT'
            and self._normalise_status(item.get('status')) in VALID_ASSESSMENT_STATUSES
            and (
                framework_id is None
                or canonical_framework_id(str(item.get('frameworkId') or ''))
                == canonical_framework_id(framework_id)
            )
        ]
        return sorted(filtered_items, key=lambda item: item.get('updatedAt', ''), reverse=True)

    def _get_assessment_item(
        self, organisation_id: str, assessment_id: str
    ) -> Optional[Dict[str, Any]]:
        result = self.table.get_item(
            Key={'pk': f'ORG#{organisation_id}', 'sk': f'ASSESSMENT#{assessment_id}'}
        )
        item = result.get('Item')
        if not item or item.get('entityType') != 'ASSESSMENT':
            return None
        return item

    def _get_assessment_responses(self, assessment_id: str) -> Dict[str, list[Dict[str, Any]]]:
        key = _dynamodb_key()
        result = self.table.query(
            KeyConditionExpression=(
                key('pk').eq(f'ASSESSMENT#{assessment_id}') & key('sk').begins_with('RESPONSE#')
            )
        )
        mapped: Dict[str, list[Dict[str, Any]]] = {}
        for item in result.get('Items', []):
            section_id = item.get('sectionId')
            if section_id:
                mapped[str(section_id)] = item.get('responses', [])
        return mapped

    def _serialize_assessment_summary(self, item: Dict[str, Any]) -> Dict[str, Any]:
        status = self._normalise_status(item.get('status'))
        report_s3_key = item.get('reportS3Key')
        report_url = self._get_presigned_report_url(report_s3_key)
        return {
            'assessmentId': item['assessmentId'],
            'assessment_id': item['assessmentId'],
            'frameworkId': item['frameworkId'],
            'framework_id': item['frameworkId'],
            'frameworkVersion': str(item.get('frameworkVersion') or ''),
            'framework_version': str(item.get('frameworkVersion') or ''),
            'organisationId': item['organisationId'],
            'createdBy': item['createdBy'],
            'createdAt': item['createdAt'],
            'updatedAt': item['updatedAt'],
            'status': status,
            'score': float(item.get('score', 0.0)),
            'completedAt': item.get('completedAt'),
            'completed_at': item.get('completedAt'),
            'reportS3Key': report_s3_key,
            'report_s3_key': report_s3_key,
            'reportUrl': report_url,
            'report_url': report_url,
            'currentSectionId': item.get('currentSectionId', ''),
            'previousAssessmentId': item.get('previousAssessmentId'),
            'sectionScores': item.get('sectionScores', []),
            'maturityLevel': map_maturity_level(float(item.get('score', 0.0))),
        }

    def get_assessment_report_download_url(
        self, user: UserSummary, assessment_id: str
    ) -> Dict[str, str]:
        membership = self._require_membership(user['sub'])
        assessment = self._get_assessment_item(membership['organisationId'], assessment_id)
        if not assessment:
            raise ValidationError('Assessment not found.')
        report_s3_key = str(assessment.get('reportS3Key') or '').strip()
        if not report_s3_key:
            report_s3_key = self._generate_report_for_completed_assessment(assessment)
        if not report_s3_key:
            raise ReportUnavailableError('Report is not available for this assessment.')

        bucket_name = self._get_reports_bucket_name(required=False)
        if not bucket_name:
            raise ReportUnavailableError('Report storage is not configured.')

        import boto3

        s3_client = boto3.client('s3')
        try:
            s3_client.head_object(Bucket=bucket_name, Key=report_s3_key)
        except ClientError as error:
            error_code = str(error.response.get('Error', {}).get('Code', '')).strip()
            if error_code in {'404', 'NoSuchKey', 'NotFound'}:
                logger.warning(
                    'Assessment report object not found in S3.',
                    extra={
                        'assessmentId': assessment_id,
                        'reportS3Key': report_s3_key,
                        'reportsBucketName': bucket_name,
                    },
                )
                raise ReportUnavailableError(
                    'Report is not available for this assessment.'
                ) from error
            raise

        signed_url = s3_client.generate_presigned_url(
            'get_object',
            Params={'Bucket': bucket_name, 'Key': report_s3_key},
            ExpiresIn=3600,
        )
        return {
            'url': signed_url,
            'reportUrl': signed_url,
            'signedUrl': signed_url,
        }

    def _generate_report_for_completed_assessment(
        self, assessment: Dict[str, Any]
    ) -> Optional[str]:
        assessment_id = str(assessment.get('assessmentId') or '').strip()
        organisation_id = str(assessment.get('organisationId') or '').strip()
        if not assessment_id or not organisation_id:
            return None
        if self._normalise_status(assessment.get('status')) != 'COMPLETED':
            return None

        logger.info(
            'Attempting on-demand report generation for completed assessment.',
            extra={'assessmentId': assessment_id, 'organisationId': organisation_id},
        )

        try:
            framework = self._get_framework(str(assessment.get('frameworkId') or '').strip())
            if framework is None:
                return None
            sections = self._resolve_assessment_sections(assessment, framework)
            all_responses = self._get_assessment_responses(assessment_id)
            scoring = calculate_assessment_score(all_responses)
            report = self._build_assessment_report(assessment, sections, all_responses, scoring)
            report_s3_key = self._save_report_to_s3(assessment_id, report)
            if not report_s3_key:
                return None

            now = datetime.now(timezone.utc).isoformat()
            self.table.update_item(
                Key={'pk': f'ORG#{organisation_id}', 'sk': f'ASSESSMENT#{assessment_id}'},
                UpdateExpression=(
                    'SET reportS3Key = :reportS3Key, score = :score, '
                    'sectionScores = :sectionScores, updatedAt = :updatedAt'
                ),
                ExpressionAttributeValues=self._to_dynamodb(
                    {
                        ':reportS3Key': report_s3_key,
                        ':score': scoring['score'],
                        ':sectionScores': scoring['sectionScores'],
                        ':updatedAt': now,
                    }
                ),
            )
            return report_s3_key
        except Exception:
            logger.exception(
                'On-demand report generation failed.',
                extra={'assessmentId': assessment_id, 'organisationId': organisation_id},
            )
            return None

    def _build_assessment_report(
        self,
        assessment: Dict[str, Any],
        sections: list[Dict[str, Any]],
        all_responses: Dict[str, list[Dict[str, Any]]],
        scoring: Dict[str, Any],
    ) -> Dict[str, Any]:
        organisation = self._get_organisation(assessment['organisationId'])
        if organisation is None:
            raise DataStoreError('Organisation not found for report generation.')

        framework = self._get_framework(assessment['frameworkId'])
        if framework is None:
            raise DataStoreError('Framework not found for report generation.')

        enriched_sections = self._enrich_sections_for_reporting(
            sections=sections,
            framework_sections=self._load_assessment_sections(framework),
        )
        question_index = self._build_question_index(enriched_sections)
        risks: list[Dict[str, Any]] = []
        recommended_actions: list[Dict[str, Any]] = []
        for section_id, responses in all_responses.items():
            for response in responses:
                response_score = normalize_response_value(response.get('value'))
                if response_score >= 1.0:
                    continue
                question = question_index.get(str(response.get('questionId')), {})
                risk_level = 'HIGH' if response_score == 0 else 'MEDIUM'
                risk_item = {
                    'section_id': section_id,
                    'question_id': response.get('questionId'),
                    'question': question.get('text', 'Unknown question'),
                    'risk_level': risk_level,
                }
                risks.append(risk_item)
                guidance = self._normalise_question_guidance(question)
                primary_action = guidance['actions'][0]
                recommended_actions.append(
                    {
                        'section_id': section_id,
                        'question_id': response.get('questionId'),
                        'severity': 'no' if response_score == 0 else 'partial',
                        'priority': risk_level,
                        'title': guidance['title'],
                        'issue': guidance['title'],
                        'risk': guidance['risk'],
                        'actions': guidance['actions'],
                        'action': primary_action,
                        'evidence': guidance['evidence'],
                        'compliance_relevance': str(
                            question.get('compliance_relevance') or ''
                        ).strip(),
                    }
                )

        recommended_actions.sort(
            key=lambda item: REMEDIATION_PRIORITY_ORDER.get(
                str(item.get('priority', 'MEDIUM')).upper(), 99
            )
        )

        section_name_lookup = {
            section['sectionId']: section.get('name', section['sectionId'])
            for section in enriched_sections
        }
        section_summaries = [
            {
                'name': section_name_lookup.get(item['sectionId'], item['sectionId']),
                'score': item['score'],
            }
            for item in scoring['sectionScores']
        ]

        return build_assessment_report(
            organisation=organisation,
            framework={
                'framework_id': framework['frameworkId'],
                'name': framework['name'],
                'version': framework['version'],
            },
            score=scoring['score'],
            sections=section_summaries,
            risks=risks,
            recommendations=recommended_actions,
        )

    def _enrich_sections_for_reporting(
        self, sections: list[Dict[str, Any]], framework_sections: list[Dict[str, Any]]
    ) -> list[Dict[str, Any]]:
        # Developer note:
        # Report-time enrichment safely merges latest non-answer metadata into old snapshots
        # without changing responses, scoring, or assessment status.
        framework_question_index = self._build_question_index(framework_sections)
        enriched_sections: list[Dict[str, Any]] = []
        for section in sections:
            section_questions = []
            for question in section.get('questions', []):
                question_id = str(question.get('questionId') or '').strip()
                if not question_id:
                    continue
                latest_question = framework_question_index.get(question_id, {})
                section_questions.append(self._merge_question_metadata(question, latest_question))
            enriched_sections.append({**section, 'questions': section_questions})
        return enriched_sections

    def _merge_question_metadata(
        self, snapshot_question: Dict[str, Any], latest_question: Dict[str, Any]
    ) -> Dict[str, Any]:
        merged_question = dict(snapshot_question)
        for field in ('guidance', 'compliance_relevance', 'helpText'):
            current_value = merged_question.get(field)
            if field == 'guidance':
                if isinstance(current_value, dict) and not self._question_snapshot_is_stale(
                    {
                        'guidance': current_value,
                        'compliance_relevance': merged_question.get(
                            'compliance_relevance'
                        ),
                    }
                ):
                    continue
                latest_value = latest_question.get(field)
                if isinstance(latest_value, dict):
                    merged_question[field] = latest_value
                continue

            if str(current_value or '').strip():
                continue
            latest_value = latest_question.get(field)
            if isinstance(latest_value, str) and latest_value.strip():
                merged_question[field] = latest_value.strip()
        return merged_question

    def _build_question_index(self, sections: list[Dict[str, Any]]) -> dict[str, Dict[str, Any]]:
        question_index: dict[str, Dict[str, Any]] = {}
        for section in sections:
            for question in section.get('questions', []):
                question_id = str(question.get('questionId', '')).strip()
                if question_id:
                    question_index[question_id] = question
        return question_index

    def _normalise_question_guidance(self, question: Dict[str, Any]) -> Dict[str, Any]:
        question_title = str(question.get('text') or 'Control gap identified').strip()
        recommendation = str(question.get('recommendation') or '').strip()
        compliance_relevance = str(question.get('compliance_relevance') or '').strip()
        evidence_required = question.get('evidence_required')
        normalised_evidence_required = (
            [str(item).strip() for item in evidence_required if str(item).strip()]
            if isinstance(evidence_required, list)
            else []
        )

        if recommendation and normalised_evidence_required:
            logger.debug(
                'Using question metadata for report recommendation.',
                extra={
                    'questionId': question.get('questionId'),
                    'hasComplianceRelevance': bool(compliance_relevance),
                },
            )
            return {
                'title': question_title,
                'risk': compliance_relevance or question_title,
                'actions': [recommendation],
                'evidence': normalised_evidence_required,
            }

        guidance = question.get('guidance')
        guidance_obj = guidance if isinstance(guidance, dict) else {}

        actions = guidance_obj.get('actions')
        if isinstance(actions, list):
            normalised_actions = [str(action).strip() for action in actions if str(action).strip()]
        else:
            action_value = str(guidance_obj.get('action') or '').strip()
            normalised_actions = [action_value] if action_value else []

        evidence = guidance_obj.get('evidence')
        if isinstance(evidence, list):
            normalised_evidence = [
                str(item).strip() for item in evidence if str(item).strip()
            ]
        else:
            normalised_evidence = []

        title = str(guidance_obj.get('title') or '').strip() or 'Control improvement required'
        risk = str(guidance_obj.get('risk') or '').strip() or 'Control gap requires review.'
        actions = normalised_actions or ['Review this control and define a remediation plan.']
        evidence = normalised_evidence or [
            'Documented remediation plan and implementation evidence.'
        ]
        logger.debug(
            'Falling back to legacy guidance for report recommendation.',
            extra={'questionId': question.get('questionId')},
        )

        return {'title': title, 'risk': risk, 'actions': actions, 'evidence': evidence}

    def _save_report_to_s3(self, assessment_id: str, report: Dict[str, Any]) -> Optional[str]:
        bucket_name = self._get_reports_bucket_name(required=False)
        if not bucket_name:
            logger.warning(
                'Skipping report upload because REPORTS_BUCKET_NAME is not configured.',
                extra={'assessmentId': assessment_id},
            )
            return None

        logger.info(
            'Uploading assessment report to S3.',
            extra={'assessmentId': assessment_id, 'reportsBucketName': bucket_name},
        )

        report_key = f'reports/{assessment_id}.pdf'
        import boto3

        try:
            pdf_bytes = build_assessment_report_pdf(report)
        except ModuleNotFoundError as error:
            if error.name == 'reportlab':
                logger.exception(
                    (
                        'PDF generation dependency missing: '
                        'reportlab is not packaged in this Lambda artifact.'
                    ),
                    extra={
                        'assessmentId': assessment_id,
                        'reportsBucketName': bucket_name,
                        'missingDependency': error.name,
                    },
                )
            raise
        if not isinstance(pdf_bytes, (bytes, bytearray)):
            raise TypeError('PDF builder must return bytes.')
        if len(pdf_bytes) < 256:
            raise ValueError('Generated report PDF is unexpectedly small.')
        if not bytes(pdf_bytes).startswith(b'%PDF'):
            raise ValueError('Generated report is not a valid PDF.')
        s3_client = boto3.client('s3')
        s3_client.put_object(
            Bucket=bucket_name,
            Key=report_key,
            Body=pdf_bytes,
            ContentType='application/pdf',
            ContentDisposition=f'inline; filename="assessment-report-{assessment_id}.pdf"',
        )
        logger.info(
            'Assessment report upload succeeded.',
            extra={
                'assessmentId': assessment_id,
                'reportS3Key': report_key,
                'reportsBucketName': bucket_name,
            },
        )
        return report_key

    def _get_reports_bucket_name(self, *, required: bool) -> Optional[str]:
        bucket_name = os.environ.get('REPORTS_BUCKET_NAME', '').strip()
        if bucket_name:
            logger.info('Using reports S3 bucket.', extra={'reportsBucketName': bucket_name})
            return bucket_name

        if required:
            raise DataStoreError('REPORTS_BUCKET_NAME is not configured.')

        logger.warning('REPORTS_BUCKET_NAME is not configured; report storage is disabled.')
        return None

    def _get_presigned_report_url(self, report_s3_key: Any) -> Optional[str]:
        key = str(report_s3_key or '').strip()
        if not key:
            return None

        bucket_name = self._get_reports_bucket_name(required=False)
        if not bucket_name:
            return None

        try:
            import boto3

            s3_client = boto3.client('s3')
            return str(
                s3_client.generate_presigned_url(
                    'get_object',
                    Params={'Bucket': bucket_name, 'Key': key},
                    ExpiresIn=3600,
                )
            )
        except Exception:
            logger.exception('Failed to generate presigned report URL.', extra={'reportS3Key': key})
            return None

    def _normalise_status(self, value: Any) -> str:
        normalized = str(value or '').strip().upper()
        if normalized in {'NOT_STARTED', 'NOT STARTED'}:
            return 'NOT_STARTED'
        if normalized in {'IN_PROGRESS', 'IN PROGRESS'}:
            return 'IN_PROGRESS'
        if normalized == 'COMPLETED':
            return 'COMPLETED'
        return 'NOT_STARTED'

    def _normalise_framework_sections(self, sections: list[Dict[str, Any]]) -> list[Dict[str, Any]]:
        normalised_sections: list[Dict[str, Any]] = []
        for section in sections:
            if not isinstance(section, dict):
                continue
            section_id = str(section.get('sectionId') or section.get('id') or '').strip()
            if not section_id:
                continue
            questions = []
            for question in section.get('questions') or section.get('controls') or []:
                if not isinstance(question, dict):
                    continue
                question_id = str(
                    question.get('questionId')
                    or question.get('id')
                    or question.get('controlId')
                    or ''
                ).strip()
                if not question_id:
                    continue
                questions.append(
                    {
                        'questionId': question_id,
                        'text': str(
                            question.get('text')
                            or question.get('prompt')
                            or question.get('question')
                            or question.get('title')
                            or ''
                        ).strip(),
                        'helpText': str(question.get('helpText', '')).strip(),
                        'weight': int(question.get('weight', 1)),
                        'expectedAnswer': str(
                            question.get('expectedAnswer')
                            or question.get('expected_answer')
                            or 'yes'
                        ).strip()
                        or 'yes',
                        'recommendation': str(question.get('recommendation') or '').strip(),
                        'evidence_required': [
                            str(item).strip()
                            for item in (question.get('evidence_required') or [])
                            if str(item).strip()
                        ],
                        'compliance_relevance': str(
                            question.get('compliance_relevance') or ''
                        ).strip(),
                        'guidance': question.get('guidance')
                        if isinstance(question.get('guidance'), dict)
                        else {},
                    }
                )
            normalised_sections.append(
                {
                    'sectionId': section_id,
                    'name': str(section.get('name') or section.get('title') or '').strip(),
                    'description': str(
                        section.get('description') or section.get('summary') or ''
                    ).strip(),
                    'questions': questions,
                }
            )
        return normalised_sections

    def _resolve_current_section(
        self, sections: list[Dict[str, Any]], current_section_id: str
    ) -> Optional[Dict[str, Any]]:
        if not sections:
            return None
        selected = next(
            (section for section in sections if section.get('sectionId') == current_section_id),
            None,
        )
        return selected or sections[0]

    def _validate_transaction_item_keys(self, item: Dict[str, Any], item_name: str) -> None:
        missing_attributes = [
            attribute
            for attribute in (TABLE_PK_ATTRIBUTE, TABLE_SK_ATTRIBUTE)
            if attribute not in item
        ]
        if missing_attributes:
            raise DataStoreError(
                f"{item_name} transaction item is missing key attributes: {missing_attributes}."
            )

        for attribute in (TABLE_PK_ATTRIBUTE, TABLE_SK_ATTRIBUTE):
            value = item.get(attribute)
            if value is None:
                raise DataStoreError(
                    f'{item_name} transaction item has null key attribute: {attribute}.'
                )
            if isinstance(value, str) and not value.strip():
                raise DataStoreError(
                    f'{item_name} transaction item has empty key attribute: {attribute}.'
                )

    def _validate_transact_items(self, transact_items: List[Dict[str, Any]]) -> None:
        for index, transaction in enumerate(transact_items):
            put_item = transaction.get('Put', {})
            item = put_item.get('Item')

            if not isinstance(item, dict):
                raise DataStoreError(
                    f'Transaction item at index {index} is missing an Item payload.'
                )

            for attribute in (TABLE_PK_ATTRIBUTE, TABLE_SK_ATTRIBUTE):
                if attribute not in item:
                    raise DataStoreError(
                        f'Transaction item at index {index} is missing key: {attribute}.'
                    )

                attribute_value = item[attribute]
                if not isinstance(attribute_value, str) or not attribute_value.strip():
                    raise DataStoreError(
                        f'Transaction item at index {index} has invalid value for '
                        f'key {attribute}: {attribute_value}.'
                    )

    def _to_dynamodb(self, value: Any) -> Any:
        return _convert_floats_to_decimal(value)



def get_user_from_event(event: Dict[str, Any]) -> UserSummary:
    authorizer = event.get('requestContext', {}).get('authorizer', {})
    claims = authorizer.get('jwt', {}).get('claims') or authorizer.get('claims', {})

    if not isinstance(claims, dict):
        claims = {}

    user_sub = claims.get('sub')
    email = claims.get('email')

    if not user_sub:
        raise NotAuthenticatedError('Authenticated user claims were not found.')

    user: UserSummary = {'sub': str(user_sub), 'email': ''}
    if email:
        user['email'] = str(email)
    return user


def _dynamodb_key() -> Any:
    from boto3.dynamodb.conditions import Key

    return Key


def _convert_floats_to_decimal(value: Any) -> Any:
    if isinstance(value, float):
        return Decimal(str(value))
    if isinstance(value, dict):
        return {key: _convert_floats_to_decimal(item) for key, item in value.items()}
    if isinstance(value, list):
        return [_convert_floats_to_decimal(item) for item in value]
    if isinstance(value, tuple):
        return tuple(_convert_floats_to_decimal(item) for item in value)
    return value

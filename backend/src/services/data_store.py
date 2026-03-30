from __future__ import annotations

import logging
import os
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional
from uuid import uuid4

from models.types import FrameworkSummary, OrganisationSummary, UserSummary
from services.framework_registry import (
    build_framework_seed_items,
    load_framework_catalog,
    load_framework_definition,
)


class DataStoreError(RuntimeError):
    pass


class NotAuthenticatedError(DataStoreError):
    pass


class ConflictError(DataStoreError):
    pass


class ValidationError(DataStoreError):
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

VALID_ASSESSMENT_STATUSES = {'not_started', 'in_progress', 'completed'}

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
        key = _dynamodb_key()
        result = self.table.query(
            KeyConditionExpression=key('pk').eq('FRAMEWORKS') & key('sk').begins_with('FRAMEWORK#')
        )
        if result.get('Items'):
            return

        with self.table.batch_writer() as batch:
            for item in build_framework_seed_items():
                batch.put_item(
                    Item={
                        'pk': 'FRAMEWORKS',
                        'sk': f"FRAMEWORK#{item['frameworkId']}",
                        'entityType': item['entityType'],
                        'frameworkId': item['frameworkId'],
                        'name': item['name'],
                        'version': item['version'],
                        'description': item['description'],
                        'sections': item['sections'],
                    }
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

        return [
            {
                'frameworkId': item['frameworkId'],
                'name': item['name'],
                'version': item['version'],
                'description': item['description'],
                'sections': item.get('sections', []),
            }
            for item in items
        ]

    def get_bootstrap(self, user: UserSummary) -> Dict[str, Any]:
        membership = self._get_user_membership(user['sub'])
        organisation = None
        if membership:
            organisation = self._get_organisation(membership['organisationId'])

        return {
            'user': user,
            'hasOrganisation': organisation is not None,
            'organisation': organisation,
            'frameworks': self.list_frameworks(),
        }

    def create_or_resume_assessment(
        self, user: UserSummary, framework_id: str
    ) -> tuple[Dict[str, Any], bool]:
        membership = self._require_membership(user['sub'])
        organisation_id = membership['organisationId']
        framework = self._get_framework(framework_id)
        if framework is None:
            raise ValidationError(f'Framework not found: {framework_id}.')

        assessments = self._list_assessment_items(organisation_id, framework_id)
        in_progress = next(
            (item for item in assessments if item.get('status') == 'in_progress'),
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
            'frameworkId': framework_id,
            'organisationId': organisation_id,
            'createdBy': user['sub'],
            'createdAt': now,
            'updatedAt': now,
            'status': 'not_started',
            'currentSectionId': current_section_id,
        }
        self.table.put_item(Item=assessment_item)
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

        sections = self._load_assessment_sections(framework)
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

        sections = self._load_assessment_sections(framework)
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
        self.table.put_item(Item=response_item)

        next_status = 'in_progress'
        next_section_id = section_id
        if section_id in section_ids:
            section_index = section_ids.index(section_id)
            has_next = section_index + 1 < len(section_ids)
            next_section_id = section_ids[section_index + 1] if has_next else section_id
            if not has_next:
                next_status = 'completed'

        self.table.update_item(
            Key={'pk': f'ORG#{organisation_id}', 'sk': f'ASSESSMENT#{assessment_id}'},
            UpdateExpression=(
                'SET #status = :status, currentSectionId = :section, updatedAt = :updatedAt'
            ),
            ExpressionAttributeNames={'#status': 'status'},
            ExpressionAttributeValues={
                ':status': next_status,
                ':section': next_section_id,
                ':updatedAt': now,
            },
        )
        refreshed = self._get_assessment_item(organisation_id, assessment_id)
        if not refreshed:
            raise DataStoreError('Assessment update failed.')
        return self._serialize_assessment_summary(refreshed)

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
                        Item=item,
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
        self.ensure_framework_seed_data()
        result = self.table.get_item(Key={'pk': 'FRAMEWORKS', 'sk': f'FRAMEWORK#{framework_id}'})
        item = result.get('Item')
        framework = load_framework_definition()
        if item and self._framework_contains_questions(item):
            return item

        if framework.get('frameworkId') == framework_id:
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
        if self._sections_have_questions(sections):
            return sections

        fallback_framework = load_framework_definition()
        fallback_sections = self._normalise_framework_sections(
            fallback_framework.get('sections', [])
        )
        if self._sections_have_questions(fallback_sections):
            logger.warning(
                'Assessment framework did not contain questions; using local fallback definition.',
                extra={'frameworkId': framework.get('frameworkId')},
            )
            return fallback_sections

        return sections

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
                ExpressionAttributeValues={
                    ':sections': framework_definition.get('sections', []),
                    ':updatedAt': datetime.now(timezone.utc).isoformat(),
                },
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
            and item.get('status') in VALID_ASSESSMENT_STATUSES
            and (framework_id is None or item.get('frameworkId') == framework_id)
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
        return {
            'assessmentId': item['assessmentId'],
            'frameworkId': item['frameworkId'],
            'organisationId': item['organisationId'],
            'createdBy': item['createdBy'],
            'createdAt': item['createdAt'],
            'updatedAt': item['updatedAt'],
            'status': item['status'],
            'currentSectionId': item.get('currentSectionId', ''),
        }

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

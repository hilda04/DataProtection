from __future__ import annotations

import logging
import os
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional
from uuid import uuid4

from models.types import FrameworkSummary, OrganisationSummary, UserSummary
from services.framework_registry import build_framework_seed_items, load_framework_catalog


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
                    'Item': _serialize_item(organisation_item),
                    'ConditionExpression': CREATE_ORGANISATION_CONDITION_EXPRESSION,
                }
            },
            {
                'Put': {
                    'TableName': table_name,
                    'Item': _serialize_item(membership_item),
                    'ConditionExpression': CREATE_ORGANISATION_CONDITION_EXPRESSION,
                }
            },
        ]

        self._validate_transact_items(transact_items)

        first_item = transact_items[0]['Put']['Item']
        first_item_pk = first_item.get(TABLE_PK_ATTRIBUTE)
        first_item_sk = first_item.get(TABLE_SK_ATTRIBUTE)

        logger.error('DYNAMODB TABLE NAME: %s', table_name)
        logger.error('TRANSACT ITEMS: %s', transact_items)
        logger.error('FIRST TRANSACT ITEM PK: %s', first_item_pk)
        logger.error('FIRST TRANSACT ITEM SK: %s', first_item_sk)
        logger.error(
            'FIRST ITEM KEY ATTRIBUTE TYPES: pk=%s sk=%s',
            type(first_item_pk).__name__,
            type(first_item_sk).__name__,
        )
        logger.error(
            'FIRST ITEM KEY ATTRIBUTEVALUE SHAPES: pk_has_S=%s sk_has_S=%s',
            isinstance(first_item_pk, dict) and 'S' in first_item_pk,
            isinstance(first_item_sk, dict) and 'S' in first_item_sk,
        )

        for index, transaction in enumerate(transact_items):
            marshalled_item = transaction.get('Put', {}).get('Item', {})
            marshalled_types = {
                key: sorted(value.keys()) if isinstance(value, dict) else str(type(value).__name__)
                for key, value in marshalled_item.items()
            }
            logger.error('TRANSACT ITEM %s ATTRIBUTEVALUE TYPES: %s', index, marshalled_types)

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
                    client.put_item(
                        TableName=table_name,
                        Item=_serialize_item(item),
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
            marshalled_item = put_item.get('Item')

            if not isinstance(marshalled_item, dict):
                raise DataStoreError(
                    f'Transaction item at index {index} is missing a marshalled Item payload.'
                )

            for attribute in (TABLE_PK_ATTRIBUTE, TABLE_SK_ATTRIBUTE):
                if attribute not in marshalled_item:
                    raise DataStoreError(
                        f'Transaction item at index {index} is missing marshalled key: {attribute}.'
                    )

                marshalled_attribute = marshalled_item[attribute]
                if not isinstance(marshalled_attribute, dict) or 'S' not in marshalled_attribute:
                    raise DataStoreError(
                        f'Transaction item at index {index} has invalid AttributeValue '
                        f'for key {attribute}: {marshalled_attribute}.'
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


def _serialize_item(item: Dict[str, Any]) -> Dict[str, Dict[str, Any]]:
    from boto3.dynamodb.types import TypeSerializer

    serializer = TypeSerializer()
    return {key: serializer.serialize(value) for key, value in item.items()}

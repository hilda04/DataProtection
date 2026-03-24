from __future__ import annotations

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


REQUIRED_ORGANISATION_FIELDS = (
    'name',
    'sector',
    'size',
    'country',
    'primaryContactName',
    'primaryContactEmail',
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
            'pk': f"ORG#{organisation_id}",
            'sk': 'META',
            'entityType': 'ORGANISATION',
            **organisation,
        }
        membership_item = {
            'pk': f"USER#{user['sub']}",
            'sk': f"MEMBERSHIP#ORG#{organisation_id}",
            'entityType': 'USER_ORGANISATION_MEMBERSHIP',
            'organisationId': organisation_id,
            'userSub': user['sub'],
            'email': user['email'],
            'role': 'owner',
            'createdAt': created_at,
        }

        client = self.table.meta.client
        table_name = self.table.name

        try:
            client.transact_write_items(
                TransactItems=[
                    {
                        'Put': {
                            'TableName': table_name,
                            'Item': _serialize_item(organisation_item),
                            'ConditionExpression': (
                                'attribute_not_exists(pk) AND '
                                'attribute_not_exists(sk)'
                            ),
                        }
                    },
                    {
                        'Put': {
                            'TableName': table_name,
                            'Item': _serialize_item(membership_item),
                            'ConditionExpression': (
                                'attribute_not_exists(pk) AND '
                                'attribute_not_exists(sk)'
                            ),
                        }
                    },
                ]
            )
        except Exception as error:
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

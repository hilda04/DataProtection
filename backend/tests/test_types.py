from __future__ import annotations

import json
from decimal import Decimal

from models.types import ApiResponse, safe_json_dumps, to_json_safe


def test_to_json_safe_converts_decimal_values_recursively() -> None:
    payload = {
        'whole': Decimal('4'),
        'fractional': Decimal('4.25'),
        'nested': {
            'list': [Decimal('7'), {'value': Decimal('3.50')}],
        },
    }

    result = to_json_safe(payload)

    assert result == {
        'whole': 4,
        'fractional': 4.25,
        'nested': {
            'list': [7, {'value': 3.5}],
        },
    }


def test_safe_json_dumps_serializes_decimal_values() -> None:
    payload = {'value': Decimal('9.75'), 'count': Decimal('2')}

    encoded = safe_json_dumps(payload)

    assert json.loads(encoded) == {'value': 9.75, 'count': 2}


def test_api_response_to_dict_uses_safe_json_serialization() -> None:
    response = ApiResponse(
        status_code=200,
        body={'scores': [Decimal('10'), {'weight': Decimal('0.5')}]},
    ).to_dict()

    assert response['statusCode'] == 200
    assert json.loads(response['body']) == {'scores': [10, {'weight': 0.5}]}

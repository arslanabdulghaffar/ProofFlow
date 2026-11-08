"""Access envelope validates the actual product token format and fixed destination."""

import sys
from datetime import UTC, datetime, timedelta
from pathlib import Path
from uuid import uuid4

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / 'scripts'))
from guest_demo_access import validate  # noqa: E402

from api.app.auth import AuthError, SessionSecrets  # noqa: E402


def value():
    secrets = SessionSecrets.create()
    return {'window_id': str(uuid4()), 'workspace_id': str(uuid4()),
            'origin': 'https://158.247.227.66:8443', 'token': secrets.token, 'csrf': secrets.csrf,
            'expires_at': (datetime.now(UTC) + timedelta(minutes=30)).isoformat()}


def test_generated_product_tokens_are_accepted():
    validate(value(), datetime.now(UTC))


@pytest.mark.parametrize('field, changed', [('token', 'x' * 43), ('csrf', 'x' * 43),
    ('origin', 'https://unrelated.invalid'), ('origin', 'https://158.247.227.66:8443/#secret'),
    ('expires_at', '2020-01-01T00:00:00+00:00')])
def test_malformed_expired_or_redirected_access_fails(field, changed):
    with pytest.raises((RuntimeError, AuthError)):
        validate(value() | {field: changed}, datetime.now(UTC))

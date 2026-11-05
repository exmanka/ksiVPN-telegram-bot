"""Grace-period configuration and the raw ``PATCH /api/users`` body.

- ``GraceSettings``: ``days`` bounds, ``internal_squad_uuid`` required only when enabled,
  ``external_squad_uuid`` optional, empty strings from docker compose become None.
- ``build_update_user_payload``: ``UNSET`` fields are omitted, ``None`` external
  squad is sent as JSON null (the SDK can't do that), dates are UTC with ``Z``.
"""

import uuid
from datetime import datetime

import pytest
from pydantic import ValidationError

from src.config.schema import GraceSettings
from src.services import remnawave_service
from src.services.remnawave_service import UNSET, build_update_user_payload


SQUAD = uuid.UUID('11111111-1111-1111-1111-111111111111')
EXT = uuid.UUID('22222222-2222-2222-2222-222222222222')
USER = uuid.UUID('33333333-3333-3333-3333-333333333333')


# --- GraceSettings ------------------------------------------------------------

def test_defaults_are_disabled_three_days():
    grace = GraceSettings()
    assert (grace.enabled, grace.days, grace.internal_squad_uuid, grace.external_squad_uuid) == (False, 3, None, None)


def test_enabled_requires_squad():
    with pytest.raises(ValidationError, match='internal_squad_uuid is required'):
        GraceSettings(enabled=True)


def test_enabled_without_external_squad_is_valid():
    grace = GraceSettings(enabled=True, internal_squad_uuid=str(SQUAD))
    assert grace.internal_squad_uuid == SQUAD
    assert grace.external_squad_uuid is None


@pytest.mark.parametrize('days', [0, 31, -1])
def test_days_out_of_range_rejected(days):
    with pytest.raises(ValidationError):
        GraceSettings(days=days)


def test_days_is_configurable():
    assert GraceSettings(days=1).days == 1
    assert GraceSettings(days=30).days == 30


def test_empty_strings_from_compose_become_none():
    grace = GraceSettings(enabled=False, internal_squad_uuid='', external_squad_uuid='')
    assert grace.internal_squad_uuid is None and grace.external_squad_uuid is None

    with pytest.raises(ValidationError, match='internal_squad_uuid is required'):
        GraceSettings(enabled=True, internal_squad_uuid='')


# --- build_update_user_payload --------------------------------------------------

@pytest.fixture
def moscow_bot_tz(monkeypatch):
    monkeypatch.setattr(remnawave_service.settings, 'tz', 'Europe/Moscow')


def test_payload_only_expire_at_by_default(moscow_bot_tz):
    payload = build_update_user_payload(USER, expire_at=datetime(2026, 11, 10, 15, 0))

    assert payload == {'uuid': str(USER), 'expireAt': '2026-11-10T12:00:00.000Z'}


def test_payload_with_squads_and_external(moscow_bot_tz):
    payload = build_update_user_payload(
        USER, expire_at=datetime(2026, 11, 10, 15, 0), internal_squads=[SQUAD], external_squad=EXT,
    )

    assert payload['activeInternalSquads'] == [str(SQUAD)]
    assert payload['externalSquadUuid'] == str(EXT)


def test_payload_none_external_squad_is_sent_as_null(moscow_bot_tz):
    payload = build_update_user_payload(USER, expire_at=datetime(2026, 11, 10, 15, 0), external_squad=None)

    assert 'externalSquadUuid' in payload and payload['externalSquadUuid'] is None
    assert 'activeInternalSquads' not in payload


def test_unset_is_omitted(moscow_bot_tz):
    payload = build_update_user_payload(
        USER, expire_at=datetime(2026, 11, 10, 15, 0), internal_squads=UNSET, external_squad=UNSET,
    )

    assert set(payload) == {'uuid', 'expireAt'}

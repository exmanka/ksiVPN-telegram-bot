"""Regression tests for ``YooMoneyTransferProvider.get_status`` label-filtering.

Background: an early version of ``get_status`` relied on YooMoney's server-side
``label`` filter alone and picked ``operations[-1]`` to decide success. That
combination caused false positives in dev — when the API returned the full
operation history (server-side filter not honored), any new payment was
finalized because the latest historic operation in the wallet was a past
successful test payment.

These tests pin the contract: SUCCEEDED only when an operation with a
matching label exists.
"""

import json
from unittest.mock import AsyncMock, MagicMock

import pytest

from src.payments.enums import PaymentStatus
from src.payments.providers.yoomoney import YooMoneyTransferProvider


@pytest.fixture
def provider() -> YooMoneyTransferProvider:
    return YooMoneyTransferProvider(
        receiver_account=4100123456789,
        access_token="test-token",
        notification_secret="test-secret",
    )


def _mock_response(payload: dict, status: int = 200):
    """Build an awaitable async-context-manager wrapping aiohttp.ClientResponse."""
    resp = MagicMock()
    resp.status = status
    resp.json = AsyncMock(return_value=payload)
    # The async-context-manager protocol used by ``async with resp:``.
    resp.__aenter__ = AsyncMock(return_value=resp)
    resp.__aexit__ = AsyncMock(return_value=None)
    return resp


async def test_get_status_returns_pending_when_label_does_not_match(provider, monkeypatch):
    """The bug we're guarding against: server returns historic ops, none for our label."""
    # Server-side filter ignored — full history returned. The latest op is a
    # past successful payment under a DIFFERENT label.
    historic_payload = {
        "operations": [
            {"label": "1", "status": "success", "amount": 5.4, "operation_id": "op-1"},
            {"label": "2", "status": "success", "amount": 5.4, "operation_id": "op-2"},
            {"label": "3", "status": "success", "amount": 5.4, "operation_id": "op-3"},
        ],
    }
    response = _mock_response(historic_payload)
    monkeypatch.setattr(
        provider, "_request_with_retry", AsyncMock(return_value=response),
    )

    event = await provider.get_status("4")  # we're asking about payment_id=4

    assert event.status == PaymentStatus.PENDING, (
        "Past payments with different labels must NOT match a fresh query — "
        "this is the bug that finalized unpaid invoices in dev."
    )
    assert event.external_id == "4"


async def test_get_status_returns_succeeded_only_for_matching_label(provider, monkeypatch):
    payload = {
        "operations": [
            {"label": "1", "status": "success", "amount": 5.4, "operation_id": "op-1"},
            {"label": "4", "status": "success", "amount": 5.4, "operation_id": "op-4"},
        ],
    }
    response = _mock_response(payload)
    monkeypatch.setattr(
        provider, "_request_with_retry", AsyncMock(return_value=response),
    )

    event = await provider.get_status("4")

    assert event.status == PaymentStatus.SUCCEEDED
    # payment_id is always None from YooMoney get_status — PaymentService resolves
    # it via DB lookup by (provider, external_id). See service.handle_event.
    assert event.payment_id is None
    # raw_payload is the matching operation, not the most recent one.
    assert event.raw_payload == {"label": "4", "status": "success", "amount": 5.4, "operation_id": "op-4"}


async def test_get_status_returns_pending_for_empty_history(provider, monkeypatch):
    response = _mock_response({"operations": []})
    monkeypatch.setattr(
        provider, "_request_with_retry", AsyncMock(return_value=response),
    )
    event = await provider.get_status("42")
    assert event.status == PaymentStatus.PENDING


async def test_get_status_returns_pending_when_matching_operation_not_successful(provider, monkeypatch):
    """A label-matching operation with status != 'success' is still PENDING."""
    payload = {
        "operations": [
            {"label": "4", "status": "refused", "amount": 5.4, "operation_id": "op-4"},
        ],
    }
    response = _mock_response(payload)
    monkeypatch.setattr(
        provider, "_request_with_retry", AsyncMock(return_value=response),
    )

    event = await provider.get_status("4")
    assert event.status == PaymentStatus.PENDING

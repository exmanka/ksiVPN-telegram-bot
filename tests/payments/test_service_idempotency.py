"""Idempotency contract of ``PaymentService.handle_event``.

The service is intentionally narrow: it owns the atomic finalize and invokes
``on_payment_succeeded`` exactly once. The post-finalize business chain
(Remnawave, referral, admin/user notifications, FSM, keyboards) lives in
``src.services.internal_functions.finalize_successful_payment`` and is NOT
tested here — that's the wiring's responsibility, not the service's.

What we DO test here:

- Double-delivery of the same SUCCEEDED event → callback invoked exactly once.
- Already-finalized event → callback NOT invoked; raw_payload still recorded.
- Callback failure → caught and logged; service does not propagate.
- ``payment_id`` resolution from the DB context when the event provides it.
"""

from decimal import Decimal
from unittest.mock import AsyncMock

import pytest

from src.payments.enums import PaymentStatus
from src.payments.models import ProviderPaymentEvent
from src.payments.service import PaymentService


def _make_service(callback: AsyncMock) -> PaymentService:
    return PaymentService(
        providers={},
        on_payment_succeeded=callback,
        test_user_ids=[],
        test_price=Decimal("2"),
    )


async def test_double_event_calls_callback_exactly_once(monkeypatch):
    """Two identical succeeded events → claim_finalize wins once → callback called once."""
    claim_calls = 0

    async def fake_claim(*, payment_id, client_id, days_number):
        nonlocal claim_calls
        claim_calls += 1
        # First call wins; subsequent calls find status='succeeded' and return False.
        return claim_calls == 1

    monkeypatch.setattr(
        "src.payments.repository.get_finalize_context",
        AsyncMock(return_value={
            "id": 42, "client_id": 100, "days_number": 30,
            "status": "pending", "telegram_id": 999, "telegram_message_id": 555,
        }),
    )
    monkeypatch.setattr("src.payments.repository.claim_finalize", AsyncMock(side_effect=fake_claim))
    monkeypatch.setattr("src.payments.repository.record_raw_payload", AsyncMock())

    callback = AsyncMock()
    service = _make_service(callback)

    event = ProviderPaymentEvent(
        external_id="42",
        status=PaymentStatus.SUCCEEDED,
        payment_id=42,
        raw_payload={"operation_id": "abc"},
    )

    await service.handle_event(event)
    await service.handle_event(event)  # duplicate delivery

    # claim_finalize attempted twice, only one win; callback fires only on the win.
    assert claim_calls == 2
    callback.assert_awaited_once_with(42, 100, 30)


async def test_already_finalized_event_skips_callback(monkeypatch):
    """When claim returns False (someone else got it), callback is NOT invoked."""
    monkeypatch.setattr(
        "src.payments.repository.get_finalize_context",
        AsyncMock(return_value={
            "id": 42, "client_id": 100, "days_number": 30,
            "status": "succeeded", "telegram_id": 999, "telegram_message_id": 555,
        }),
    )
    monkeypatch.setattr("src.payments.repository.claim_finalize", AsyncMock(return_value=False))
    raw_mock = AsyncMock()
    monkeypatch.setattr("src.payments.repository.record_raw_payload", raw_mock)

    callback = AsyncMock()
    service = _make_service(callback)

    event = ProviderPaymentEvent(
        external_id="42",
        status=PaymentStatus.SUCCEEDED,
        payment_id=42,
        raw_payload={"operation_id": "abc"},
    )

    await service.handle_event(event)

    callback.assert_not_awaited()
    # raw_payload still persisted — useful for diagnostics on duplicate webhooks.
    raw_mock.assert_awaited_once()


async def test_callback_failure_is_swallowed(monkeypatch):
    """A failing post-finalize callback must not propagate — DB is the source of truth."""
    monkeypatch.setattr(
        "src.payments.repository.get_finalize_context",
        AsyncMock(return_value={
            "id": 42, "client_id": 100, "days_number": 30,
            "status": "pending", "telegram_id": 999, "telegram_message_id": 555,
        }),
    )
    monkeypatch.setattr("src.payments.repository.claim_finalize", AsyncMock(return_value=True))
    monkeypatch.setattr("src.payments.repository.record_raw_payload", AsyncMock())

    callback = AsyncMock(side_effect=RuntimeError("Remnawave panel down"))
    service = _make_service(callback)

    event = ProviderPaymentEvent(
        external_id="42",
        status=PaymentStatus.SUCCEEDED,
        payment_id=42,
        raw_payload={"operation_id": "abc"},
    )

    # Must not raise.
    await service.handle_event(event)

    callback.assert_awaited_once_with(42, 100, 30)


async def test_event_without_payment_id_raises(monkeypatch):
    """Events arriving without a payment_id are a provider contract violation."""
    monkeypatch.setattr("src.payments.repository.get_finalize_context", AsyncMock())

    callback = AsyncMock()
    service = _make_service(callback)

    event = ProviderPaymentEvent(
        external_id="42", status=PaymentStatus.SUCCEEDED, payment_id=None,
    )

    with pytest.raises(Exception, match="payment_id"):
        await service.handle_event(event)

    callback.assert_not_awaited()


async def test_raw_payload_persisted_on_winning_claim(monkeypatch):
    """The winning claim path also persists raw_payload (forensics)."""
    monkeypatch.setattr(
        "src.payments.repository.get_finalize_context",
        AsyncMock(return_value={
            "id": 42, "client_id": 100, "days_number": 30,
            "status": "pending", "telegram_id": 999, "telegram_message_id": 555,
        }),
    )
    monkeypatch.setattr("src.payments.repository.claim_finalize", AsyncMock(return_value=True))
    raw_mock = AsyncMock()
    monkeypatch.setattr("src.payments.repository.record_raw_payload", raw_mock)

    callback = AsyncMock()
    service = _make_service(callback)

    event = ProviderPaymentEvent(
        external_id="42",
        status=PaymentStatus.SUCCEEDED,
        payment_id=42,
        raw_payload={"operation_id": "abc", "amount": "300.00"},
    )

    await service.handle_event(event)
    raw_mock.assert_awaited_once()

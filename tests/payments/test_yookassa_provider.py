"""YookassaProvider — contract tests with mocked SDK.

We don't call YooKassa's real API; instead we patch ``yookassa.Payment.create``
and ``yookassa.Payment.find_one`` to return SDK-shaped fakes. The goal is to
prove the adapter:

- Builds correctly-shaped Payment.create payloads (amount string, capture, metadata).
- Maps every documented YooKassa status to our ``PaymentStatus`` enum.
- Re-fetches from API in ``parse_webhook`` instead of trusting the body
  (the security boundary — YooKassa webhooks are unsigned).
- Raises ``InvalidWebhookSignature`` for malformed webhook envelopes.
- Wraps SDK exceptions as ``ProviderError``.
"""

import json
from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest

from src.payments.enums import PaymentStatus
from src.payments.exceptions import InvalidWebhookSignature, ProviderError
from src.payments.models import Money
from src.payments.providers.yookassa import YookassaProvider


def _fake_payment(
    *,
    id_: str = "2db5e3a4-000f-5000-9000-1b68e7c41e2a",
    status: str = "succeeded",
    payment_id: int | None = 42,
    value: str = "300.00",
    confirmation_url: str | None = "https://yookassa.example/checkout/...",
):
    """Build a duck-typed YooKassa Payment object."""
    return SimpleNamespace(
        id=id_,
        status=status,
        paid=(status == "succeeded"),
        test=True,
        created_at="2026-05-20T12:00:00.000Z",
        captured_at="2026-05-20T12:00:05.000Z" if status == "succeeded" else None,
        expires_at=None,
        description="Подписка ksiVPN",
        amount=SimpleNamespace(value=value, currency="RUB"),
        confirmation=SimpleNamespace(
            type="redirect",
            confirmation_url=confirmation_url,
        ),
        metadata={"payment_id": str(payment_id)} if payment_id is not None else {},
    )


@pytest.fixture
def provider() -> YookassaProvider:
    return YookassaProvider(
        shop_id=123456,
        secret_key="test-secret-key",
        return_url="https://t.me/ksiVPN_bot",
    )


async def test_create_invoice_builds_correct_payload(provider, monkeypatch):
    """Payload must have amount as decimal string, capture=true, metadata with payment_id."""
    captured: dict = {}

    def fake_create(payload, idempotence_key):
        captured["payload"] = payload
        captured["idempotence_key"] = idempotence_key
        return _fake_payment(id_="yk-123", status="pending")

    monkeypatch.setattr("src.payments.providers.yookassa.YooKassaPayment.create", fake_create)

    invoice = await provider.create_invoice(
        payment_id=42,
        amount=Money(amount=300, currency="RUB"),  # type: ignore[arg-type]
        description="test",
    )

    assert captured["idempotence_key"] == "42"
    payload = captured["payload"]
    assert payload["amount"] == {"value": "300.00", "currency": "RUB"}
    assert payload["capture"] is True
    assert payload["metadata"] == {"payment_id": "42"}
    assert payload["confirmation"]["type"] == "redirect"
    assert payload["confirmation"]["return_url"] == "https://t.me/ksiVPN_bot"

    assert invoice.external_id == "yk-123"
    assert invoice.payment_url.startswith("https://")


async def test_create_invoice_uses_explicit_return_url(provider, monkeypatch):
    captured: dict = {}

    def fake_create(payload, idempotence_key):
        captured["payload"] = payload
        return _fake_payment(id_="yk-123", status="pending")

    monkeypatch.setattr("src.payments.providers.yookassa.YooKassaPayment.create", fake_create)

    await provider.create_invoice(
        payment_id=1,
        amount=Money(amount=2, currency="RUB"),  # type: ignore[arg-type]
        description="x",
        return_url="https://example.com/return",
    )
    assert captured["payload"]["confirmation"]["return_url"] == "https://example.com/return"


async def test_create_invoice_wraps_sdk_errors(provider, monkeypatch):
    from yookassa.domain.exceptions import ApiError

    def boom(payload, idempotence_key):
        # YooKassa's ApiError constructor expects a dict-like — match SDK shape.
        raise ApiError({"description": "API down", "code": "internal_error"})

    monkeypatch.setattr("src.payments.providers.yookassa.YooKassaPayment.create", boom)

    with pytest.raises(ProviderError, match="Payment.create failed"):
        await provider.create_invoice(
            payment_id=1,
            amount=Money(amount=2, currency="RUB"),  # type: ignore[arg-type]
            description="x",
        )


async def test_create_invoice_raises_when_no_confirmation_url(provider, monkeypatch):
    """A pending payment without a confirmation URL is a YooKassa contract violation."""
    monkeypatch.setattr(
        "src.payments.providers.yookassa.YooKassaPayment.create",
        lambda p, k: _fake_payment(id_="yk-x", status="pending", confirmation_url=None),
    )
    with pytest.raises(ProviderError, match="no confirmation_url"):
        await provider.create_invoice(
            payment_id=1,
            amount=Money(amount=2, currency="RUB"),  # type: ignore[arg-type]
            description="x",
        )


@pytest.mark.parametrize(
    "yookassa_status,expected",
    [
        ("succeeded", PaymentStatus.SUCCEEDED),
        ("canceled", PaymentStatus.FAILED),
        ("pending", PaymentStatus.PENDING),
        ("waiting_for_capture", PaymentStatus.PENDING),
    ],
)
async def test_get_status_maps_provider_statuses(provider, monkeypatch, yookassa_status, expected):
    monkeypatch.setattr(
        "src.payments.providers.yookassa.YooKassaPayment.find_one",
        lambda eid: _fake_payment(id_=eid, status=yookassa_status, payment_id=99),
    )

    event = await provider.get_status("yk-id-1")

    assert event.status == expected
    assert event.external_id == "yk-id-1"
    assert event.payment_id == 99


async def test_get_status_unknown_status_falls_back_to_pending(provider, monkeypatch):
    """Defensive: a status YooKassa adds in the future should NOT be treated as succeeded."""
    monkeypatch.setattr(
        "src.payments.providers.yookassa.YooKassaPayment.find_one",
        lambda eid: _fake_payment(id_=eid, status="some_new_future_status"),
    )
    event = await provider.get_status("yk-id-1")
    assert event.status == PaymentStatus.PENDING


async def test_parse_webhook_refetches_status_from_api(provider, monkeypatch):
    """Key security property: webhook body is NOT trusted — status comes from API re-fetch."""
    fetch_called = False

    def fake_find_one(external_id):
        nonlocal fetch_called
        fetch_called = True
        # Even though the webhook body claims "succeeded", we return a "canceled"
        # to prove the body is not trusted.
        return _fake_payment(id_=external_id, status="canceled")

    monkeypatch.setattr(
        "src.payments.providers.yookassa.YooKassaPayment.find_one", fake_find_one,
    )

    # Webhook body claims succeeded — attacker could spoof this.
    webhook_body = json.dumps({
        "type": "notification",
        "event": "payment.succeeded",
        "object": {
            "id": "spoofed-id",
            "status": "succeeded",  # ← LIE
            "amount": {"value": "1000000.00", "currency": "RUB"},
            "metadata": {"payment_id": "42"},
            "paid": True,
        },
    }).encode("utf-8")

    event = await provider.parse_webhook(body=webhook_body, headers={})

    assert fetch_called, "must re-fetch from API instead of trusting body"
    assert event.status == PaymentStatus.FAILED  # from re-fetch, not from body


async def test_parse_webhook_rejects_invalid_json(provider):
    with pytest.raises(InvalidWebhookSignature, match="not valid JSON"):
        await provider.parse_webhook(body=b"not json at all", headers={})


async def test_parse_webhook_rejects_envelope_without_object_id(provider, monkeypatch):
    body = json.dumps({"type": "notification", "event": "payment.succeeded"}).encode("utf-8")
    with pytest.raises(InvalidWebhookSignature):
        await provider.parse_webhook(body=body, headers={})


async def test_parse_webhook_wraps_api_errors_during_refetch(provider, monkeypatch):
    from yookassa.domain.exceptions import ApiError

    def boom(external_id):
        raise ApiError({"description": "upstream temporary error", "code": "internal_error"})

    monkeypatch.setattr("src.payments.providers.yookassa.YooKassaPayment.find_one", boom)

    body = json.dumps({
        "type": "notification",
        "event": "payment.succeeded",
        "object": {"id": "yk-id-1", "status": "succeeded"},
    }).encode("utf-8")

    with pytest.raises(ProviderError, match="re-fetch failed"):
        await provider.parse_webhook(body=body, headers={})


async def test_raw_payload_is_jsonable(provider, monkeypatch):
    """The raw_payload we store must survive json.dumps — never persist SDK objects."""
    monkeypatch.setattr(
        "src.payments.providers.yookassa.YooKassaPayment.find_one",
        lambda eid: _fake_payment(id_=eid, status="succeeded", payment_id=42),
    )

    event = await provider.get_status("yk-id-1")

    # Must round-trip through json without error.
    serialized = json.dumps(event.raw_payload)
    assert "succeeded" in serialized
    assert "300.00" in serialized

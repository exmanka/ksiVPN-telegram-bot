"""HMAC-SHA256 verification for YooMoney P2P webhooks.

These tests guard the security boundary: webhook handler trusts the
provider's signature check; if it accepts a wrong signature, an attacker
could fake "payment received" and extend a subscription for free.
"""

import hashlib
import hmac
import urllib.parse

import pytest

from src.payments.exceptions import InvalidWebhookSignature
from src.payments.providers.yoomoney import (
    YooMoneyTransferProvider,
    _compute_yoomoney_signature,
)


def _build_signed_body(fields: dict[str, str], secret: str) -> bytes:
    """Build a urlencoded body with a valid YooMoney signature.

    Pure helper that mirrors the algorithm — useful as both test input
    and a documented reference of the expected format.
    """
    sign = _compute_yoomoney_signature(fields, secret)
    payload = {**fields, "sign": sign}
    return urllib.parse.urlencode(payload).encode("utf-8")


SECRET = "test-notification-secret"


@pytest.fixture
def provider() -> YooMoneyTransferProvider:
    return YooMoneyTransferProvider(
        receiver_account=4100123456789,
        access_token="ignored-for-webhook-tests",
        notification_secret=SECRET,
    )


def test_signature_matches_documented_algorithm():
    """Reference vector: sorted, URL-encoded, &-joined, HMAC-SHA256, hex lowercase."""
    fields = {"a": "1", "b": "two words", "z": "yes"}
    expected = hmac.new(
        SECRET.encode("utf-8"),
        b"a=1&b=two%20words&z=yes",
        hashlib.sha256,
    ).hexdigest()
    assert _compute_yoomoney_signature(fields, SECRET) == expected


def test_url_encoding_uses_rfc3986():
    """Reserved/special characters must be percent-encoded with quote(safe='')."""
    fields = {"x": "hello world+foo"}
    # urllib.parse.quote(s, safe='') encodes ' ' as %20 and '+' as %2B (RFC 3986).
    sig = _compute_yoomoney_signature(fields, SECRET)
    expected_payload = b"x=hello%20world%2Bfoo"
    expected = hmac.new(SECRET.encode("utf-8"), expected_payload, hashlib.sha256).hexdigest()
    assert sig == expected


async def test_parse_webhook_accepts_valid_signature(provider):
    fields = {
        "notification_type": "p2p-incoming",
        "operation_id": "1234567890",
        "amount": "300.00",
        "withdraw_amount": "300.00",
        "currency": "643",
        "datetime": "2026-05-20T12:00:00Z",
        "sender": "4100987654321",
        "codepro": "false",
        "label": "42",
    }
    body = _build_signed_body(fields, SECRET)

    event = await provider.parse_webhook(body=body, headers={})

    assert event.payment_id == 42
    assert event.external_id == "42"
    assert event.status.value == "succeeded"
    assert event.raw_payload == fields  # 'sign' stripped, others preserved


async def test_parse_webhook_rejects_wrong_signature(provider):
    fields = {
        "notification_type": "p2p-incoming",
        "operation_id": "1234567890",
        "amount": "300.00",
        "label": "42",
    }
    # Build body signed with the WRONG secret.
    bad_body = _build_signed_body(fields, "attacker-guess")
    with pytest.raises(InvalidWebhookSignature, match="signature mismatch"):
        await provider.parse_webhook(body=bad_body, headers={})


async def test_parse_webhook_rejects_missing_signature(provider):
    body = urllib.parse.urlencode({
        "notification_type": "p2p-incoming",
        "operation_id": "1234567890",
        "label": "42",
    }).encode("utf-8")
    with pytest.raises(InvalidWebhookSignature, match="missing 'sign'"):
        await provider.parse_webhook(body=body, headers={})


async def test_parse_webhook_rejects_tampered_amount(provider):
    """A real attack: change amount but leave the original signature in place."""
    fields = {
        "notification_type": "p2p-incoming",
        "operation_id": "1234567890",
        "amount": "300.00",
        "label": "42",
    }
    body = _build_signed_body(fields, SECRET)
    # Mutate the body — replace amount but keep the now-stale sign.
    tampered = body.replace(b"amount=300.00", b"amount=99999.00")
    with pytest.raises(InvalidWebhookSignature, match="signature mismatch"):
        await provider.parse_webhook(body=tampered, headers={})


async def test_parse_webhook_rejects_unexpected_notification_type(provider):
    """Bot's wallet should only receive p2p-incoming or card-incoming."""
    fields = {
        "notification_type": "p2p-outgoing",  # this should never arrive
        "operation_id": "1234567890",
        "label": "42",
    }
    body = _build_signed_body(fields, SECRET)
    with pytest.raises(InvalidWebhookSignature, match="notification_type"):
        await provider.parse_webhook(body=body, headers={})


async def test_parse_webhook_handles_missing_label(provider):
    """If label is empty (shouldn't happen for our payments), payment_id is None."""
    fields = {
        "notification_type": "p2p-incoming",
        "operation_id": "1234567890",
        "label": "",
    }
    body = _build_signed_body(fields, SECRET)

    event = await provider.parse_webhook(body=body, headers={})
    assert event.payment_id is None
    assert event.external_id == ""


async def test_parse_webhook_includes_sha1_hash_in_signature(provider):
    """The legacy ``sha1_hash`` parameter is still part of the HMAC-SHA256 input.

    YooMoney sends both ``sha1_hash`` (deprecated) and ``sign`` until 2026-05-18.
    We must include ``sha1_hash`` when verifying ``sign`` or signatures would mismatch.
    """
    fields = {
        "notification_type": "p2p-incoming",
        "operation_id": "1234567890",
        "label": "42",
        "sha1_hash": "deadbeef" * 5,  # 40-char placeholder
    }
    body = _build_signed_body(fields, SECRET)

    event = await provider.parse_webhook(body=body, headers={})
    assert event.payment_id == 42
    assert "sha1_hash" in event.raw_payload

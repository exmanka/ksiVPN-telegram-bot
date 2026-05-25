"""Contract tests for ``PaymentProvider.fiscalize_income``.

The method has two well-defined branches:

- ``moy_nalog is None`` (provider's fiscalization is disabled in runtime wiring)
  → returns ``None`` without any I/O.
- ``moy_nalog is not None`` → delegates to ``MoyNalogClient.register_income``
  and returns its ``FiscalReceipt`` unchanged.

The actual «Мой налог» SDK call is mocked at the ``MoyNalogClient.register_income``
boundary — these tests don't exercise nalogo itself.
"""

from decimal import Decimal
from unittest.mock import AsyncMock, MagicMock

import pytest

from src.payments.fiscalization import FiscalReceipt
from src.payments.providers.yookassa import YookassaProvider
from src.payments.providers.yoomoney import YooMoneyTransferProvider


@pytest.fixture
def yookassa_no_fiscalizer() -> YookassaProvider:
    return YookassaProvider(
        shop_id=123456,
        secret_key="test-secret",
        return_url="https://t.me/ksiVPN_bot",
        moy_nalog=None,
    )


@pytest.fixture
def yoomoney_no_fiscalizer() -> YooMoneyTransferProvider:
    return YooMoneyTransferProvider(
        access_token="test-token",
        notification_secret="test-secret",
        moy_nalog=None,
    )


async def test_yookassa_fiscalize_disabled_returns_none(yookassa_no_fiscalizer):
    """When MoyNalogClient is not injected, fiscalize_income is a silent no-op."""
    result = await yookassa_no_fiscalizer.fiscalize_income(
        payment_id=42, amount=Decimal("300.00"), description="ignored",
    )
    assert result is None


async def test_yoomoney_fiscalize_disabled_returns_none(yoomoney_no_fiscalizer):
    result = await yoomoney_no_fiscalizer.fiscalize_income(
        payment_id=42, amount=Decimal("300.00"), description="ignored",
    )
    assert result is None


async def test_yookassa_fiscalize_delegates_to_moy_nalog():
    """When a MoyNalogClient is injected, fiscalize_income returns its FiscalReceipt verbatim."""
    expected = FiscalReceipt(
        receipt_uuid="abc-uuid",
        print_url="https://lknpd.nalog.ru/api/v1/receipt/123456789012/abc-uuid/print",
    )
    moy_nalog = MagicMock()
    moy_nalog.register_income = AsyncMock(return_value=expected)

    provider = YookassaProvider(
        shop_id=123456, secret_key="k", return_url="https://t.me/b",
        moy_nalog=moy_nalog,
    )

    result = await provider.fiscalize_income(
        payment_id=42, amount=Decimal("300.00"),
        description="Оплата подписки на 30 дней",
    )

    assert result is expected
    moy_nalog.register_income.assert_awaited_once_with(
        amount=Decimal("300.00"),
        description="Оплата подписки на 30 дней",
    )


async def test_yoomoney_fiscalize_delegates_to_moy_nalog():
    expected = FiscalReceipt(receipt_uuid="x", print_url="https://lknpd.example/x/print")
    moy_nalog = MagicMock()
    moy_nalog.register_income = AsyncMock(return_value=expected)

    provider = YooMoneyTransferProvider(
        access_token="t", notification_secret="s", moy_nalog=moy_nalog,
    )

    result = await provider.fiscalize_income(
        payment_id=99, amount=Decimal("100.00"), description="Оплата подписки на 90 дней",
    )

    assert result is expected
    moy_nalog.register_income.assert_awaited_once()

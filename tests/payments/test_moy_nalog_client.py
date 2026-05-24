"""Tests for MoyNalogClient — the «Мой налог» SDK wrapper.

The wrapper has two non-trivial behaviors worth pinning:

1. ``print_url`` is assembled with the **wrapper's INN** + the **SDK-returned UUID**.
   Off-by-one in URL template format would mean broken receipts shipped to buyers.
2. On ``UnauthorizedException`` during ``register_income``, the wrapper re-authenticates
   once and retries. After that one retry, failures propagate as ``FiscalizationError``.

The underlying ``nalogo.Client`` is fully mocked — these tests don't hit the network.
"""

from decimal import Decimal
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from nalogo import UnauthorizedException

from src.payments.fiscalization import FiscalizationError, MoyNalogClient


def _make_mocked_nalogo_client(create_responses, auth_responses=None):
    """Build a MagicMock that behaves enough like nalogo.Client for the wrapper.

    ``create_responses`` is the list of values/exceptions that
    ``client.income.create`` returns/raises on successive calls. ``auth_responses``
    is the same for ``client.create_new_access_token``; defaults to a stable token.
    """
    if auth_responses is None:
        auth_responses = ["access-token-1"]

    mock = MagicMock()
    mock.create_new_access_token = AsyncMock(side_effect=auth_responses)
    mock.authenticate = MagicMock(return_value=None)
    mock.income = MagicMock()
    mock.income.create = AsyncMock(side_effect=create_responses)
    mock.close = AsyncMock()
    return mock


@pytest.fixture
def patched_client_factory():
    """Patch the NalogoClient class so the wrapper consumes our mock instances.

    Yields a list that test code can populate with mock-builders, one per
    Client() instantiation expected during the test.
    """
    instances: list = []

    def factory(*args, **kwargs):
        if not instances:
            raise AssertionError("Test forgot to register a NalogoClient mock")
        return instances.pop(0)

    with patch("src.payments.fiscalization.moy_nalog.NalogoClient", side_effect=factory):
        yield instances


async def test_register_income_returns_print_url_with_inn_and_uuid(patched_client_factory):
    patched_client_factory.append(
        _make_mocked_nalogo_client(create_responses=[{"approvedReceiptUuid": "abc-123"}])
    )
    wrapper = MoyNalogClient(inn="123456789012", password="pw")

    receipt = await wrapper.register_income(
        amount=Decimal("300.00"),
        description="Оплата подписки на 30 дней",
    )

    assert receipt.receipt_uuid == "abc-123"
    assert receipt.print_url == "https://lknpd.nalog.ru/api/v1/receipt/123456789012/abc-123/print"


async def test_register_income_passes_arguments_to_sdk(patched_client_factory):
    nalogo_mock = _make_mocked_nalogo_client(
        create_responses=[{"approvedReceiptUuid": "u"}],
    )
    patched_client_factory.append(nalogo_mock)
    wrapper = MoyNalogClient(inn="1234567890", password="pw")

    await wrapper.register_income(amount=Decimal("99.50"), description="x")

    nalogo_mock.income.create.assert_awaited_once_with(
        name="x", amount=Decimal("99.50"), quantity=1,
    )


async def test_register_income_reauths_once_on_unauthorized(patched_client_factory):
    """First create_receipt raises 401 → wrapper re-auths and retries → success."""
    nalogo_mock = _make_mocked_nalogo_client(
        create_responses=[
            UnauthorizedException("token expired"),
            {"approvedReceiptUuid": "second-try-uuid"},
        ],
        auth_responses=["access-token-1", "access-token-2"],
    )
    patched_client_factory.append(nalogo_mock)
    wrapper = MoyNalogClient(inn="1234567890", password="pw")

    receipt = await wrapper.register_income(amount=Decimal("100"), description="x")

    assert receipt.receipt_uuid == "second-try-uuid"
    # Two auth calls: initial bootstrap + re-auth after 401.
    assert nalogo_mock.create_new_access_token.await_count == 2
    # Two create calls: failed + successful retry.
    assert nalogo_mock.income.create.await_count == 2


async def test_register_income_gives_up_after_one_reauth(patched_client_factory):
    """Two consecutive 401s → wrapper raises FiscalizationError, no second retry."""
    nalogo_mock = _make_mocked_nalogo_client(
        create_responses=[
            UnauthorizedException("expired"),
            UnauthorizedException("still expired"),
        ],
        auth_responses=["t1", "t2"],
    )
    patched_client_factory.append(nalogo_mock)
    wrapper = MoyNalogClient(inn="1234567890", password="pw")

    with pytest.raises(FiscalizationError, match="after re-auth"):
        await wrapper.register_income(amount=Decimal("100"), description="x")

    assert nalogo_mock.income.create.await_count == 2  # exactly two attempts, no more


async def test_register_income_wraps_non_auth_errors_as_fiscalization_error(patched_client_factory):
    nalogo_mock = _make_mocked_nalogo_client(
        create_responses=[RuntimeError("nalogo internals exploded")],
    )
    patched_client_factory.append(nalogo_mock)
    wrapper = MoyNalogClient(inn="1234567890", password="pw")

    with pytest.raises(FiscalizationError, match="income.create failed"):
        await wrapper.register_income(amount=Decimal("100"), description="x")


async def test_register_income_raises_when_sdk_returns_no_uuid(patched_client_factory):
    nalogo_mock = _make_mocked_nalogo_client(
        create_responses=[{"some_other_field": "no uuid here"}],
    )
    patched_client_factory.append(nalogo_mock)
    wrapper = MoyNalogClient(inn="1234567890", password="pw")

    with pytest.raises(FiscalizationError, match="no approvedReceiptUuid"):
        await wrapper.register_income(amount=Decimal("100"), description="x")


async def test_auth_failure_surfaces_as_fiscalization_error(patched_client_factory):
    nalogo_mock = _make_mocked_nalogo_client(
        create_responses=[],
        auth_responses=[UnauthorizedException("bad password")],
    )
    patched_client_factory.append(nalogo_mock)
    wrapper = MoyNalogClient(inn="1234567890", password="wrong-pw")

    with pytest.raises(FiscalizationError, match="credentials rejected"):
        await wrapper.register_income(amount=Decimal("100"), description="x")

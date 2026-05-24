"""Singleton wiring for the payments module.

Built once at import time, mirroring ``src/runtime.py``. Handlers and the
``main.py`` entrypoint import ``payment_service`` from here.

This module is also the wiring point between the payments transport layer and
the subscription business-logic chain: it injects
``internal_functions.finalize_successful_payment`` as the
``on_payment_succeeded`` callback. Outside of this file, nothing in
``src.payments`` knows about Remnawave, referrals, admin notifications, FSM,
or keyboards.
"""

from src.config import settings
from src.services import internal_functions

from .enums import PaymentProviderName
from .fiscalization import MoyNalogClient
from .providers.base import PaymentProvider
from .providers.yoomoney import YooMoneyTransferProvider
from .providers.yookassa import YookassaProvider
from .service import PaymentService


# Shared «Мой налог» client (the fiscalizer). Constructed once if the master
# fiscalization flag is on AND credentials are populated; injected into each
# provider whose own fiscalization flag is on. The schema's model_validator
# already enforces that creds exist whenever any provider has fiscalization
# enabled and the master is on, so the assertions below cannot trip in a
# validated-startup path — they're for type-narrowing.
moy_nalog_client: MoyNalogClient | None = None
if settings.payments.fiscalization.enabled:
    if settings.payments.fiscalization.moy_nalog.inn and settings.payments.fiscalization.moy_nalog.password:
        moy_nalog_client = MoyNalogClient(
            inn=settings.payments.fiscalization.moy_nalog.inn,
            password=settings.payments.fiscalization.moy_nalog.password.get_secret_value(),
        )


def _moy_nalog_for(provider_flag: bool) -> MoyNalogClient | None:
    """Return the shared MoyNalogClient only if both global and provider flags are on."""
    if moy_nalog_client is None or not provider_flag:
        return None
    return moy_nalog_client


# Build provider instances based on per-provider enabled flags. YooMoney creates
# its aiohttp.ClientSession lazily inside the running loop. YooKassa sets its
# SDK's module-level config eagerly (safe — just stores credentials, no network
# calls). The provider's UI buttons and webhook routes are conditional on
# membership in this dict.
providers: dict[PaymentProviderName, PaymentProvider] = {}

if settings.payments.yookassa.enabled:
    # type narrows: schema model_validator enforces credentials when enabled
    assert settings.payments.yookassa.shop_id is not None
    assert settings.payments.yookassa.secret_key is not None
    providers[PaymentProviderName.YOOKASSA] = YookassaProvider(
        shop_id=settings.payments.yookassa.shop_id,
        secret_key=settings.payments.yookassa.secret_key.get_secret_value(),
        return_url=settings.payments.return_url,
        moy_nalog=_moy_nalog_for(settings.payments.fiscalization.providers.yookassa),
    )

if settings.payments.yoomoney.enabled:
    assert settings.payments.yoomoney.token is not None
    assert settings.payments.yoomoney.notification_secret is not None
    providers[PaymentProviderName.YOOMONEY] = YooMoneyTransferProvider(
        access_token=settings.payments.yoomoney.token.get_secret_value(),
        notification_secret=settings.payments.yoomoney.notification_secret.get_secret_value(),
        moy_nalog=_moy_nalog_for(settings.payments.fiscalization.providers.yoomoney),
    )

if not providers:
    # Schema-level validator already prevents this, but belt-and-braces:
    # if it slips through, fail loudly rather than starting a useless bot.
    raise RuntimeError(
        "No payment providers enabled — at least one of "
        "payments.yoomoney.enabled / payments.yookassa.enabled must be True",
    )


payment_service = PaymentService(
    providers=providers,
    on_payment_succeeded=internal_functions.finalize_successful_payment,
    test_user_ids=list(settings.payments.test_user_ids),
    test_price=settings.payments.test_price,
)


async def aclose_all_providers() -> None:
    """Close any resources providers and the fiscalizer hold.

    Called from ``main.on_shutdown``.
    """
    import logging
    log = logging.getLogger(__name__)

    for provider in providers.values():
        aclose = getattr(provider, "aclose", None)
        if aclose is not None:
            try:
                await aclose()
            except Exception:
                # Shutdown — log but don't propagate; we're about to exit anyway.
                log.warning("Provider %s aclose failed", provider.name, exc_info=True)

    if moy_nalog_client is not None:
        try:
            await moy_nalog_client.aclose()
        except Exception:
            log.warning("MoyNalogClient aclose failed", exc_info=True)

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
from .providers.base import PaymentProvider
from .providers.yoomoney import YooMoneyTransferProvider
from .providers.yookassa import YookassaProvider
from .service import PaymentService


# Build provider instances. YooMoney creates its aiohttp.ClientSession lazily
# inside the running loop. YooKassa sets its SDK's module-level config eagerly
# (safe — just stores credentials, no network calls).
yoomoney_provider = YooMoneyTransferProvider(
    receiver_account=settings.payments.yoomoney.account,
    access_token=settings.payments.yoomoney.token.get_secret_value(),
    notification_secret=settings.payments.yoomoney.notification_secret.get_secret_value(),
)

yookassa_provider = YookassaProvider(
    shop_id=settings.payments.yookassa.shop_id,
    secret_key=settings.payments.yookassa.secret_key.get_secret_value(),
    return_url=settings.payments.return_url,
)


providers: dict[PaymentProviderName, PaymentProvider] = {
    PaymentProviderName.YOOMONEY: yoomoney_provider,
    PaymentProviderName.YOOKASSA: yookassa_provider,
}


payment_service = PaymentService(
    providers=providers,
    on_payment_succeeded=internal_functions.finalize_successful_payment,
    test_user_ids=list(settings.payments.test_user_ids),
    test_price=settings.payments.test_price,
)


async def aclose_all_providers() -> None:
    """Close any resources providers hold (aiohttp sessions, etc.).

    Called from ``main.on_shutdown``.
    """
    for provider in providers.values():
        aclose = getattr(provider, "aclose", None)
        if aclose is not None:
            try:
                await aclose()
            except Exception:
                # Shutdown — log but don't propagate; we're about to exit anyway.
                import logging
                logging.getLogger(__name__).warning(
                    "Provider %s aclose failed", provider.name, exc_info=True,
                )

"""Payment webhook routes (mounted by :mod:`src.webhook_app`).

Routes:

- ``POST /webhook/payment/{provider}`` — provider-specific webhook receiver.
  The provider must be registered in ``PaymentService.providers`` and have
  ``supports_webhook = True``.

Security: webhooks are accepted only via the local listener (docker-compose
exposes ``127.0.0.1:<port>``); TLS is terminated on the host by an external
reverse-proxy that proxies ``https://<host>/webhook/payment/<provider>`` to
this listener.

Each provider verifies its own signature inside ``parse_webhook``. We never
trust the request body — the provider's parser is the authority.
"""

import logging

from aiohttp import web

from .enums import PaymentProviderName
from .exceptions import InvalidWebhookSignature, ProviderError, ProviderUnavailable


logger = logging.getLogger(__name__)


def register_payment_routes(app: web.Application) -> None:
    """Mount payment webhook routes on the given aiohttp app.

    Expects ``app["payment_service"]`` to be set by the caller (see
    :mod:`src.webhook_app`).
    """
    app.router.add_post("/webhook/payment/{provider}", _handle_payment_webhook)


async def _handle_payment_webhook(request: web.Request) -> web.Response:
    service = request.app["payment_service"]
    provider_str = request.match_info["provider"]

    try:
        provider_name = PaymentProviderName(provider_str)
    except ValueError:
        logger.warning("Webhook received for unknown provider: %r", provider_str)
        return web.Response(status=404)

    try:
        provider = service.get_provider(provider_name)
    except ProviderUnavailable:
        logger.warning("Webhook received for unregistered provider: %s", provider_name)
        return web.Response(status=404)

    if not provider.supports_webhook:
        logger.warning(
            "Webhook received for provider that doesn't support webhooks: %s",
            provider_name,
        )
        return web.Response(status=404)

    body = await request.read()
    try:
        event = await provider.parse_webhook(body=body, headers=request.headers)
    except InvalidWebhookSignature as exc:
        logger.warning("Webhook signature verification failed for %s: %s", provider_name, exc)
        return web.Response(status=400)
    except ProviderError:
        logger.exception("Webhook parse failed for %s — returning 400", provider_name)
        return web.Response(status=400)

    try:
        await service.handle_event(event, provider_name=provider_name)
    except Exception:
        logger.exception(
            "handle_event failed for %s external_id=%s — returning 500 so provider retries",
            provider_name, event.external_id,
        )
        return web.Response(status=500)

    # Important: providers (notably YooMoney) treat anything other than 200 OK as
    # a delivery failure and will retry (immediately, then +10min, then +1h).
    return web.Response(status=200, text="ok")

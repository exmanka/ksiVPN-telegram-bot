"""aiohttp.web application for inbound payment webhooks.

Mounted by :mod:`main` alongside the aiogram polling loop:

    runner = web.AppRunner(build_webhook_app(payment_service))
    await runner.setup()
    site = web.TCPSite(runner, host, port)
    await site.start()

Routes:

- ``POST /webhook/{provider}`` — provider-specific webhook receiver. The
  provider must be registered in ``PaymentService.providers`` and have
  ``supports_webhook = True``.
- ``GET /health`` — liveness probe for the reverse-proxy / orchestrator.

Security: webhooks are accepted only via the local listener (docker-compose
exposes ``127.0.0.1:<port>``); TLS is terminated on the host by an external
reverse-proxy that proxies ``https://payments.<host>/webhook/<provider>`` to
this listener.

Each provider verifies its own signature inside ``parse_webhook``. We never
trust the request body — the provider's parser is the authority.
"""

import logging

from aiohttp import web

from .enums import PaymentProviderName
from .exceptions import InvalidWebhookSignature, ProviderError, ProviderUnavailable
from .service import PaymentService


logger = logging.getLogger(__name__)


def build_webhook_app(service: PaymentService) -> web.Application:
    """Construct the webhook aiohttp app for the given ``PaymentService``."""
    app = web.Application()
    app["payment_service"] = service
    app.router.add_post("/webhook/{provider}", _handle_webhook)
    app.router.add_get("/health", _handle_health)
    return app


async def _handle_health(request: web.Request) -> web.Response:  # noqa: ARG001
    return web.Response(text="ok", status=200)


async def _handle_webhook(request: web.Request) -> web.Response:
    service: PaymentService = request.app["payment_service"]
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

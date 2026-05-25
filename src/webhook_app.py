"""Top-level aiohttp.web app factory for all inbound webhooks.

Composes the payment and Remnawave route groups onto a single ``Application``
mounted by :mod:`main`:

    runner = web.AppRunner(build_webhook_app(payment_service))
    await runner.setup()
    site = web.TCPSite(runner, host, port)
    await site.start()

Routes:

- ``POST /webhook/payment/{provider}`` — payment provider webhooks
  (see :mod:`src.payments.webhook`)
- ``POST /webhook/remnawave`` — Remnawave Panel events (registered only
  when ``settings.remnawave.webhook_secret`` is configured; see
  :mod:`src.services.remnawave_webhook`)
- ``GET  /health`` — liveness probe for the reverse-proxy / orchestrator
"""

from aiohttp import web

from src.payments.service import PaymentService
from src.payments.webhook import register_payment_routes
from src.services.remnawave_webhook import register_remnawave_routes


def build_webhook_app(payment_service: PaymentService) -> web.Application:
    """Construct the aiohttp webhook app with all route groups mounted."""
    app = web.Application()
    app["payment_service"] = payment_service
    register_payment_routes(app)
    register_remnawave_routes(app)
    app.router.add_get("/health", _handle_health)
    return app


async def _handle_health(request: web.Request) -> web.Response:  # noqa: ARG001
    return web.Response(text="ok", status=200)

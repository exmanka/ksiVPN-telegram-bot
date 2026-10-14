"""Inbound webhook receiver for Remnawave Panel events.

Single endpoint ``POST /webhook/remnawave`` accepts all event types the panel
is subscribed to deliver. Dispatch happens by the ``event`` field of the JSON
payload. Supported events: ``torrent_blocker.report`` (emitted by the node's
torrent-blocker plugin, see https://docs.rw/docs/learn/node-plugins/) and
``user.revoked`` (refreshes the cached subscription_url).

Signature verification: HMAC-SHA256 over the raw request body using the
shared secret from ``settings.remnawave.webhook_secret``. We do **not** call
``WebhookPayloadDto.from_dict`` from the Remnawave SDK — its dispatcher does
not cover ``torrent_blocker.*`` events and the corresponding DTO is incomplete
(no ``user``/``report`` fields). We parse the raw JSON dict directly.

The endpoint is only registered if ``webhook_secret`` is configured; without
a secret we cannot authenticate inbound requests, so the safer default is to
reject by 404 (i.e. route not mounted at all).
"""

import json
import logging
import uuid

from aiohttp import web
from remnawave.controllers.webhooks import WebhookUtility

from src.config import settings
from src.database import postgres_dbms
from src.runtime import bot
from src.services.internal_functions import safe_deliver
from src.services import localization as loc


logger = logging.getLogger(__name__)

_SIGNATURE_HEADER = "x-remnawave-signature"


def register_remnawave_routes(app: web.Application) -> None:
    """Mount the Remnawave webhook route on the given aiohttp app.

    No-op when ``settings.remnawave.webhook_secret`` is not configured —
    leaves an INFO log so the operator notices.
    """
    if settings.remnawave.webhook_secret is None:
        logger.info(
            "Remnawave webhook receiver disabled: settings.remnawave.webhook_secret is not set"
        )
        return
    app.router.add_post("/webhook/remnawave", _handle_remnawave_webhook)
    logger.info("Remnawave webhook receiver registered at POST /webhook/remnawave")


async def _handle_remnawave_webhook(request: web.Request) -> web.Response:
    secret = settings.remnawave.webhook_secret.get_secret_value()

    signature = request.headers.get(_SIGNATURE_HEADER)
    if not signature:
        logger.warning("Remnawave webhook rejected: missing %s header", _SIGNATURE_HEADER)
        return web.Response(status=400)

    body_bytes = await request.read()
    try:
        body_str = body_bytes.decode("utf-8")
    except UnicodeDecodeError:
        logger.warning("Remnawave webhook rejected: body is not valid UTF-8")
        return web.Response(status=400)

    if not WebhookUtility.validate_webhook(body=body_str, signature=signature, webhook_secret=secret):
        logger.warning("Remnawave webhook rejected: signature mismatch")
        return web.Response(status=400)

    try:
        payload = json.loads(body_str)
    except json.JSONDecodeError:
        logger.warning("Remnawave webhook rejected: body is not valid JSON")
        return web.Response(status=400)

    event = payload.get("event")
    data = payload.get("data", {})

    if event == "torrent_blocker.report":
        await _handle_torrent_blocker_report(data)
    elif event == "user.revoked":
        await _handle_user_revoked(data)
    else:
        logger.info("Unhandled Remnawave event: %s", event)

    # Always 200 once the signature is verified — non-200 triggers panel retries.
    return web.Response(status=200, text="ok")


async def _handle_torrent_blocker_report(data: dict) -> None:
    """Notify the offending user that their VPN node was blocked for torrent traffic.

    Payload shape (per docs.rw, not fully covered by the Remnawave SDK DTOs):
        data.user.telegramId : int | None
        data.node.name       : str
        data.report.actionReport.blockDuration : int  (seconds)
    """
    try:
        user_block = data.get("user") or {}
        telegram_id = user_block.get("telegramId")
        node_name = data["node"]["name"]
        block_seconds = data["report"]["actionReport"]["blockDuration"]
    except (KeyError, TypeError):
        logger.exception("torrent_blocker.report: malformed payload — keys missing")
        return

    block_minutes = block_seconds // 60

    if telegram_id is None:
        logger.info(
            "torrent_blocker.report on node=%s for block_minutes=%s (raw seconds=%s) — user has no telegramId, skip notify",
            node_name, block_minutes, block_seconds,
        )
        return

    logger.warning(
        "Remnawave torrent_blocker.report: telegram_id=%s node=%s block_minutes=%s",
        telegram_id, node_name, block_minutes,
    )

    text = loc.internal.msgs["torrent_blocker_warning"].format(
        node_name=node_name,
        block_minutes=block_minutes,
    )
    await safe_deliver(
        lambda: bot.send_message(telegram_id, text),
        telegram_id=telegram_id,
    )


async def _handle_user_revoked(data: dict) -> None:
    """Refresh the cached subscription_url after the subscription was revoked in the panel.

    A revoke regenerates the user's shortUuid, so the old subscription_url stops working.
    Payload shape: ``data`` is the panel user (UserDto):
        data.uuid            : str
        data.subscriptionUrl : str
    """
    try:
        remnawave_uuid = uuid.UUID(data["uuid"])
        subscription_url = data["subscriptionUrl"]
    except (KeyError, TypeError, ValueError):
        logger.exception("user.revoked: malformed payload — keys missing or invalid uuid")
        return

    if not await postgres_dbms.update_client_remnawave_subscription_url(remnawave_uuid, subscription_url):
        logger.info("user.revoked for remnawave_uuid=%s — no linked client, skip", remnawave_uuid)
        return

    logger.info("user.revoked: updated subscription_url for remnawave_uuid=%s", remnawave_uuid)

import logging
import logging.handlers
import asyncio
import signal
import os

# Set up logger before imports
if __name__ == '__main__':
    # 'logs/' dir is relative to bot workdir
    os.makedirs('logs', exist_ok=True)
    logging.basicConfig(
        handlers=[
            logging.handlers.RotatingFileHandler(
                'logs/bot.log', maxBytes=10 * 1024 * 1024, backupCount=5, encoding='utf-8'
            ),
            logging.StreamHandler(),
        ],
        level=logging.INFO,
        format='[%(asctime)s: %(levelname)s: %(name)s] %(message)s',
        datefmt='%Y-%m-%d %H:%M:%S',
        encoding='utf-8',
    )
    logging.getLogger('aiogram.event').setLevel(logging.WARNING)

from aiohttp import web

from src.middlewares import user_authorized_mw, user_unauthorized_mw, admin_mw, throttling_mw
from src.handlers import user_authorized, user_unauthorized, admin, other
from src.database import postgres_dbms
from src.services import scheduler
from src.runtime import dp, bot
from src.config import settings
from src.payments.runtime import payment_service, aclose_all_providers
from src.payments.webhook import build_webhook_app


logger = logging.getLogger(__name__)


async def on_startup() -> None:
    """Connect to database and run scheduler during bot launch."""
    await postgres_dbms.asyncpg_run()
    await scheduler.apscheduler_start()
    logger.info('Bot has been successfully launched!')


async def on_shutdown() -> None:
    """Disconnect from database and finish scheduler during bot shutdown."""
    await postgres_dbms.asyncpg_close()
    await scheduler.apscheduler_finish()
    await aclose_all_providers()
    await dp.storage.close()
    await bot.session.close()
    logger.info('Bot has been successfully shut down!')


async def main() -> None:
    # register middlewares (order matters: admin/auth first, then throttling)
    dp.message.middleware(admin_mw.CheckAdmin())
    dp.message.middleware(user_authorized_mw.CheckAuthorized())
    dp.message.middleware(user_unauthorized_mw.CheckUnauthorized())
    dp.message.middleware(throttling_mw.Throttling())

    # register handlers (routers)
    other.register_handlers_global(dp)
    user_authorized.register_handlers_authorized_client(dp)
    user_unauthorized.register_handlers_unauthorized_client(dp)
    admin.register_handlers_admin(dp)
    other.register_handlers_other(dp)

    dp.startup.register(on_startup)
    dp.shutdown.register(on_shutdown)

    loop = asyncio.get_running_loop()
    loop.add_signal_handler(signal.SIGTERM, lambda: signal.raise_signal(signal.SIGINT))

    # Start aiohttp.web for inbound payment webhooks IN PARALLEL with polling.
    # TLS is terminated by an external reverse-proxy on the host; this listener
    # accepts plain HTTP from 127.0.0.1 (see docker-compose port mapping).
    webhook_app = build_webhook_app(payment_service)
    runner = web.AppRunner(webhook_app, access_log=None)
    await runner.setup()
    site = web.TCPSite(
        runner,
        host=settings.webhook.host,
        port=settings.webhook.port,
    )
    await site.start()
    logger.info(
        'Webhook listener started on %s:%d',
        settings.webhook.host, settings.webhook.port,
    )

    try:
        await bot.delete_webhook(drop_pending_updates=True)
        await dp.start_polling(bot, allowed_updates=dp.resolve_used_update_types())
    finally:
        await runner.cleanup()


if __name__ == '__main__':
    asyncio.run(main())

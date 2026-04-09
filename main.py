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

from src.middlewares import user_authorized_mw, user_unauthorized_mw, admin_mw, throttling_mw
from src.handlers import user_authorized, user_unauthorized, admin, other
from src.database import postgres_dbms
from src.services import scheduler
from src.runtime import dp, bot


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

    await bot.delete_webhook(drop_pending_updates=True)
    await dp.start_polling(bot, allowed_updates=dp.resolve_used_update_types())


if __name__ == '__main__':
    asyncio.run(main())

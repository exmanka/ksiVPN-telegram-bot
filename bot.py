import logging
from aiogram.utils import executor
from src.middlewares import admin_mw, user_mw, throttling_mw
from src.handlers import user_authorized, user_unauthorized, admin, other
from src.database import postgres_dbms
from src.services import scheduler
from bot_init import dp


async def on_startup(_):
    """Connect to database and run scheduler during bot launch."""
    await postgres_dbms.asyncpg_run()
    await scheduler.apscheduler_start()
    logger.info('Bot has been successfully launched!')


async def on_shutdown(_):
    """Disconnect from database and finish scheduler during bot shutdown."""
    await postgres_dbms.asyncpg_close()
    await scheduler.apscheduler_finish()
    logger.info('Bot has been successfully shut down!')


def main() -> None:
    # register middlwares
    dp.middleware.setup(admin_mw.CheckAdmin())
    dp.middleware.setup(user_mw.CheckAuthorized())
    dp.middleware.setup(throttling_mw.Throttling())

    # register handlers
    user_authorized.register_handlers_authorized_client(dp)
    user_unauthorized.register_handlers_unauthorized_client(dp)
    admin.register_handlers_admin(dp)
    other.register_handlers_other(dp)

    # launch bot
    executor.start_polling(dp, skip_updates=True, on_startup=on_startup, on_shutdown=on_shutdown)


if __name__ == '__main__':
    # add logging
    logging.basicConfig(filename='bot.log',
                        level=logging.INFO,
                        format='[%(asctime)s: %(levelname)s: %(name)s] %(message)s',
                        datefmt='%Y-%m-%d %H:%M:%S',
                        encoding='utf-8')
    logger = logging.getLogger(__name__)
    main()

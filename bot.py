from aiogram.utils import executor
from src.middlewares import admin_mw, user_mw, throttling_mw
from src.handlers import user_authorized, user_unauthorized, admin, other
from src.database import postgesql_db
from src.services import scheduler
from bot_init import dp


async def on_startup(_):
    """Connect to database and run scheduler during bot launch."""
    await postgesql_db.asyncpg_run()
    await scheduler.apscheduler_start()
    print('Bot has been successfully launched!')


async def on_shutdown(_):
    """Disconnect from database and finish scheduler during bot shutdown."""
    print()
    await postgesql_db.asyncpg_close()
    await scheduler.apscheduler_finish()
    print('Bot has been successfully shut down!')


if __name__ == '__main__':
    # registration of middlwares
    dp.middleware.setup(admin_mw.CheckAdmin())
    dp.middleware.setup(user_mw.CheckAuthorized())
    dp.middleware.setup(throttling_mw.Throttling())

    # registration of handlers
    user_authorized.register_handlers_authorized_client(dp)
    user_unauthorized.register_handlers_unauthorized_client(dp)
    admin.register_handlers_admin(dp)
    other.register_handlers_other(dp)

    # bot launch
    executor.start_polling(dp, skip_updates=True, on_startup=on_startup, on_shutdown=on_shutdown)

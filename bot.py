from aiogram.utils import executor
from bot_init import dp
from src.handlers import user_authorized, user_unauthorized
from src.database import postgesql_db
from src.handlers import admin, other
from src.middlewares import admin_mw, user_mw
from src.services import scheduler
from apscheduler.schedulers.asyncio import AsyncIOScheduler

async def on_startup(_):
    postgesql_db.sql_start()
    print('DB has been successfully launched!')

    await scheduler.scheduler_start()
    print('Scheluler has been successfully launched!')
    print('Bot has been successfully launched!')



async def on_shutdown(_): # ФУНКЦИЯ ПОКА НЕ ДОБАВЛЕНА В executor!
    postgesql_db.cur.close()
    postgesql_db.base.close()


if __name__ == '__main__':
    # Регистрация хэндлеров
    dp.middleware.setup(admin_mw.CheckAdmin())
    dp.middleware.setup(user_mw.CheckAuthorized())
    dp.middleware.setup(user_mw.Throttling())
    user_authorized.register_handlers_authorized_client(dp)
    user_unauthorized.register_handlers_unauthorized_client(dp)
    admin.register_handlers_admin(dp)
    other.register_handlers_other(dp)

    # Запуск бота. Флаг skip_updates отвечает за пропуск апдейтов, произошедших в то время, пока бот был не в сети.
    # Параметр on_startup принимает ссылку на функцию, которая будет исполнятся при запуске
    executor.start_polling(dp, skip_updates=True, on_startup=on_startup)

import os
import logging
from aiogram import Bot
from aiogram.dispatcher import Dispatcher
from aiogram.contrib.fsm_storage.redis import RedisStorage2


logger = logging.getLogger(__name__)


BOT_TOKEN = os.getenv('BOT_TOKEN')
PROXY_URL = os.getenv('PROXY_URL')
POSTGRES_USER = os.getenv('POSTGRES_USER')
POSTGRES_PASSWORD = os.getenv('POSTGRES_PASSWORD')
POSTGRES_DB = os.getenv('POSTGRES_DB')
REDIS_HOST = os.getenv("REDIS_HOST")
REDIS_PORT = int(os.getenv("REDIS_PORT"))
REDIS_DB = int(os.getenv("REDIS_DB"))
REDIS_PASSWORD = os.getenv("REDIS_PASSWORD")
FSM_PREFIX = os.getenv("FSM_PREFIX")
ADMIN_ID = int(os.getenv('ADMIN_ID'))
YOOMONEY_TOKEN = os.getenv('YOOMONEY_TOKEN')
YOOMONEY_ACCOUNT_NUMBER = os.getenv('YOOMONEY_ACCOUNT_NUMBER')
BACKUP_PATH = os.getenv('BACKUP_PATH')
LOCALIZATION_LANGUAGE = os.getenv('LOCALIZATION_LANGUAGE')
TIMEZONE = os.getenv('TZ')


if PROXY_URL:
    bot = Bot(token=BOT_TOKEN, proxy=PROXY_URL)
    logger.info(f"Bot starts using SOCKS5 proxy")
else:
    bot = Bot(BOT_TOKEN)
    logger.debug(f"Bot starts in normal mode without SOCKS5 proxy")

storage = RedisStorage2(
    host=REDIS_HOST,
    port=REDIS_PORT,
    db=REDIS_DB,
    password=REDIS_PASSWORD,
    prefix=FSM_PREFIX,
)
dp = Dispatcher(bot, storage=storage)

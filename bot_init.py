import os
import logging
from aiogram import Bot, Dispatcher
from aiogram.client.default import DefaultBotProperties
from aiogram.client.session.aiohttp import AiohttpSession
from aiogram.enums import ParseMode
from aiogram.fsm.storage.redis import RedisStorage, DefaultKeyBuilder
from redis.asyncio import Redis


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


_default_props = DefaultBotProperties(parse_mode=ParseMode.HTML)

if PROXY_URL:
    bot = Bot(token=BOT_TOKEN, default=_default_props, session=AiohttpSession(proxy=PROXY_URL))
    logger.info("Bot starts using SOCKS5 proxy")
else:
    bot = Bot(token=BOT_TOKEN, default=_default_props)
    logger.debug("Bot starts in normal mode without SOCKS5 proxy")

_redis = Redis(
    host=REDIS_HOST,
    port=REDIS_PORT,
    db=REDIS_DB,
    password=REDIS_PASSWORD,
)
storage = RedisStorage(redis=_redis, key_builder=DefaultKeyBuilder(prefix=FSM_PREFIX))
dp = Dispatcher(storage=storage)

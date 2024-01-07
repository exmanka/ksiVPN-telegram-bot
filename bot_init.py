import os
from aiogram import Bot
from aiogram.dispatcher import Dispatcher
from aiogram.contrib.fsm_storage.memory import MemoryStorage


storage = MemoryStorage()
bot = Bot(token=os.getenv('BOT_TOKEN'))
dp = Dispatcher(bot, storage=storage)
POSTGRES_USER = os.getenv('POSTGRES_USER')
POSTGRES_PASSWORD = os.getenv('POSTGRES_PASSWORD')
POSTGRES_DB = os.getenv('POSTGRES_DB')
ADMIN_ID = int(os.getenv('ADMIN_ID'))
YOOMONEY_TOKEN = os.getenv('YOOMONEY_TOKEN')
YOOMONEY_ACCOUNT_NUMBER = os.getenv('YOOMONEY_ACCOUNT_NUMBER')
BACKUP_PATH_NAME = os.getenv('BACKUP_PATH_NAME')
LOCALIZATION_LANGUAGE = os.getenv('LOCALIZATION_LANGUAGE')

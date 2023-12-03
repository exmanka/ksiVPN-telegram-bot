# bot_init - вспомогательный файл, необходимый для грамотной передачи объектов классов между различными файлами.
from aiogram import Bot
from aiogram.dispatcher import Dispatcher
import os
from aiogram.contrib.fsm_storage.memory import MemoryStorage    # Класс позволяет хранить данные в оперативной памяти.

storage = MemoryStorage()
bot = Bot(token=os.getenv('TOKEN'))     # Инициализация бота
dp = Dispatcher(bot, storage=storage)   # Инициализация диспетчера
admin_ID = int(os.getenv('ADMIN_ID'))
postgres_PW = os.getenv('POSTGRES_PW')
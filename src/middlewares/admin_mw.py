from bot_init import ADMIN_ID
from aiogram import types
from aiogram.dispatcher.middlewares import BaseMiddleware
from aiogram.dispatcher.handler import CancelHandler, current_handler


def admin_only():
    def wrapper(func):
        setattr(func, 'admin_only', True)

        return func
    
    return wrapper


class CheckAdmin(BaseMiddleware):
    async def on_process_message(self, message: types.Message, data: dict):
        handler = current_handler.get()
        if handler:
            only_for_admin = getattr(handler, 'admin_only', False)
            if only_for_admin and not message.from_user.id == ADMIN_ID:
                await message.answer('Ууупс! Эта функция доступна только администратору \U0001F47E')
                raise CancelHandler()


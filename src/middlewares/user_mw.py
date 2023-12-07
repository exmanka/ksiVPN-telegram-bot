from aiogram import types
from aiogram.dispatcher.middlewares import BaseMiddleware
from aiogram.dispatcher.handler import CancelHandler, current_handler
from src.database.postgesql_db import is_user_registered


def unauthorized_only():
    def wrapper(func):
        setattr(func, 'unauthorized_only', True)

        return func
    return wrapper

def authorized_only():
    def wrapper(func):
        setattr(func, 'authorized_only', True)

        return func
    return wrapper


class CheckAuthorized(BaseMiddleware):
    async def on_process_message(self, message: types.Message, data: dict):
        if handler := current_handler.get():
            only_for_unauthorized_users = getattr(handler, 'unauthorized_only', False)
            if only_for_unauthorized_users and is_user_registered(message.from_user.id):
                await message.answer('Вы уже зарегистрировались!')
                raise CancelHandler()
            
            only_for_authorized_users = getattr(handler, 'authorized_only', False)
            if only_for_authorized_users and not is_user_registered(message.from_user.id):
                await message.answer('Ууупс! Эта функция доступна только зарегистрированным пользователям!')
                raise CancelHandler()


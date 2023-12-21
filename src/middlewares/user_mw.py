from aiogram import types
from aiogram.dispatcher.middlewares import BaseMiddleware
from aiogram.dispatcher.handler import CancelHandler, current_handler
from aiogram.utils.exceptions import Throttled
from src.database.postgesql_db import is_user_registered
from bot_init import dp


def unauthorized_only():
    """Decorator for handlers available only for unauthorized users."""
    def wrapper(func):
        setattr(func, 'unauthorized_only', True)

        return func
    return wrapper


def authorized_only():
    """Decorator for handlers available only for authorized clients."""
    def wrapper(func):
        setattr(func, 'authorized_only', True)

        return func
    return wrapper


def antiflood(rate_limit: int):
    """Decorator for handlers with antiflood."""
    def wrapper(func):
        setattr(func, 'antiflood', True)
        setattr(func, 'rate_limit', rate_limit)

        return func
    return wrapper


class CheckAuthorized(BaseMiddleware):
    async def on_process_message(self, message: types.Message, data: dict):
        if handler := current_handler.get():
            only_for_unauthorized_users = getattr(
                handler, 'unauthorized_only', False)
            if only_for_unauthorized_users and await is_user_registered(message.from_user.id):
                await message.answer('Вы уже зарегистрировались!')
                raise CancelHandler()

            only_for_authorized_users = getattr(
                handler, 'authorized_only', False)
            if only_for_authorized_users and not await is_user_registered(message.from_user.id):
                await message.answer('Ууупс! Эта функция доступна только зарегистрированным пользователям!')
                raise CancelHandler()


class Throttling(BaseMiddleware):
    async def on_process_message(self, message: types.Message, data: dict):
        handler = current_handler.get()
        if handler and getattr(handler, 'antiflood', False):
            try:
                rate_limit = getattr(handler, 'rate_limit', 2)
                await dp.throttle(key='antiflood_message', rate=rate_limit)
            except Throttled as _t:
                await message.answer('Егор (тестировщик), пожалуйста, не спамь запросами!')
                raise CancelHandler()

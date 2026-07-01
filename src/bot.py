import logging

from aiogram import Bot
from aiogram.client.default import DefaultBotProperties
from aiogram.client.session.aiohttp import AiohttpSession
from aiogram.enums import ParseMode

from src.config.schema import Settings
from src.middlewares.retry_mw import RetryRequestMiddleware


logger = logging.getLogger(__name__)


def build_bot(settings: Settings) -> Bot:
    """Construct the aiogram Bot, wiring proxy session if enabled."""
    default_props = DefaultBotProperties(parse_mode=ParseMode.HTML)
    token = settings.bot.token.get_secret_value()

    if settings.proxy.enabled and settings.proxy.url:
        logger.info("Bot starts using SOCKS5 proxy")
        session = AiohttpSession(proxy=settings.proxy.url)
    else:
        logger.info("Bot starts in normal mode without SOCKS5 proxy")
        session = AiohttpSession()

    session.middleware.register(
        RetryRequestMiddleware(
            retries=settings.network.retries,
            retry_delay=settings.network.retry_delay,
        )
    )

    return Bot(token=token, default=default_props, session=session)

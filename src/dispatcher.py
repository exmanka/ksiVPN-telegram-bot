from aiogram import Dispatcher
from aiogram.fsm.storage.redis import DefaultKeyBuilder, RedisStorage
from redis.asyncio import Redis

from src.config.schema import Settings


def build_dispatcher(settings: Settings) -> Dispatcher:
    """Construct the Dispatcher with Redis-backed FSM storage."""
    redis_cfg = settings.connections.redis
    redis = Redis(
        host=redis_cfg.host,
        port=redis_cfg.port,
        db=redis_cfg.db,
        password=redis_cfg.password.get_secret_value(),
    )
    storage = RedisStorage(
        redis=redis,
        key_builder=DefaultKeyBuilder(prefix=redis_cfg.fsm_prefix),
    )
    return Dispatcher(storage=storage)

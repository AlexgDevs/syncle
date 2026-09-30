import logging

from redis.asyncio import Redis, from_url
from redis.exceptions import AuthenticationError, ConnectionError

from src.core.settings import get_settings

logger = logging.getLogger(__name__)

_client: Redis | None = None


def get_redis() -> Redis:
    """Process-wide client created by `init_redis` (worker startup / bot run)."""
    if _client is None:
        raise RuntimeError("Redis is not initialized; call init_redis() first")
    return _client


async def init_redis() -> Redis:
    global _client
    cfg = get_settings()
    try:
        client = from_url(
            cfg.REDIS_URL,
            encoding="utf-8",
            decode_responses=True,
            max_connections=cfg.REDIS_MAX_CONNECTIONS,
            socket_timeout=cfg.REDIS_SOCKET_TIMEOUT,
            socket_connect_timeout=cfg.REDIS_SOCKET_CONNECT_TIMEOUT,
            retry_on_timeout=cfg.REDIS_RETRY_ON_TIMEOUT,
        )

        await client.ping()
        _client = client
        return client

    except AuthenticationError:
        logger.error(
            "Failed to authenticate with Redis. Please check your credentials."
        )
        raise
    except ConnectionError:
        logger.error(
            "Failed to connect to Redis. Please check if the Redis server is "
            "running and accessible."
        )
        raise
    except Exception:
        logger.error(
            "An unexpected error occurred while initializing Redis.", exc_info=True
        )
        raise


async def close_redis(client: Redis) -> None:
    global _client
    await client.aclose()
    if _client is client:
        _client = None

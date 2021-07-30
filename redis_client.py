import sys
import redis
from datetime import timedelta


def redis_connect() -> redis.client.Redis:
    try:
        client = redis.Redis(
            host="localhost",
            port=6379,
            db=0,
            socket_timeout=5,
            decode_responses=True
        )
        ping = client.ping()
        if ping is True:
            return client
    except redis.AuthenticationError:
        print("AuthenticationError")
        sys.exit(1)


client = redis_connect()


def get_from_cache(key: str) -> str:
    """Data from redis."""

    val = client.get(f'ram_{key}')
    return val


def set_to_cache(key: str, value: str) -> bool:
    """Data to redis."""

    state = client.setex(f'ram_{key}', timedelta(seconds=3600), value=value, )
    return state


def delete_key(key: str) -> bool:
    """Delete key."""

    list_keys = client.keys(f'ram_{key}')
    state = False
    for key in list_keys:
        state = client.delete(key)
    return state

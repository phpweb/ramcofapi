from functools import lru_cache
from pydantic import BaseSettings


class Settings(BaseSettings):
    api_key: str
    api_secret: str
    hook_secret: str

    class Config:
        env_file = ".env"


@lru_cache()
def get_settings():
    return Settings()

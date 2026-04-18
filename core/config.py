from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    playwright_timeout: int = 30000
    headless: bool = True

    class Config:
        env_file = ".env"


settings = Settings()
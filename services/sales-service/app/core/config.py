from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    app_name: str = "StockSync"
    app_version: str = "0.1.0"
    debug: bool = False

    class Config:
        env_file = ".env"


settings = Settings()

from pydantic_settings import BaseSettings, SettingsConfigDict

class Config(BaseSettings):
    JAVA_PATH:  str
    MIN_RAM:  str
    MAX_RAM: str
    Forge_Version: str
    BACKUP_INTERVAL: int
    MAX_BACKUPS: int


    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8")


config = Config()
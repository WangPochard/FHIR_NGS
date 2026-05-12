from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    # Server
    host: str = "0.0.0.0"
    port: int = 8000
    log_level: str = "INFO"
    log_retention_days: int = 90

    # HAPI FHIR
    hapi_fhir_url: str = "http://localhost:8080/fhir"

    # Database
    db_url: str = "postgresql+asyncpg://fhir:fhir@localhost:5432/fhir_ngs"

    # App metadata
    app_title: str = "FHIR NGS Converter"
    app_version: str = "0.1.0"
    app_description: str = (
        "將 NGS（次世代定序）報告（VCF / PDF）轉換為 HL7 FHIR R4 transaction Bundle，"
        "供 HAPI FHIR Server 儲存與查詢。"
    )


@lru_cache
def get_settings() -> Settings:
    return Settings()

"""Configuration for the product-intel pipeline."""

from __future__ import annotations

from functools import lru_cache
from pathlib import Path
from typing import Literal

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    app_name: str = "Amazon Product Intel Agent"
    app_version: str = "0.2.0"

    llm_mode: Literal["mock", "real"] = "mock"
    llm_base_url: str = ""
    llm_api_key: str = ""
    llm_model: str = ""

    db_path: Path = Path("data/runtime/product_intel.db")
    report_dir: Path = Path("reports")
    excel_path: Path = Path("data/source/amazon_products.xlsx")
    excel_out: Path = Path("data/exports/amazon_products.xlsx")
    raw_dir: Path = Path("data/raw")

    amazon_source: Literal["replay", "live"] = "replay"
    amazon_marketplace: str = "amazon.com"
    amazon_timeout: float = 30.0
    amazon_retries: int = 1
    amazon_delay: float = 6.0
    amazon_proxy: str = ""
    amazon_headless: bool = True
    amazon_user_agent: str = ""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    return Settings()

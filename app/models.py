"""Pydantic models shared by the pipeline."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field


class Product(BaseModel):
    product_id: str
    name: str
    category: str
    url: str
    marketplace: str = "amazon.com"
    excel_sheet: str = ""

    model_config = ConfigDict(extra="ignore")

    @property
    def asin(self) -> str:
        return self.product_id


class ParsedProduct(BaseModel):
    title: str
    price_text: str | None = None
    list_price_text: str | None = None
    rating_text: str | None = None
    reviews_text: str | None = None
    sales_text: str | None = None
    bullets: list[str] = Field(default_factory=list)
    description: str | None = None
    main_image: str | None = None
    gallery_images: list[str] = Field(default_factory=list)
    availability: str | None = None
    seller: str | None = None
    coupon: str | None = None
    canonical_url: str | None = None
    selector_hits: dict[str, str] = Field(default_factory=dict)


class Snapshot(BaseModel):
    product_id: str
    snapshot_date: str
    title: str
    price: float | None
    list_price: float | None = None
    currency: str | None
    rating: float | None
    reviews: int | None
    sales_value: int | None
    sales_text: str | None
    bullets: list[str] = Field(default_factory=list)
    description: str | None = None
    main_image: str | None = None
    gallery_images: list[str] = Field(default_factory=list)
    in_stock: bool | None = None
    availability: str | None = None
    seller: str | None = None
    coupon: str | None = None
    data_gaps: list[str] = Field(default_factory=list)
    raw_html_path: str | None = None
    selector_hits: dict[str, str] = Field(default_factory=dict)

    model_config = ConfigDict(extra="ignore")


class ProductAnalysis(BaseModel):
    product_id: str
    snapshot_date: str
    title: str
    summary: str
    price_trend: str
    sales_trend: str
    key_changes: list[str] = Field(default_factory=list)
    actions: list[str] = Field(default_factory=list)
    confidence: Literal["high", "medium", "low"]
    data_gaps: list[str] = Field(default_factory=list)

    model_config = ConfigDict(extra="ignore")


@dataclass
class RunLog:
    run_id: str
    snapshot_date: str
    started_at: str
    duration_ms: float
    total: int
    success: int
    skipped: int
    failed: int
    source_mode: str = "replay"
    blocked: int = 0
    cache_hits: int = 0
    details: list[dict[str, Any]] = field(default_factory=list)

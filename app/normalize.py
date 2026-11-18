"""Normalize raw Amazon page text into comparable fields."""

from __future__ import annotations

import re
from typing import Any

from app.images import clean_url, dedupe_images
from app.models import ParsedProduct, Product, Snapshot

PRICE_RE = re.compile(r"([0-9][0-9,]*(?:\.[0-9]+)?)")
RATING_RE = re.compile(r"([0-9]+(?:\.[0-9]+)?)")
SALES_RE = re.compile(
    r"([0-9][0-9,]*(?:\.[0-9]+)?)\s*([KkMm])?\+?\s*(?:bought|(?:人)?购买)",
    re.IGNORECASE,
)
SALES_K_RE = re.compile(r"([0-9]+(?:\.[0-9]+)?)\s*[KkMm]\+")
SALES_INT_RE = re.compile(r"([0-9][0-9,]*)\s*\+")

BULLET_NOISE = (
    "make sure this fits",
    "see more product details",
    "show more",
    "show less",
)


def parse_price(text: str | None) -> tuple[float | None, str | None]:
    if not text:
        return None, None

    currency = None
    lowered = text.upper()
    if "US$" in lowered or "USD" in lowered or "$" in text:
        currency = "$"
    elif "¥" in text or "￥" in text or "CNY" in lowered:
        currency = "¥"
    elif "€" in text or "EUR" in lowered:
        currency = "€"
    elif "£" in text or "GBP" in lowered:
        currency = "£"

    match = PRICE_RE.search(text)
    if not match:
        return None, currency
    try:
        return float(match.group(1).replace(",", "")), currency
    except ValueError:
        return None, currency


def parse_rating(text: str | None) -> float | None:
    if not text:
        return None
    match = RATING_RE.search(text)
    if not match:
        return None
    try:
        value = float(match.group(1))
    except ValueError:
        return None
    return value if 0 <= value <= 5 else None


def parse_reviews(text: str | None) -> int | None:
    if not text:
        return None
    digits = re.sub(r"[^0-9]", "", text)
    return int(digits) if digits else None


def parse_sales(text: str | None) -> tuple[int | None, str | None]:
    if not text:
        return None, None

    match = SALES_RE.search(text)
    if match:
        value = float(match.group(1).replace(",", ""))
        unit = (match.group(2) or "").lower()
        if unit == "k":
            value *= 1000
        elif unit == "m":
            value *= 1_000_000
        amount = int(round(value))
    else:
        match = SALES_K_RE.search(text)
        if match:
            amount = int(float(match.group(1)) * 1000)
        else:
            match = SALES_INT_RE.search(text)
            amount = int(match.group(1).replace(",", "")) if match else None

    if amount is None:
        return None, None

    normalized = f"{amount / 1000:g}K+" if amount >= 1000 else f"{amount}+"
    return amount, normalized


def parse_availability(text: str | None) -> bool | None:
    if not text:
        return None
    lowered = text.lower()
    if "unavailable" in lowered or "out of stock" in lowered or "not available" in lowered:
        return False
    if "in stock" in lowered or "available" in lowered:
        return True
    return None


def _clean_bullets(bullets: list[str]) -> list[str]:
    result: list[str] = []
    for bullet in bullets:
        text = re.sub(r"\s+", " ", bullet).strip()
        if not text:
            continue
        if any(text.lower().startswith(noise) for noise in BULLET_NOISE):
            continue
        if text in result:
            continue
        result.append(text)
    return result


def _clean_description(text: str | None) -> str | None:
    if not text:
        return None
    cleaned = re.sub(r"[ \t]+", " ", text)
    cleaned = re.sub(r"\n\s*\n+", "\n", cleaned).strip()
    return cleaned or None


def _product_value(product: Product | dict[str, Any], key: str, default: Any = None) -> Any:
    if isinstance(product, Product):
        return getattr(product, key, default)
    return product.get(key, default)


def build_snapshot(
    product: Product | dict[str, Any],
    snapshot_date: str,
    parsed: ParsedProduct,
    raw_html_path: str | None = None,
) -> Snapshot:
    price, currency = parse_price(parsed.price_text)
    list_price, _ = parse_price(parsed.list_price_text)
    if currency is None and price is not None:
        currency = "$"

    rating = parse_rating(parsed.rating_text)
    reviews = parse_reviews(parsed.reviews_text)
    sales_value, sales_normalized = parse_sales(parsed.sales_text)
    sales_text = parsed.sales_text or sales_normalized
    bullets = _clean_bullets(parsed.bullets)
    description = _clean_description(parsed.description)
    main_image = clean_url(parsed.main_image)
    gallery = dedupe_images(parsed.gallery_images)

    gaps: list[str] = []
    if price is None:
        gaps.append("价格")
    if sales_value is None:
        gaps.append("预计销量")
    if rating is None:
        gaps.append("星级")
    if reviews is None:
        gaps.append("评价数")
    if not bullets:
        gaps.append("产品简介")
    if not description:
        gaps.append("产品描述")
    if not main_image:
        gaps.append("主图")
    if not gallery:
        gaps.append("详情图")

    return Snapshot(
        product_id=str(_product_value(product, "product_id", "")),
        snapshot_date=snapshot_date,
        title=parsed.title,
        price=price,
        list_price=list_price,
        currency=currency,
        rating=rating,
        reviews=reviews,
        sales_value=sales_value,
        sales_text=sales_text,
        bullets=bullets,
        description=description,
        main_image=main_image,
        gallery_images=gallery,
        in_stock=parse_availability(parsed.availability),
        availability=parsed.availability,
        seller=parsed.seller,
        coupon=parsed.coupon,
        data_gaps=gaps,
        raw_html_path=raw_html_path,
        selector_hits=parsed.selector_hits,
    )

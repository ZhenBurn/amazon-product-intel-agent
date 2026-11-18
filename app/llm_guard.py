"""Numeric grounding for LLM analysis output.

The LLM may organize language, but it must not introduce numbers that cannot be
traced to the current snapshot, history, or a deterministic delta.
"""

from __future__ import annotations

import math
import re
from dataclasses import dataclass
from typing import Any

from app.models import ProductAnalysis, Snapshot

NUMBER_RE = re.compile(
    r"(?<![\w.])"
    r"(?P<sign>[+-])?"
    r"\s*(?P<currency>US\$|\$|¥|￥|€|£)?"
    r"\s*(?P<number>\d[\d,]*(?:\.\d+)?)"
    r"\s*(?P<unit>[KkMm](?=\+|(?:\s|$|[),.;])))?"
    r"\s*(?P<percent>%)?"
    r"\s*\+?"
)
TEXT_FIELDS = ("summary", "price_trend", "sales_trend", "key_changes", "actions")
COMMON_VALUES = {0.0, 1.0, 5.0}
COMMON_PERCENTAGES = {0.0}


@dataclass(frozen=True)
class NumberToken:
    raw: str
    value: float
    is_percent: bool


@dataclass(frozen=True)
class GroundingResult:
    ok: bool
    violations: list[str]
    checked: int


def _token_value(match: re.Match[str]) -> float:
    value = float(match.group("number").replace(",", ""))
    unit = (match.group("unit") or "").lower()
    if unit == "k":
        value *= 1_000
    elif unit == "m":
        value *= 1_000_000
    if match.group("sign") == "-":
        value = -value
    return value


def extract_numbers(text: str | None) -> list[NumberToken]:
    if not text:
        return []
    tokens: list[NumberToken] = []
    for match in NUMBER_RE.finditer(text):
        tokens.append(
            NumberToken(
                raw=match.group(0).strip(),
                value=_token_value(match),
                is_percent=bool(match.group("percent")),
            )
        )
    return tokens


def _add_text_values(values: set[float], text: str | None) -> None:
    for token in extract_numbers(text):
        if not token.is_percent:
            values.add(token.value)


def _snapshot_texts(snapshot: Snapshot) -> list[str | None]:
    return [
        snapshot.title,
        snapshot.sales_text,
        snapshot.description,
        snapshot.availability,
        snapshot.seller,
        snapshot.coupon,
        snapshot.snapshot_date,
        *snapshot.bullets,
    ]


def _pct(current: float, previous: float) -> float:
    if previous == 0:
        return 0.0
    return (current - previous) / previous * 100


def _price_values(
    values: set[float],
    percentages: set[float],
    current: Snapshot,
    previous: Snapshot | None,
) -> None:
    for snapshot in (current, previous):
        if snapshot is None:
            continue
        for value in (snapshot.price, snapshot.list_price):
            if value is None:
                continue
            values.add(float(value))
            values.add(float(round(value)))
            values.add(float(round(value, 1)))
    if previous is None or current.price is None or previous.price is None:
        return
    pct = _pct(current.price, previous.price)
    percentages.update({pct, abs(pct), round(pct, 1), round(abs(pct), 1)})
    delta = current.price - previous.price
    values.update({delta, abs(delta), round(delta, 1), round(abs(delta), 1)})


def _sales_values(
    values: set[float],
    percentages: set[float],
    current: Snapshot,
    previous: Snapshot | None,
) -> None:
    for snapshot in (current, previous):
        if snapshot is None:
            continue
        if snapshot.sales_value is not None:
            values.add(float(snapshot.sales_value))
    if (
        previous is None
        or current.sales_value is None
        or previous.sales_value is None
    ):
        return
    pct = _pct(float(current.sales_value), float(previous.sales_value))
    percentages.update({pct, abs(pct), round(pct, 1), round(abs(pct), 1)})
    delta = current.sales_value - previous.sales_value
    values.update({float(delta), float(abs(delta))})


def _review_rating_values(
    values: set[float],
    current: Snapshot,
    previous: Snapshot | None,
) -> None:
    for snapshot in (current, previous):
        if snapshot is None:
            continue
        if snapshot.reviews is not None:
            values.add(float(snapshot.reviews))
            values.add(float(round(snapshot.reviews, -1)))
        if snapshot.rating is not None:
            values.add(float(snapshot.rating))
            values.add(float(round(snapshot.rating)))
            values.add(float(round(snapshot.rating, 1)))
    if previous is None:
        return
    if current.reviews is not None and previous.reviews is not None:
        delta = current.reviews - previous.reviews
        values.update({float(delta), float(abs(delta))})
    if current.rating is not None and previous.rating is not None:
        delta = current.rating - previous.rating
        values.update({float(delta), float(abs(delta)), round(delta, 1), round(abs(delta), 1)})


def allowed_numbers(
    current: Snapshot,
    history: list[Snapshot],
    product: dict[str, Any] | None = None,
) -> tuple[set[float], set[float]]:
    values: set[float] = set(COMMON_VALUES)
    percentages: set[float] = set(COMMON_PERCENTAGES)
    previous = history[-2] if len(history) >= 2 else None

    for snapshot in [*history, current]:
        for text in _snapshot_texts(snapshot):
            _add_text_values(values, text)
        if snapshot.data_gaps:
            _add_text_values(values, "、".join(snapshot.data_gaps))
        if snapshot.price is not None:
            values.add(float(snapshot.price))
            values.add(float(round(snapshot.price)))
            values.add(float(round(snapshot.price, 1)))
        if snapshot.list_price is not None:
            values.add(float(snapshot.list_price))
            values.add(float(round(snapshot.list_price)))
            values.add(float(round(snapshot.list_price, 1)))
        if snapshot.rating is not None:
            values.add(float(snapshot.rating))
            values.add(float(round(snapshot.rating)))
        if snapshot.reviews is not None:
            values.add(float(snapshot.reviews))
            values.add(float(round(snapshot.reviews, -1)))
        if snapshot.sales_value is not None:
            values.add(float(snapshot.sales_value))

    if product:
        for key in ("name", "category"):
            _add_text_values(values, str(product.get(key, "")))

    _price_values(values, percentages, current, previous)
    _sales_values(values, percentages, current, previous)
    _review_rating_values(values, current, previous)

    values.update(
        {
            float(len(history)),
            float(max(0, len(history) - 1)),
            float(len(current.bullets)),
            float(len(current.gallery_images)),
            float(len(current.data_gaps)),
        }
    )
    return values, percentages


def _matches(value: float, allowed: set[float]) -> bool:
    return any(
        math.isclose(value, candidate, rel_tol=0.02, abs_tol=0.11)
        for candidate in allowed
    )


def validate_analysis(
    analysis: ProductAnalysis,
    current: Snapshot,
    history: list[Snapshot],
    product: dict[str, Any] | None = None,
) -> GroundingResult:
    values, percentages = allowed_numbers(current, history, product)
    violations: list[str] = []
    checked = 0

    for field in TEXT_FIELDS:
        value = getattr(analysis, field)
        texts = value if isinstance(value, list) else [value]
        for text in texts:
            for token in extract_numbers(str(text)):
                checked += 1
                allowed = percentages if token.is_percent else values
                if not _matches(token.value, allowed):
                    violations.append(f"{field}:{token.raw}")

    unique = list(dict.fromkeys(violations))
    return GroundingResult(ok=not unique, violations=unique, checked=checked)

"""Deterministic business signals derived from snapshot history."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

from app.models import Snapshot

Severity = Literal["high", "medium", "low"]
SEVERITY_ORDER = {"high": 0, "medium": 1, "low": 2}
SIGNAL_ORDER = {
    "seller_change": 0,
    "stock_out": 1,
    "price_change": 2,
    "rating_drop": 3,
    "price_gap": 4,
    "sales_gap": 5,
    "sales_change": 6,
    "review_growth": 7,
    "review_drop": 8,
    "data_gaps": 9,
    "history": 10,
}


@dataclass(frozen=True)
class Signal:
    kind: str
    severity: Severity
    text: str
    evidence: str

    @property
    def severity_label(self) -> str:
        return {"high": "高", "medium": "中", "low": "低"}[self.severity]


def _pct(current: float, previous: float) -> float:
    if previous == 0:
        return 0.0
    return (current - previous) / previous * 100


def _price(current: Snapshot, previous: Snapshot | None) -> list[Signal]:
    if current.price is None:
        return [
            Signal(
                kind="price_gap",
                severity="medium",
                text="价格缺失，需要美国代理或官方数据源补全。",
                evidence="data_gaps 包含“价格”",
            )
        ]
    if previous is None or previous.price is None:
        return []
    change = _pct(current.price, previous.price)
    if abs(change) < 5:
        return []
    direction = "上升" if change > 0 else "下降"
    severity: Severity = "high" if abs(change) >= 10 else "medium"
    return [
        Signal(
            kind="price_change",
            severity=severity,
            text=f"价格较上次{direction} {abs(change):.1f}%。",
            evidence=(
                f"{previous.currency or ''}{previous.price:,.2f} → "
                f"{current.currency or ''}{current.price:,.2f}"
            ),
        )
    ]


def _seller(current: Snapshot, previous: Snapshot | None) -> list[Signal]:
    current_seller = (current.seller or "").strip()
    previous_seller = (previous.seller or "").strip() if previous else ""
    if not current_seller:
        return []
    if current_seller == previous_seller:
        return []
    third_party = "amazon" not in current_seller.lower()
    return [
        Signal(
            kind="seller_change",
            severity="high" if third_party else "medium",
            text=(
                "出现第三方卖家，价格不可直接与历史 buybox 比较。"
                if third_party
                else "卖家发生变化，建议核实配送与价格口径。"
            ),
            evidence=current_seller,
        )
    ]


def _reviews(current: Snapshot, previous: Snapshot | None) -> list[Signal]:
    if previous is None or current.reviews is None or previous.reviews is None:
        return []
    delta = current.reviews - previous.reviews
    if delta >= 100:
        return [
            Signal(
                kind="review_growth",
                severity="medium",
                text=f"评价数增加 {delta:,}，建议跟进新增差评。",
                evidence=f"{previous.reviews:,} → {current.reviews:,}",
            )
        ]
    if delta <= -100:
        return [
            Signal(
                kind="review_drop",
                severity="low",
                text=f"评价数减少 {abs(delta):,}，可能是页面或变体差异。",
                evidence=f"{previous.reviews:,} → {current.reviews:,}",
            )
        ]
    return []


def _rating(current: Snapshot, previous: Snapshot | None) -> list[Signal]:
    if previous is None or current.rating is None or previous.rating is None:
        return []
    delta = current.rating - previous.rating
    if delta > -0.1:
        return []
    return [
        Signal(
            kind="rating_drop",
            severity="high" if delta <= -0.2 else "medium",
            text=f"星级下降 {abs(delta):.2f}，建议检查评价结构。",
            evidence=f"{previous.rating:.2f} → {current.rating:.2f}",
        )
    ]


def _stock(current: Snapshot, previous: Snapshot | None) -> list[Signal]:
    if previous is None or previous.in_stock is None or current.in_stock is None:
        return []
    if previous.in_stock and not current.in_stock:
        return [
            Signal(
                kind="stock_out",
                severity="high",
                text="库存状态从有货变为无货。",
                evidence=str(current.availability or "无货"),
            )
        ]
    return []


def _sales(current: Snapshot, previous: Snapshot | None) -> list[Signal]:
    if current.sales_value is None:
        return [
            Signal(
                kind="sales_gap",
                severity="medium",
                text="预计销量缺失，趋势判断受限。",
                evidence="data_gaps 包含“预计销量”",
            )
        ]
    if (
        previous is None
        or previous.sales_value is None
        or current.sales_text == previous.sales_text
    ):
        return []
    change = _pct(float(current.sales_value), float(previous.sales_value))
    direction = "上升" if change > 0 else "下降"
    return [
        Signal(
            kind="sales_change",
            severity="medium",
            text=f"预计销量较上次{direction} {abs(change):.1f}%（区间口径）。",
            evidence=f"{previous.sales_text or '未知'} → {current.sales_text or '未知'}",
        )
    ]


def build_signals(
    current: Snapshot,
    history: list[Snapshot],
    product_name: str = "",
) -> list[Signal]:
    previous = history[-2] if len(history) >= 2 else None
    signals: list[Signal] = []
    signals.extend(_seller(current, previous))
    signals.extend(_stock(current, previous))
    signals.extend(_price(current, previous))
    signals.extend(_rating(current, previous))
    signals.extend(_sales(current, previous))
    signals.extend(_reviews(current, previous))
    extra_gaps = [
        gap for gap in current.data_gaps if gap not in {"价格", "预计销量"}
    ]
    if extra_gaps:
        signals.append(
            Signal(
                kind="data_gaps",
                severity="low",
                text="存在其他字段缺口：" + "、".join(extra_gaps),
                evidence="data_gaps",
            )
        )
    if previous is None:
        signals.append(
            Signal(
                kind="history",
                severity="low",
                text="历史样本不足，趋势暂不可比较。",
                evidence="少于 2 条快照",
            )
        )
    if product_name:
        signals = [
            Signal(
                kind=signal.kind,
                severity=signal.severity,
                text=f"{product_name}：{signal.text}",
                evidence=signal.evidence,
            )
            for signal in signals
        ]
    unique: dict[tuple[str, str], Signal] = {}
    for signal in signals:
        unique[(signal.kind, signal.text)] = signal
    return sorted(
        unique.values(),
        key=lambda signal: (
            SEVERITY_ORDER[signal.severity],
            SIGNAL_ORDER.get(signal.kind, 99),
        ),
    )


def top_signals(signals: list[Signal], limit: int = 3) -> list[Signal]:
    return sorted(
        signals,
        key=lambda signal: (
            SEVERITY_ORDER[signal.severity],
            SIGNAL_ORDER.get(signal.kind, 99),
        ),
    )[:limit]

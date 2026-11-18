"""Read the watchlist / history and write snapshots back to the Excel workbook."""

from __future__ import annotations

import re
import shutil
from copy import copy
from dataclasses import dataclass, field
from datetime import date, datetime, time, timedelta
from pathlib import Path
from typing import Any, Iterable

from openpyxl import load_workbook
from openpyxl.cell.cell import Cell
from openpyxl.worksheet.worksheet import Worksheet

from app.models import ParsedProduct, Product, Snapshot
from app.normalize import build_snapshot

WATCHLIST_SHEET = "监控商品"
SUMMARY_SHEET = "商品数据"
HEADERS = [
    "名称",
    "产品简介",
    "产品描述",
    "主图链接",
    "详情图链接",
    "价格",
    "预计销量",
    "星级",
    "评价数量",
    "获取日期",
]
ASIN_RE = re.compile(r"/(?:dp|gp/product)/([A-Z0-9]{10})", re.IGNORECASE)
CELL_LIMIT = 32767
EXCEL_EPOCH = date(1899, 12, 30)

DEFAULT_CATEGORIES = {
    "B09C13PZX7": "外设",
    "B0DZZWMB2L": "笔记本",
    "B0DZFVBQLK": "笔记本",
    "B0874XWW23": "存储",
}


@dataclass
class WriteResult:
    path: Path
    appended: list[str] = field(default_factory=list)
    updated: list[str] = field(default_factory=list)
    skipped: list[str] = field(default_factory=list)


def extract_asin(value: Any) -> str | None:
    text = str(value or "").strip()
    match = ASIN_RE.search(text)
    if match:
        return match.group(1).upper()
    if re.fullmatch(r"[A-Z0-9]{10}", text, re.IGNORECASE):
        return text.upper()
    return None


def load_watchlist(path: Path) -> list[Product]:
    workbook = load_workbook(path, data_only=True)
    if WATCHLIST_SHEET not in workbook.sheetnames:
        raise ValueError(f"workbook is missing sheet {WATCHLIST_SHEET!r}")
    sheet = workbook[WATCHLIST_SHEET]
    products: list[Product] = []
    seen: set[str] = set()
    for row in sheet.iter_rows(min_row=2, max_col=2, values_only=True):
        name = _clean_text(row[0])
        asin = extract_asin(row[1])
        if not name or not asin or asin in seen:
            continue
        seen.add(asin)
        products.append(
            Product(
                product_id=asin,
                name=name,
                category=DEFAULT_CATEGORIES.get(asin, _category_from_name(name)),
                url=f"https://www.amazon.com/dp/{asin}",
                marketplace="amazon.com",
                excel_sheet=name,
            )
        )
    if not products:
        raise ValueError("watchlist is empty")
    return products


def read_history(path: Path, products: list[Product] | None = None) -> list[Snapshot]:
    products = products or load_watchlist(path)
    workbook = load_workbook(path, data_only=True)
    snapshots: dict[tuple[str, str], Snapshot] = {}
    order: list[tuple[str, str]] = []

    for product in products:
        if product.excel_sheet not in workbook.sheetnames:
            continue
        sheet = workbook[product.excel_sheet]
        for row in sheet.iter_rows(min_row=2, max_col=10, values_only=True):
            snapshot = _row_to_snapshot(product, row)
            if snapshot is None:
                continue
            key = (snapshot.product_id, snapshot.snapshot_date)
            if key not in snapshots:
                order.append(key)
            snapshots[key] = snapshot

    return [snapshots[key] for key in order]


def write_snapshots(
    source_path: Path,
    snapshots: Iterable[Snapshot],
    products: list[Product] | None = None,
    out_path: Path | None = None,
    in_place: bool = False,
) -> WriteResult:
    products = products or load_watchlist(source_path)
    by_asin = {product.product_id: product for product in products}
    snapshots = list(snapshots)

    if not in_place:
        out_path = out_path or source_path.with_name(
            f"{source_path.stem}_collected{source_path.suffix}"
        )
        out_path.parent.mkdir(parents=True, exist_ok=True)
        target = out_path
        if out_path.exists():
            workbook = load_workbook(target)
        else:
            shutil.copy2(source_path, out_path)
            workbook = load_workbook(target)
    else:
        target = source_path
        backup = source_path.with_name(
            f"{source_path.stem}.backup-{datetime.now():%Y%m%d-%H%M%S}{source_path.suffix}"
        )
        shutil.copy2(source_path, backup)
        workbook = load_workbook(source_path)

    result = WriteResult(path=target)

    for snapshot in snapshots:
        product = by_asin.get(snapshot.product_id)
        if product is None or product.excel_sheet not in workbook.sheetnames:
            result.skipped.append(snapshot.product_id)
            continue
        sheet = workbook[product.excel_sheet]
        _ensure_headers(sheet)
        existing_row = _find_row_by_date(sheet, snapshot.snapshot_date)
        if existing_row is None:
            row = sheet.max_row + 1
            _write_row(sheet, row, snapshot)
            result.appended.append(snapshot.product_id)
        else:
            _write_row(sheet, existing_row, snapshot)
            result.updated.append(snapshot.product_id)

    _write_summary(workbook, snapshots, products)
    workbook.save(target)
    return result


def _row_to_snapshot(product: Product, row: tuple[Any, ...]) -> Snapshot | None:
    title = _clean_text(row[0])
    snapshot_date = _excel_date_to_str(row[9])
    if not title or not snapshot_date:
        return None

    bullets = _split_bullets(_clean_text(row[1]))
    description = _clean_text(row[2])
    main_image = _clean_text(row[3])
    gallery = _split_images(_clean_text(row[4]))
    price_text = _clean_text(row[5])
    sales_text = _clean_text(row[6])
    rating_text = _clean_text(row[7])
    reviews_text = _clean_text(row[8])

    parsed = ParsedProduct(
        title=title,
        price_text=price_text,
        rating_text=rating_text,
        reviews_text=reviews_text,
        sales_text=sales_text,
        bullets=bullets,
        description=description,
        main_image=main_image,
        gallery_images=gallery,
        availability="In Stock",
        selector_hits={},
    )
    snapshot = build_snapshot(product, snapshot_date, parsed, raw_html_path=None)
    return snapshot


def _write_row(sheet: Worksheet, row: int, snapshot: Snapshot) -> None:
    values = [
        snapshot.title,
        "\n".join(snapshot.bullets),
        snapshot.description or "",
        snapshot.main_image or "",
        "\n".join(snapshot.gallery_images),
        _price_text(snapshot.price, snapshot.currency),
        snapshot.sales_text or "",
        f"{snapshot.rating:.1f} out of 5 stars" if snapshot.rating is not None else "",
        f"({snapshot.reviews:,})" if snapshot.reviews is not None else "",
        _date_value(snapshot.snapshot_date, sheet.cell(row=2, column=10)),
    ]
    for index, value in enumerate(values, start=1):
        cell = sheet.cell(row=row, column=index)
        cell.value = _truncate(value)
        source_cell = sheet.cell(row=2, column=index)
        if source_cell.has_style:
            cell._style = copy(source_cell._style)
    template_format = str(sheet.cell(row=2, column=10).number_format or "")
    if not any(marker in template_format.lower() for marker in ("y", "m", "d")):
        template_format = "yyyy/mm/dd"
    sheet.cell(row=row, column=10).number_format = template_format


def _write_summary(
    workbook: Any,
    snapshots: list[Snapshot],
    products: list[Product],
) -> None:
    if SUMMARY_SHEET not in workbook.sheetnames:
        return
    sheet = workbook[SUMMARY_SHEET]
    _ensure_headers(sheet)
    by_asin = {snapshot.product_id: snapshot for snapshot in snapshots}
    for index, product in enumerate(products, start=2):
        snapshot = by_asin.get(product.product_id)
        if snapshot is None:
            continue
        _write_row(sheet, index, snapshot)


def _ensure_headers(sheet: Worksheet) -> None:
    for column, header in enumerate(HEADERS, start=1):
        cell = sheet.cell(row=1, column=column)
        if not cell.value:
            cell.value = header


def _find_row_by_date(sheet: Worksheet, snapshot_date: str) -> int | None:
    found = None
    for row in range(2, sheet.max_row + 1):
        value = _excel_date_to_str(sheet.cell(row=row, column=10).value)
        if value == snapshot_date:
            found = row
    return found


def _date_value(value: str, template: Cell) -> Any:
    day = date.fromisoformat(value)
    return datetime.combine(day, time.min)


def _excel_date_to_str(value: Any) -> str | None:
    if isinstance(value, datetime):
        return value.date().isoformat()
    if isinstance(value, date):
        return value.isoformat()
    if isinstance(value, (int, float)):
        return (EXCEL_EPOCH + timedelta(days=int(value))).isoformat()
    text = _clean_text(value)
    if not text:
        return None
    match = re.search(r"(\d{4})[-/.](\d{1,2})[-/.](\d{1,2})", text)
    if match:
        year, month, day = (int(part) for part in match.groups())
        try:
            return date(year, month, day).isoformat()
        except ValueError:
            return None
    return None


def _split_bullets(text: str | None) -> list[str]:
    if not text:
        return []
    parts = re.split(r"\r?\n|(?<=\.)\s{2,}", text)
    return [part.strip() for part in parts if part.strip()]


def _split_images(text: str | None) -> list[str]:
    if not text:
        return []
    parts = re.split(r"\r?\n|,\s*(?=https?://)", text)
    return [part.strip() for part in parts if part.strip()]


def _price_text(price: float | None, currency: str | None) -> str:
    if price is None:
        return ""
    return f"{currency or '$'}{price:,.2f}"


def _category_from_name(name: str) -> str:
    lowered = name.lower()
    if "鼠标" in name or "mouse" in lowered:
        return "外设"
    if "笔记本" in name or "laptop" in lowered or "电脑" in name:
        return "笔记本"
    if "ssd" in lowered or "硬盘" in name:
        return "存储"
    return "未分类"


def _clean_text(value: Any) -> str:
    if value is None:
        return ""
    text = str(value).replace("\u00a0", " ")
    return _truncate(text.strip())


def _truncate(value: Any) -> Any:
    if isinstance(value, (datetime, date)):
        return value
    text = "" if value is None else str(value)
    text = re.sub(r"[\x00-\x08\x0b\x0c\x0e-\x1f]", "", text)
    return text[:CELL_LIMIT]

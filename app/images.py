"""Amazon image URL normalization."""

from __future__ import annotations

import re
from collections.abc import Iterable

IMAGE_ID_RE = re.compile(r"/images/I/([^/.]+)")
SIZE_TOKEN_RE = re.compile(r"\._[^/]+_\.(jpe?g|png|webp)$", re.IGNORECASE)


def clean_url(url: str | None) -> str | None:
    if not url:
        return None
    cleaned = url.strip().replace("&amp;", "&")
    if cleaned.startswith("//"):
        cleaned = "https:" + cleaned
    if cleaned.startswith("data:"):
        return None
    return cleaned or None


def upgrade_image_url(url: str | None, size: str = "SL1500") -> str | None:
    cleaned = clean_url(url)
    if not cleaned:
        return None
    if "play-icon-overlay" in cleaned:
        return cleaned
    if "m.media-amazon.com/images/I/" not in cleaned:
        return cleaned
    return SIZE_TOKEN_RE.sub(f"._AC_{size}_.\\1", cleaned)


def image_key(url: str | None) -> str | None:
    cleaned = clean_url(url)
    if not cleaned:
        return None
    match = IMAGE_ID_RE.search(cleaned)
    return match.group(1) if match else cleaned


def dedupe_images(urls: Iterable[str | None]) -> list[str]:
    result: list[str] = []
    seen: set[str] = set()
    for url in urls:
        cleaned = clean_url(url)
        if not cleaned:
            continue
        key = image_key(cleaned) or cleaned
        if key in seen:
            continue
        seen.add(key)
        result.append(cleaned)
    return result


def gallery_from_html(html: str) -> list[str]:
    """Extract hi-res gallery images from Amazon's ImageBlockATF script."""
    urls: list[str] = []
    for pattern in (
        r'"hiRes":"(https?://[^"]+)"',
        r"'hiRes':'(https?://[^']+)'",
        r'"large":"(https?://[^"]+)"',
        r"'large':'(https?://[^']+)'",
    ):
        urls.extend(re.findall(pattern, html))
    return dedupe_images(upgrade_image_url(url) for url in urls)

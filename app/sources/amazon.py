"""Amazon product source: replay cache, curl_cffi live fetch, Playwright fallback."""

from __future__ import annotations

import gzip
import hashlib
import json
import random
import time
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from app.errors import (
    CacheMissError,
    FetchError,
    SourceBlockedError,
    SourceUnavailableError,
)
from app.parse import detect_page_state

DEFAULT_USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
    "AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/131.0.0.0 Safari/537.36"
)


@dataclass
class FetchResult:
    html: str
    path: Path
    from_cache: bool
    status_code: int | None = None
    fetched_at: str = ""
    source: str = "replay"


class AmazonSource:
    def __init__(
        self,
        cache_dir: Path,
        mode: str = "replay",
        marketplace: str = "amazon.com",
        timeout: float = 30.0,
        retries: int = 1,
        delay: float = 6.0,
        proxy: str = "",
        headless: bool = True,
        user_agent: str = "",
    ) -> None:
        self.cache_dir = cache_dir
        self.mode = mode
        self.marketplace = marketplace
        self.timeout = timeout
        self.retries = max(0, retries)
        self.delay = max(0.0, delay)
        self.proxy = proxy
        self.headless = headless
        self.user_agent = user_agent or DEFAULT_USER_AGENT
        self._last_live_request = 0.0

    # ------------------------------------------------------------------ public
    def fetch(
        self,
        product: Any,
        snapshot_date: str,
        refresh: bool = False,
    ) -> FetchResult:
        if self.mode == "replay":
            return self._fetch_replay(product, snapshot_date)
        return self._fetch_live(product, snapshot_date, refresh=refresh)

    def capture(self, product: Any, snapshot_date: str, file_path: Path) -> FetchResult:
        html = file_path.read_text(encoding="utf-8", errors="replace")
        state = detect_page_state(html)
        if state == "captcha":
            raise SourceBlockedError("captured page is a CAPTCHA page")
        if state in {"blocked", "not_found"}:
            raise SourceUnavailableError(f"captured page state: {state}")
        path = self._save_cache(product.product_id, snapshot_date, html, None, "manual")
        return FetchResult(
            html=html,
            path=path,
            from_cache=False,
            status_code=None,
            fetched_at=_now(),
            source="manual",
        )

    def cache_path(self, asin: str, snapshot_date: str) -> Path:
        return self.cache_dir / asin / f"{snapshot_date}.html.gz"

    def cached_dates(self, asin: str) -> list[str]:
        folder = self.cache_dir / asin
        if not folder.exists():
            return []
        dates: list[str] = []
        for path in folder.glob("*.html.gz"):
            if ".blocked." in path.name:
                continue
            dates.append(path.name.removesuffix(".html.gz"))
        return sorted(dates, reverse=True)

    # ------------------------------------------------------------------ replay
    def _fetch_replay(self, product: Any, snapshot_date: str) -> FetchResult:
        path = self.cache_path(product.product_id, snapshot_date)
        if not path.exists():
            dates = self.cached_dates(product.product_id)
            available = ", ".join(dates[:5]) if dates else "none"
            raise CacheMissError(
                f"{product.product_id}: no cache for {snapshot_date} "
                f"(available: {available})"
            )
        html = _read_gzip(path)
        meta = _read_meta(path)
        return FetchResult(
            html=html,
            path=path,
            from_cache=True,
            status_code=meta.get("status_code"),
            fetched_at=meta.get("fetched_at", ""),
            source=meta.get("source", "replay"),
        )

    # -------------------------------------------------------------------- live
    def _fetch_live(self, product: Any, snapshot_date: str, refresh: bool) -> FetchResult:
        path = self.cache_path(product.product_id, snapshot_date)
        if path.exists() and not refresh:
            html = _read_gzip(path)
            meta = _read_meta(path)
            return FetchResult(
                html=html,
                path=path,
                from_cache=True,
                status_code=meta.get("status_code"),
                fetched_at=meta.get("fetched_at", ""),
                source=meta.get("source", "cache"),
            )

        url = self.product_url(product)
        last_error: Exception | None = None
        for attempt in range(self.retries + 1):
            self._polite_delay()
            try:
                html, status_code, source = self._request(url)
            except FetchError as exc:
                last_error = exc
                if attempt < self.retries:
                    time.sleep(min(2**attempt, 8) + random.uniform(0, 1))
                continue

            state = detect_page_state(html)
            if state == "captcha":
                self._save_blocked(product.product_id, snapshot_date, html)
                raise SourceBlockedError(
                    f"{product.product_id}: Amazon CAPTCHA (HTTP {status_code})"
                )
            if state == "blocked":
                self._save_blocked(product.product_id, snapshot_date, html)
                raise SourceBlockedError(
                    f"{product.product_id}: Amazon bot block (HTTP {status_code})"
                )
            if state == "not_found" or status_code in {404, 410}:
                self._save_blocked(product.product_id, snapshot_date, html)
                raise SourceUnavailableError(
                    f"{product.product_id}: page unavailable (HTTP {status_code})"
                )
            if status_code is not None and status_code >= 500:
                last_error = FetchError(
                    f"{product.product_id}: HTTP {status_code}"
                )
                if attempt < self.retries:
                    time.sleep(min(2**attempt, 8) + random.uniform(0, 1))
                continue
            if status_code is not None and status_code >= 400:
                raise FetchError(f"{product.product_id}: HTTP {status_code}")

            saved = self._save_cache(
                product.product_id,
                snapshot_date,
                html,
                status_code,
                source,
            )
            return FetchResult(
                html=html,
                path=saved,
                from_cache=False,
                status_code=status_code,
                fetched_at=_now(),
                source=source,
            )

        raise FetchError(f"{product.product_id}: fetch failed: {last_error}")

    def _request(self, url: str) -> tuple[str, int | None, str]:
        errors: list[str] = []
        try:
            return self._request_curl(url)
        except FetchError as exc:
            errors.append(f"curl_cffi: {exc}")

        try:
            return self._request_playwright(url)
        except FetchError as exc:
            errors.append(f"playwright: {exc}")

        raise FetchError("; ".join(errors))

    def _request_curl(self, url: str) -> tuple[str, int | None, str]:
        try:
            from curl_cffi import requests as curl_requests
        except ImportError as exc:
            raise FetchError("curl_cffi is not installed") from exc

        kwargs: dict[str, Any] = {
            "headers": self._headers(),
            "impersonate": "chrome",
            "timeout": self.timeout,
            "allow_redirects": True,
        }
        if self.proxy:
            kwargs["proxies"] = {"http": self.proxy, "https": self.proxy}

        try:
            response = curl_requests.get(url, **kwargs)
        except Exception as exc:  # curl_cffi raises its own request errors
            raise FetchError(str(exc)) from exc
        return response.text, response.status_code, "curl_cffi"

    def _request_playwright(self, url: str) -> tuple[str, int | None, str]:
        try:
            from playwright.sync_api import sync_playwright
        except ImportError as exc:
            raise FetchError(
                "playwright is not installed "
                "(uv sync --extra browser && playwright install chromium)"
            ) from exc

        try:
            with sync_playwright() as playwright:
                browser = playwright.chromium.launch(headless=self.headless)
                context = browser.new_context(
                    user_agent=self.user_agent,
                    locale="en-US",
                    timezone_id="America/New_York",
                    viewport={"width": 1365, "height": 900},
                )
                context.add_cookies(
                    [
                        {
                            "name": "i18n-prefs",
                            "value": "USD",
                            "domain": ".amazon.com",
                            "path": "/",
                        },
                        {
                            "name": "lc-main",
                            "value": "en_US",
                            "domain": ".amazon.com",
                            "path": "/",
                        },
                    ]
                )
                page = context.new_page()
                response = page.goto(
                    url,
                    wait_until="domcontentloaded",
                    timeout=int(self.timeout * 1000),
                )
                try:
                    page.wait_for_selector("#productTitle", timeout=8000)
                except Exception:
                    pass
                page.wait_for_timeout(1200)
                html = page.content()
                status = response.status if response is not None else None
                browser.close()
                return html, status, "playwright"
        except Exception as exc:
            raise FetchError(str(exc)) from exc

    # ----------------------------------------------------------------- helpers
    def product_url(self, product: Any) -> str:
        url = str(product.url or "").strip()
        if not url:
            url = f"https://www.{self.marketplace}/dp/{product.product_id}"
        separator = "&" if "?" in url else "?"
        return f"{url}{separator}th=1&psc=1&language=en_US"

    def _headers(self) -> dict[str, str]:
        return {
            "User-Agent": self.user_agent,
            "Accept": (
                "text/html,application/xhtml+xml,application/xml;q=0.9,"
                "image/avif,image/webp,image/apng,*/*;q=0.8"
            ),
            "Accept-Language": "en-US,en;q=0.9",
            "Cache-Control": "no-cache",
            "Pragma": "no-cache",
            "Referer": f"https://www.{self.marketplace}/",
            "Cookie": "i18n-prefs=USD; lc-main=en_US",
            "Sec-Ch-Ua": '"Chromium";v="131", "Not_A Brand";v="24"',
            "Sec-Ch-Ua-Mobile": "?0",
            "Sec-Ch-Ua-Platform": '"Windows"',
            "Sec-Fetch-Dest": "document",
            "Sec-Fetch-Mode": "navigate",
            "Sec-Fetch-Site": "none",
            "Sec-Fetch-User": "?1",
            "Upgrade-Insecure-Requests": "1",
        }

    def _polite_delay(self) -> None:
        if self.delay <= 0:
            return
        elapsed = time.monotonic() - self._last_live_request
        wait = self.delay - elapsed
        if wait > 0:
            time.sleep(wait + random.uniform(0, 1.5))
        self._last_live_request = time.monotonic()

    def _save_cache(
        self,
        asin: str,
        snapshot_date: str,
        html: str,
        status_code: int | None,
        source: str,
    ) -> Path:
        path = self.cache_path(asin, snapshot_date)
        path.parent.mkdir(parents=True, exist_ok=True)
        with gzip.open(path, "wt", encoding="utf-8") as handle:
            handle.write(html)
        meta = {
            "asin": asin,
            "snapshot_date": snapshot_date,
            "url": f"https://www.{self.marketplace}/dp/{asin}",
            "status_code": status_code,
            "fetched_at": _now(),
            "source": source,
            "sha256": hashlib.sha256(html.encode("utf-8")).hexdigest(),
            "bytes": len(html.encode("utf-8")),
        }
        path.with_suffix(".meta.json").write_text(
            json.dumps(meta, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        return path

    def _save_blocked(self, asin: str, snapshot_date: str, html: str) -> Path:
        path = self.cache_dir / asin / f"{snapshot_date}.blocked.html.gz"
        path.parent.mkdir(parents=True, exist_ok=True)
        with gzip.open(path, "wt", encoding="utf-8") as handle:
            handle.write(html)
        return path


def _read_gzip(path: Path) -> str:
    with gzip.open(path, "rt", encoding="utf-8", errors="replace") as handle:
        return handle.read()


def _read_meta(path: Path) -> dict[str, Any]:
    meta_path = path.with_suffix(".meta.json")
    if not meta_path.exists():
        return {}
    try:
        return json.loads(meta_path.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return {}


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()

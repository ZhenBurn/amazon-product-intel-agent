"""Parse Amazon product detail pages with selector and JSON-LD fallbacks."""

from __future__ import annotations

import json
import re
from typing import Any

from bs4 import BeautifulSoup, Tag

from app.errors import BlockedError, PageUnavailableError, ParseError
from app.images import dedupe_images, gallery_from_html, image_key, upgrade_image_url
from app.models import ParsedProduct


def _selector_text(soup: BeautifulSoup, selectors: list[str]) -> tuple[str | None, str | None]:
    for selector in selectors:
        node = soup.select_one(selector)
        if node is None:
            continue
        value = node.get_text(" ", strip=True)
        if value:
            return value, selector
    return None, None


def _selector_attr(
    soup: BeautifulSoup,
    selectors: list[str],
    attr: str,
) -> tuple[str | None, str | None]:
    for selector in selectors:
        node = soup.select_one(selector)
        if node is None:
            continue
        value = node.get(attr)
        if value:
            return str(value).strip(), selector
    return None, None


def detect_page_state(html_text: str) -> str:
    lowered = html_text.lower()
    if (
        "validatecaptcha" in lowered
        or "robot check" in lowered
        or "enter the characters you see below" in lowered
    ):
        return "captcha"
    if (
        "sorry! something went wrong" in lowered
        or "automated access to amazon data" in lowered
        or "api-services-support@amazon.com" in lowered
    ):
        return "blocked"
    if "page not found" in lowered and "dogs of amazon" in lowered:
        return "not_found"
    return "ok"


def _iter_json_ld(data: Any) -> list[dict[str, Any]]:
    items: list[dict[str, Any]] = []
    if isinstance(data, list):
        for item in data:
            items.extend(_iter_json_ld(item))
    elif isinstance(data, dict):
        if "@graph" in data:
            items.extend(_iter_json_ld(data["@graph"]))
        items.append(data)
    return items


def _is_product(item: dict[str, Any]) -> bool:
    types = item.get("@type")
    if isinstance(types, list):
        return "Product" in types
    return types == "Product"


def _json_ld_product(soup: BeautifulSoup) -> dict[str, Any]:
    for script in soup.select('script[type="application/ld+json"]'):
        raw = script.string or script.get_text()
        if not raw.strip():
            continue
        try:
            data = json.loads(raw)
        except json.JSONDecodeError:
            continue
        for item in _iter_json_ld(data):
            if _is_product(item):
                return item
    return {}


def _ld_offer(product: dict[str, Any]) -> dict[str, Any]:
    offers = product.get("offers")
    if isinstance(offers, list):
        return next((offer for offer in offers if isinstance(offer, dict)), {})
    return offers if isinstance(offers, dict) else {}


def _ld_image(product: dict[str, Any]) -> str | None:
    image = product.get("image")
    if isinstance(image, str):
        return image
    if isinstance(image, list):
        for item in image:
            if isinstance(item, str):
                return item
            if isinstance(item, dict) and item.get("url"):
                return str(item["url"])
    if isinstance(image, dict):
        return image.get("url")
    return None


def _dynamic_main_image(node: Tag | None) -> str | None:
    if node is None:
        return None
    raw = node.get("data-a-dynamic-image")
    if not raw:
        return None
    try:
        data = json.loads(str(raw))
    except json.JSONDecodeError:
        return None
    if not isinstance(data, dict) or not data:
        return None
    return max(data, key=lambda url: len(str(url)))


def _parse_sales_text(soup: BeautifulSoup) -> tuple[str | None, str | None]:
    value, selector = _selector_text(
        soup,
        [
            "#socialProofingAsinFaceout_feature_div",
            "#social-proofing-faceout-title-tk_bought",
            "#socialProofingAsinFaceout_feature_div .a-section",
        ],
    )
    if value and "bought" in value.lower():
        return value, selector

    text = soup.get_text(" ", strip=True)
    match = re.search(
        r"([0-9][0-9.,]*\s*[KkMm]?\+?\s*bought(?:\s+in\s+(?:the\s+)?past\s+month)?)",
        text,
        re.IGNORECASE,
    )
    if match:
        return match.group(1), "text-regex"
    return None, None


def _parse_rating(soup: BeautifulSoup) -> tuple[str | None, str | None]:
    node = soup.select_one("#acrPopover")
    if node is not None:
        title = node.get("title")
        if title:
            return str(title).strip(), "#acrPopover[title]"

    return _selector_text(
        soup,
        [
            "#averageCustomerReviews .a-icon-alt",
            'span[data-hook="rating-out-of-text"]',
            "#acrPopover .a-icon-alt",
        ],
    )


def _parse_description(soup: BeautifulSoup) -> tuple[str | None, str | None]:
    for selector in (
        "#productDescription",
        "#productDescription_feature_div",
        "#bookDescription_feature_div",
        "#aplus",
    ):
        node = soup.select_one(selector)
        if node is None:
            continue
        value = node.get_text("\n", strip=True)
        if value:
            return value, selector
    return None, None


def _parse_bullets(soup: BeautifulSoup) -> tuple[list[str], str | None]:
    for selector in ("#feature-bullets li span.a-list-item", "#feature-bullets li"):
        nodes = soup.select(selector)
        values = [node.get_text(" ", strip=True) for node in nodes]
        values = [value for value in values if value]
        if values:
            return values, selector
    return [], None


def _parse_main_image(
    soup: BeautifulSoup,
    json_ld: dict[str, Any],
) -> tuple[str | None, str | None]:
    node = soup.select_one("#landingImage")
    if node is not None:
        value = node.get("data-old-hires") or node.get("src")
        if value:
            return upgrade_image_url(str(value)), "#landingImage[data-old-hires|src]"
        dynamic = _dynamic_main_image(node)
        if dynamic:
            return upgrade_image_url(dynamic), "#landingImage[data-a-dynamic-image]"

    value, selector = _selector_attr(
        soup,
        ["#imgTagWrapperId img", "#main-image-container img", "#main-image img"],
        "src",
    )
    if value:
        return upgrade_image_url(value), f"{selector}[src]"

    ld_image = _ld_image(json_ld)
    if ld_image:
        return upgrade_image_url(ld_image), "json-ld.image"
    return None, None


def _parse_gallery(soup: BeautifulSoup, main_image: str | None) -> tuple[list[str], str | None]:
    urls: list[str] = []
    selector_used: str | None = None
    for selector in ("#altImages li img", "#imageBlock #altImages img"):
        nodes = soup.select(selector)
        if nodes:
            selector_used = selector
            urls.extend(str(node.get("src")) for node in nodes if node.get("src"))
            break

    if not urls:
        for script in soup.find_all("script"):
            raw = script.string or script.get_text()
            if "colorImages" in raw or "hiRes" in raw:
                urls.extend(gallery_from_html(raw))

    upgraded = [upgrade_image_url(url) for url in urls]
    main_key = image_key(main_image)
    gallery = dedupe_images(
        url for url in upgraded if url and image_key(url) != main_key
    )
    return gallery, selector_used or "image-script"


def parse_product_page(html_text: str) -> ParsedProduct:
    soup = BeautifulSoup(html_text, "html.parser")
    json_ld = _json_ld_product(soup)
    hits: dict[str, str] = {}

    title, title_selector = _selector_text(
        soup,
        ["#productTitle", "#title", "h1.a-size-large"],
    )
    if not title:
        meta = soup.select_one('meta[property="og:title"]')
        if meta is not None and meta.get("content"):
            title, title_selector = str(meta["content"]), 'meta[property="og:title"]'
    if not title and json_ld.get("name"):
        title, title_selector = str(json_ld["name"]), "json-ld.name"
    if not title:
        state = detect_page_state(html_text)
        if state == "captcha":
            raise BlockedError("Amazon CAPTCHA page")
        if state in {"blocked", "not_found"}:
            raise PageUnavailableError(f"Amazon page state: {state}")
        raise ParseError("product title not found")
    hits["title"] = title_selector or "unknown"

    price_text, price_selector = _selector_text(
        soup,
        [
            (
                "#corePriceDisplay_desktop_feature_div "
                'span.a-price[data-a-color="base"] span.a-offscreen'
            ),
            (
                "#corePrice_feature_div "
                'span.a-price[data-a-color="base"] span.a-offscreen'
            ),
            "#corePrice_feature_div .a-offscreen",
            "#price_inside_buybox",
            "#priceblock_ourprice",
            "#priceblock_dealprice",
            "#priceblock_saleprice",
            "#tp_price_block_total_price_ww .a-offscreen",
            "#buybox .a-price .a-offscreen",
        ],
    )
    if price_text is None:
        offer = _ld_offer(json_ld)
        if offer.get("price") is not None:
            currency = str(offer.get("priceCurrency") or "USD")
            symbol = {"USD": "$", "CNY": "¥", "EUR": "€", "GBP": "£"}.get(
                currency, currency + " "
            )
            price_text, price_selector = (
                f"{symbol}{offer['price']}",
                "json-ld.offers.price",
            )
    if price_text:
        hits["price"] = price_selector or "unknown"

    list_price_text, list_price_selector = _selector_text(
        soup,
        [
            "#corePriceDisplay_desktop_feature_div .basisPrice .a-offscreen",
            "#corePriceDisplay_desktop_feature_div .a-text-price .a-offscreen",
            "#listPrice",
            "#priceblock_listprice",
        ],
    )
    if list_price_text:
        hits["list_price"] = list_price_selector or "unknown"

    rating_text, rating_selector = _parse_rating(soup)
    if rating_text is None:
        rating = json_ld.get("aggregateRating") or {}
        if rating.get("ratingValue") is not None:
            rating_text, rating_selector = (
                f"{rating['ratingValue']} out of 5 stars",
                "json-ld.aggregateRating.ratingValue",
            )
    if rating_text:
        hits["rating"] = rating_selector or "unknown"

    reviews_text, reviews_selector = _selector_text(
        soup,
        [
            "#acrCustomerReviewText",
            "#acrCustomerReviewLink",
            'span[data-hook="total-review-count"]',
        ],
    )
    if reviews_text is None:
        rating = json_ld.get("aggregateRating") or {}
        count = rating.get("reviewCount") or rating.get("ratingCount")
        if count is not None:
            reviews_text = f"({count:,} ratings)"
            reviews_selector = "json-ld.aggregateRating.reviewCount"
    if reviews_text:
        hits["reviews"] = reviews_selector or "unknown"

    sales_text, sales_selector = _parse_sales_text(soup)
    if sales_text:
        hits["sales"] = sales_selector or "unknown"

    bullets, bullets_selector = _parse_bullets(soup)
    if bullets:
        hits["bullets"] = bullets_selector or "unknown"

    description, description_selector = _parse_description(soup)
    if description is None and json_ld.get("description"):
        description = str(json_ld["description"])
        description_selector = "json-ld.description"
    if description:
        hits["description"] = description_selector or "unknown"

    main_image, main_image_selector = _parse_main_image(soup, json_ld)
    if main_image:
        hits["main_image"] = main_image_selector or "unknown"

    gallery_images, gallery_selector = _parse_gallery(soup, main_image)
    if gallery_images:
        hits["gallery"] = gallery_selector or "unknown"

    availability, availability_selector = _selector_text(
        soup,
        [
            "#availability",
            "#outOfStock",
            "#availability .a-color-success",
            "#availability .a-color-price",
        ],
    )
    if availability:
        hits["availability"] = availability_selector or "unknown"

    seller, seller_selector = _selector_text(
        soup,
        ["#merchantInfoFeature_feature_div", "#sellerProfileTriggerId", "#bylineInfo"],
    )
    if seller:
        hits["seller"] = seller_selector or "unknown"

    coupon, coupon_selector = _selector_text(
        soup,
        ["#promoPriceBlockMessage", "#couponBadge", "#couponFeature"],
    )
    if coupon:
        hits["coupon"] = coupon_selector or "unknown"

    canonical_url, _ = _selector_attr(soup, ['link[rel="canonical"]'], "href")
    if canonical_url:
        hits["canonical"] = 'link[rel="canonical"]'

    return ParsedProduct(
        title=title,
        price_text=price_text,
        list_price_text=list_price_text,
        rating_text=rating_text,
        reviews_text=reviews_text,
        sales_text=sales_text,
        bullets=bullets,
        description=description,
        main_image=main_image,
        gallery_images=gallery_images,
        availability=availability,
        seller=seller,
        coupon=coupon,
        canonical_url=canonical_url,
        selector_hits=hits,
    )

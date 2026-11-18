"""Compact Amazon-like HTML fixtures for deterministic parser tests."""

from __future__ import annotations

import html
import json

from app.models import Product

PRODUCT_A = Product(
    product_id="B09C13PZX7",
    name="Razer Basilisk V3",
    category="外设",
    url="https://www.amazon.com/dp/B09C13PZX7",
    excel_sheet="雷蛇鼠标",
)
PRODUCT_B = Product(
    product_id="B0874XWW23",
    name="Samsung T7",
    category="存储",
    url="https://www.amazon.com/dp/B0874XWW23",
    excel_sheet="Samsung T7",
)
PRODUCT_C = Product(
    product_id="B0DZZWMB2L",
    name="ASUS ROG Strix G16",
    category="笔记本",
    url="https://www.amazon.com/dp/B0DZZWMB2L",
    excel_sheet="华硕ROG电脑",
)


def captcha_page() -> str:
    return """<!DOCTYPE html>
<html><head><title>Robot Check</title></head>
<body>
<form action="/errors/validateCaptcha"></form>
<p>Enter the characters you see below</p>
</body></html>"""


def render_page(
    *,
    title: str = "Razer Basilisk V3 Customizable Ergonomic Gaming Mouse",
    price: str | None = "$34.99",
    list_price: str | None = "$49.99",
    rating: str | None = "4.6 out of 5 stars",
    reviews: str | None = "(9,215 ratings)",
    sales: str | None = "10K+ bought in past month",
    bullets: list[str] | None = None,
    description: str | None = "Create, control, and champion your playstyle.",
    main_image: str | None = (
        "https://m.media-amazon.com/images/I/61AcT0ZuO3L._AC_SL1500_.jpg"
    ),
    gallery: list[str] | None = None,
    availability: str | None = "In Stock",
    json_ld_price: bool = False,
) -> str:
    bullets = bullets if bullets is not None else [
        "ICONIC ERGONOMIC DESIGN WITH THUMB REST",
        "11 PROGRAMMABLE BUTTONS",
        "HYPERSCROLL TILT WHEEL",
    ]
    gallery = gallery if gallery is not None else [
        "https://m.media-amazon.com/images/I/31N1BZUZLwL._AC_SL1500_.jpg",
        "https://m.media-amazon.com/images/I/51XpciVLsRL._AC_SL1500_.jpg",
        "https://m.media-amazon.com/images/I/51thGzFyyYL"
        ".SS40_BG85,85,85_BR-120_PKdp-play-icon-overlay__.jpg",
    ]

    price_block = ""
    if price and not json_ld_price:
        list_block = (
            '<span class="basisPrice"><span class="a-offscreen">'
            f"{html.escape(list_price)}</span></span>"
            if list_price
            else ""
        )
        price_block = (
            '<div id="corePriceDisplay_desktop_feature_div">'
            '<span class="a-price" data-a-color="base"><span class="a-offscreen">'
            f"{html.escape(price)}</span></span>{list_block}</div>"
        )

    rating_block = (
        f'<span id="acrPopover" title="{html.escape(rating)}"></span>'
        if rating
        else ""
    )
    reviews_block = (
        f'<span id="acrCustomerReviewText">{html.escape(reviews)}</span>'
        if reviews
        else ""
    )
    sales_block = (
        f'<div id="socialProofingAsinFaceout_feature_div">{html.escape(sales)}</div>'
        if sales
        else ""
    )
    availability_block = (
        f'<div id="availability"><span>{html.escape(availability)}</span></div>'
        if availability
        else ""
    )
    bullet_html = "".join(
        f'<li><span class="a-list-item">{html.escape(item)}</span></li>' for item in bullets
    )
    gallery_html = "".join(
        f'<li class="imageThumbnail"><img src="{html.escape(url)}"></li>' for url in gallery
    )
    main_html = (
        f'<img id="landingImage" data-old-hires="{html.escape(main_image)}">'
        if main_image
        else ""
    )
    description_html = (
        f"<div id=\"productDescription\"><p>{html.escape(description)}</p></div>"
        if description
        else ""
    )

    ld = {
        "@context": "https://schema.org",
        "@type": "Product",
        "name": title,
        "image": [main_image] if main_image else [],
        "description": description or "",
        "offers": {
            "@type": "Offer",
            "price": (price or "").replace("$", "").replace(",", ""),
            "priceCurrency": "USD",
        },
        "aggregateRating": {
            "@type": "AggregateRating",
            "ratingValue": (rating or "").split()[0] if rating else "",
            "reviewCount": "9215",
        },
    }
    ld_script = (
        f'<script type="application/ld+json">{json.dumps(ld)}</script>'
        if json_ld_price
        else ""
    )

    return f"""<!DOCTYPE html>
<html lang="en-US">
<head><title>{html.escape(title)}</title>{ld_script}</head>
<body>
<span id="productTitle">{html.escape(title)}</span>
{price_block}
{rating_block}
{reviews_block}
{sales_block}
{availability_block}
<div id="feature-bullets"><ul>{bullet_html}</ul></div>
{description_html}
{main_html}
<div id="altImages"><ul>{gallery_html}</ul></div>
</body></html>"""

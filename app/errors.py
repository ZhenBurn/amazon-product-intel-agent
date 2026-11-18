"""Shared exception types for fetch and parse layers."""

from __future__ import annotations


class FetchError(RuntimeError):
    """Raised when a product page cannot be fetched."""


class CacheMissError(FetchError):
    """Raised when replay mode has no cached HTML for a product."""


class SourceBlockedError(FetchError):
    """Raised when Amazon serves a CAPTCHA or bot-block page."""


class SourceUnavailableError(FetchError):
    """Raised when the product page is a 404 or unavailable shell."""


class ParseError(RuntimeError):
    """Raised when a page cannot be parsed."""


class BlockedError(ParseError):
    """Raised when a CAPTCHA page is parsed."""


class PageUnavailableError(ParseError):
    """Raised when a product page is a 404 or unavailable shell."""

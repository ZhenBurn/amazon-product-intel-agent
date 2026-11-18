from __future__ import annotations

from eval.run_real_eval import _compare


def test_compare_none_and_numeric_fields() -> None:
    assert _compare("price", None, None)
    assert _compare("price", 436.99, 436.99)
    assert not _compare("price", None, 436.99)
    assert not _compare("price", 436.99, None)
    assert _compare("rating", 4.6, 4.6)
    assert not _compare("rating", 4.6, 4.7)


def test_compare_text_and_presence_fields() -> None:
    assert _compare("title_contains", "Samsung T7 Portable SSD", "Samsung T7")
    assert not _compare("title_contains", "Samsung T7 Portable SSD", "Razer")
    assert _compare("sales_text", "5K+ bought in past month", "5K+ bought in past month")
    assert not _compare("sales_text", None, "5K+ bought in past month")
    assert _compare("seller_present", True, True)
    assert _compare("availability_contains", "Only 12 left in stock", "Only 12 left")
    assert _compare("availability_contains", None, None)
    assert not _compare("availability_contains", "In Stock", "Only 12 left")

"""
Unit tests for scraper utility functions.
Tests price parsing, brand extraction, discount computation, and stock detection.
"""

import pytest
from scraper.utils import (
    parse_price,
    extract_brand,
    compute_discount_pct,
    is_in_stock,
)


# ─────────────────────────────────────────────────────────────────────────────
# parse_price
# ─────────────────────────────────────────────────────────────────────────────

class TestParsePrice:
    def test_standard_kes_format(self):
        assert parse_price("KES 21,999.00") == pytest.approx(21999.0)

    def test_kes_no_decimal(self):
        assert parse_price("KES 5,000") == pytest.approx(5000.0)

    def test_plain_number(self):
        assert parse_price("119999.00") == pytest.approx(119999.0)

    def test_with_commas_only(self):
        assert parse_price("1,200,000.00") == pytest.approx(1200000.0)

    def test_none_input(self):
        assert parse_price(None) is None

    def test_empty_string(self):
        assert parse_price("") is None

    def test_non_numeric(self):
        assert parse_price("N/A") is None

    def test_small_price(self):
        assert parse_price("KES 499.00") == pytest.approx(499.0)

    def test_large_price(self):
        assert parse_price("KES 850,000.00") == pytest.approx(850000.0)


# ─────────────────────────────────────────────────────────────────────────────
# extract_brand
# ─────────────────────────────────────────────────────────────────────────────

class TestExtractBrand:
    def test_lenovo_laptop(self):
        name = "Lenovo ThinkPad T480 Intel Core i5-8350U 14\" FHD"
        assert extract_brand(name) == "Lenovo"

    def test_hp_laptop(self):
        name = "HP ProBook 440 G11 Intel Core Ultra 5"
        assert extract_brand(name) == "HP"

    def test_dell_laptop(self):
        name = "Dell XPS 15 9570 Gaming PC"
        assert extract_brand(name) == "Dell"

    def test_samsung_phone(self):
        name = "Samsung Galaxy S24 Ultra 5G 256GB Phantom Black"
        assert extract_brand(name) == "Samsung"

    def test_apple_iphone(self):
        name = "Apple iPhone 15 Pro Max 256GB Black Titanium"
        assert extract_brand(name) == "Apple"

    def test_jbl_speaker(self):
        name = "JBL Flip 6 Portable Bluetooth Speaker"
        assert extract_brand(name) == "JBL"

    def test_lg_tv(self):
        name = "LG 55 Inch 4K Smart TV OLED"
        assert extract_brand(name) == "LG"

    def test_unknown_brand(self):
        # Unknown brands return None from the Python util; dbt maps them to 'Other'
        result = extract_brand("Generic USB Hub 4-Port Type C")
        assert result is None

    def test_none_input(self):
        assert extract_brand(None) is None

    def test_empty_string(self):
        assert extract_brand("") is None

    def test_logitech_accessory(self):
        name = "Logitech MX Master 3S Wireless Mouse"
        assert extract_brand(name) == "Logitech"

    def test_hisense_tv(self):
        name = "Hisense 43A4K 43 Inch FHD Smart TV"
        assert extract_brand(name) == "Hisense"


# ─────────────────────────────────────────────────────────────────────────────
# compute_discount_pct
# ─────────────────────────────────────────────────────────────────────────────

class TestComputeDiscountPct:
    def test_standard_discount(self):
        result = compute_discount_pct(80000.0, 100000.0)
        assert result == pytest.approx(20.0)

    def test_small_discount(self):
        result = compute_discount_pct(9500.0, 10000.0)
        assert result == pytest.approx(5.0)

    def test_no_discount_same_price(self):
        assert compute_discount_pct(100.0, 100.0) is None

    def test_current_higher_than_old(self):
        assert compute_discount_pct(110.0, 100.0) is None

    def test_none_current(self):
        assert compute_discount_pct(None, 100.0) is None

    def test_none_old(self):
        assert compute_discount_pct(80.0, None) is None

    def test_zero_old_price(self):
        assert compute_discount_pct(80.0, 0.0) is None

    def test_large_discount(self):
        result = compute_discount_pct(50000.0, 200000.0)
        assert result == pytest.approx(75.0)

    def test_rounding(self):
        result = compute_discount_pct(33333.0, 100000.0)
        assert result == pytest.approx(66.67, rel=0.01)


# ─────────────────────────────────────────────────────────────────────────────
# is_in_stock
# ─────────────────────────────────────────────────────────────────────────────

class TestIsInStock:
    def test_in_stock(self):
        assert is_in_stock("SKU.12383 - In Stock") is True

    def test_limited_stock(self):
        assert is_in_stock("SKU.12428 - Limited Stock (1 Left)") is True

    def test_out_of_stock(self):
        assert is_in_stock("SKU.99999 - Out of Stock") is False

    def test_empty_string(self):
        assert is_in_stock("") is True

    def test_none(self):
        assert is_in_stock(None) is True

    def test_case_insensitive(self):
        assert is_in_stock("SKU.12000 - out of stock") is False

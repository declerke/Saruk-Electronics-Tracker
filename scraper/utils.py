"""
Utility functions for Saruk scraper: price parsing and brand extraction.
"""

import re
from decimal import Decimal, InvalidOperation


KNOWN_BRANDS = [
    "Apple", "Samsung", "Lenovo", "HP", "Dell", "LG", "Sony", "Hisense", "TCL",
    "JBL", "Bose", "Sennheiser", "Xiaomi", "Infinix", "Tecno", "Itel", "Oppo",
    "Vivo", "Realme", "Huawei", "Nokia", "Motorola", "Asus", "Acer", "MSI",
    "Toshiba", "Fujitsu", "NEC", "Panasonic", "Sharp", "Philips", "Canon",
    "Nikon", "Fujifilm", "GoPro", "DJI", "Epson", "Brother", "Logitech",
    "Razer", "Corsair", "SteelSeries", "Kingston", "Seagate", "Western",
    "Sandisk", "Transcend", "Tenda", "TP-Link", "Netgear", "D-Link",
    "Ubiquiti", "Mikrotik", "Cisco", "Anker", "Belkin", "Baseus",
    "Havit", "Redragon", "HyperX", "Creative", "Harman", "Marshall",
    "Yamaha", "Denon", "Marantz", "Polk", "Klipsch", "Edifier",
    "ViewSonic", "BenQ", "AOC", "Iiyama", "Samsung", "Gigabyte",
    "Seagate", "Crucial", "PNY", "ADATA", "Verbatim",
]

BRAND_LOOKUP = {b.lower(): b for b in KNOWN_BRANDS}


def extract_brand(product_name: str) -> str | None:
    """
    Extract brand from product name by matching against a known brand list.
    Checks first word, then scans all words for a brand match.
    """
    if not product_name:
        return None

    words = product_name.split()
    # Check first word
    if words:
        first = words[0].lower()
        if first in BRAND_LOOKUP:
            return BRAND_LOOKUP[first]

    # Scan all words
    for word in words:
        clean = word.strip("(),.-").lower()
        if clean in BRAND_LOOKUP:
            return BRAND_LOOKUP[clean]

    # Try two-word combos (e.g. "Western Digital")
    for i in range(len(words) - 1):
        combo = (words[i] + " " + words[i + 1]).lower()
        if combo in BRAND_LOOKUP:
            return BRAND_LOOKUP[combo]

    return None


def parse_price(price_text: str) -> float | None:
    """
    Parse a price string like 'KES 21,999.00' or '21,999' into a float.
    Returns None if parsing fails.
    """
    if not price_text:
        return None

    cleaned = re.sub(r"[^\d.,]", "", price_text.strip())
    # Remove thousands separator commas (but keep decimal dot)
    # Pattern: comma followed by exactly 3 digits and end or another separator
    cleaned = cleaned.replace(",", "")

    try:
        return float(Decimal(cleaned))
    except (InvalidOperation, ValueError):
        return None


def compute_discount_pct(current: float | None, old: float | None) -> float | None:
    """
    Compute discount percentage from current and old prices.
    Returns None if inputs are invalid.
    """
    if current is None or old is None:
        return None
    if old <= 0 or current <= 0:
        return None
    if current >= old:
        return None
    return round((old - current) / old * 100, 2)


def is_in_stock(stock_text: str) -> bool:
    """
    Determine stock status from text like:
    - 'SKU.12383 - In Stock'
    - 'SKU.12428 - Limited Stock (1 Left)'
    - 'SKU.xxxxx - Out of Stock'
    """
    if not stock_text:
        return True  # default to in-stock when unknown
    lower = stock_text.lower()
    if "out of stock" in lower:
        return False
    return True

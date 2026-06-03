"""
Saruk Electronics Price Tracker — Playwright headless scraper.

Saruk (saruk.co.ke) is a Next.js client-side rendered app. Products load
dynamically so requests + BeautifulSoup cannot see them. This scraper uses
Playwright with Chromium to render each category page, scroll to trigger
infinite-load, extract product cards, then INSERT rows into PostgreSQL.

Design: time-series INSERT (never UPSERT) to build price history over time.
"""

import asyncio
import logging
import os
import random
from datetime import date, datetime, timezone
from typing import Any

import psycopg2
import psycopg2.extras
from playwright.async_api import async_playwright, Page, Browser

from scraper.utils import extract_brand, parse_price, compute_discount_pct, is_in_stock

logger = logging.getLogger(__name__)

BASE_URL = "https://saruk.co.ke"

# Categories discovered by visiting saruk.co.ke and reading the nav menu
CATEGORIES = [
    {"name": "Laptops", "url": "/laptops"},
    {"name": "Phones & Tablets", "url": "/phones-and-tablets"},
    {"name": "TVs & Accessories", "url": "/tvs-and-accessories"},
    {"name": "Audio Devices", "url": "/audio-devices"},
    {"name": "Desktops", "url": "/desktops"},
    {"name": "Monitors & Accessories", "url": "/monitors-and-accessories"},
    {"name": "Gaming Essentials", "url": "/gaming-essentials"},
    {"name": "Wearables", "url": "/wearables"},
    {"name": "Networking & Smart Home", "url": "/networking-and-smart-home"},
    {"name": "Cameras & Photography", "url": "/cameras-and-photography"},
    {"name": "Storage Devices", "url": "/storage-devices"},
    {"name": "Computing Accessories", "url": "/accessories-for-laptops-and-desktops"},
    {"name": "Smartphone Accessories", "url": "/accessories-for-smartphones"},
    {"name": "Home Entertainment", "url": "/home-entertainment"},
    {"name": "All In Ones", "url": "/all-in-ones"},
    {"name": "Projectors & Accessories", "url": "/projectors-and-accessories"},
    {"name": "Laptop Bags", "url": "/laptop-bags"},
    {"name": "Office Electronics", "url": "/office-electronics"},
    {"name": "Apple Store", "url": "/apple-store"},
    {"name": "Laptop Parts & Maintenance", "url": "/laptop-parts-and-maintenance"},
    {"name": "Phone Parts & Maintenance", "url": "/phone-parts-and-maintenance"},
    {"name": "Servers & Accessories", "url": "/servers-and-accessories"},
]

USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
    "AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/124.0.0.0 Safari/537.36"
)

# How many scroll iterations to do per category page (each scroll loads ~30 more)
# Kept at 3 to limit Playwright memory usage in Docker; increase for deeper scraping
MAX_SCROLL_ITERATIONS = 3

DB_CONFIG = {
    "host": os.getenv("APP_DB_HOST", "localhost"),
    "port": int(os.getenv("APP_DB_PORT", "5433")),
    "dbname": os.getenv("APP_DB_NAME", "saruk_db"),
    "user": os.getenv("APP_DB_USER", "postgres"),
    "password": os.getenv("APP_DB_PASSWORD", "postgres"),
}


def get_db_connection():
    """Return a live psycopg2 connection to the app PostgreSQL database."""
    return psycopg2.connect(**DB_CONFIG)


def ensure_schema(conn) -> None:
    """Create raw schema and table if they don't exist."""
    with conn.cursor() as cur:
        cur.execute("CREATE SCHEMA IF NOT EXISTS raw;")
        cur.execute("""
            CREATE TABLE IF NOT EXISTS raw.saruk_products (
                product_id      SERIAL PRIMARY KEY,
                product_name    VARCHAR(500) NOT NULL,
                category        VARCHAR(100),
                brand           VARCHAR(100),
                current_price_kes NUMERIC(12,2),
                old_price_kes   NUMERIC(12,2),
                discount_pct    NUMERIC(5,2),
                in_stock        BOOLEAN DEFAULT TRUE,
                product_url     TEXT,
                scraped_at      TIMESTAMPTZ DEFAULT NOW(),
                scrape_date     DATE DEFAULT CURRENT_DATE
            );
        """)
        conn.commit()
    logger.info("Schema and table verified.")


def insert_products(conn, products: list[dict]) -> int:
    """
    INSERT all products into raw.saruk_products.
    Time-series design: always INSERT, never upsert — every run creates
    new rows so price history accumulates over time.
    """
    if not products:
        return 0

    sql = """
        INSERT INTO raw.saruk_products
            (product_name, category, brand, current_price_kes, old_price_kes,
             discount_pct, in_stock, product_url, scraped_at, scrape_date)
        VALUES %s
    """
    now = datetime.now(timezone.utc)
    today = date.today()

    rows = []
    for p in products:
        rows.append((
            p["product_name"],
            p["category"],
            p["brand"],
            p["current_price_kes"],
            p["old_price_kes"],
            p["discount_pct"],
            p["in_stock"],
            p["product_url"],
            now,
            today,
        ))

    with conn.cursor() as cur:
        psycopg2.extras.execute_values(cur, sql, rows)
    conn.commit()
    return len(rows)


async def scroll_to_load_all(page: Page, category_name: str) -> None:
    """
    Scroll to the bottom of the page repeatedly to trigger infinite scroll.
    Stops when no new products load after a scroll.
    """
    previous_count = 0
    for iteration in range(MAX_SCROLL_ITERATIONS):
        await page.evaluate("window.scrollTo(0, document.body.scrollHeight)")
        await asyncio.sleep(random.uniform(1, 2))

        current_count = await page.evaluate(
            "document.querySelectorAll('a[href*=\"/product/\"]').length"
        )
        logger.info(
            "[%s] Scroll %d: %d products loaded", category_name, iteration + 1, current_count
        )

        if current_count == previous_count:
            logger.info("[%s] No new products loaded — reached end of list.", category_name)
            break
        previous_count = current_count


async def extract_products_from_page(page: Page, category_name: str) -> list[dict]:
    """
    Extract all product cards from the current page DOM.
    Returns a list of product dicts.
    """
    products_js = await page.evaluate("""
        () => {
            const results = [];
            const cards = document.querySelectorAll('a[href*="/product/"]');

            cards.forEach(card => {
                const wrapper = card.closest('[class*="wrapper"]') || card.parentElement;
                if (!wrapper) return;

                // Product name — paragraph inside the link
                const nameEl = card.querySelector('p');
                const productName = nameEl ? nameEl.textContent.trim() : '';
                if (!productName) return;

                // Product URL
                const productUrl = card.getAttribute('href') || '';

                // Prices — look for Currency module classes
                const priceEls = wrapper.querySelectorAll('[class*="Price"], [class*="price"]');
                const prices = Array.from(priceEls).map(el => el.textContent.trim());

                // Stock text — look for SKU div
                const allDivs = wrapper.querySelectorAll('div, span, p');
                let stockText = '';
                for (const el of allDivs) {
                    const t = el.textContent.trim();
                    if (t.startsWith('SKU.') || t.includes('In Stock') || t.includes('Out of Stock')) {
                        stockText = t;
                        break;
                    }
                }

                // Badge (Brand New, etc.)
                const badgeEl = wrapper.querySelector('[class*="badge"], [class*="Badge"], [class*="tag"], [class*="Tag"]');
                const badge = badgeEl ? badgeEl.textContent.trim() : '';

                results.push({
                    product_name: productName,
                    product_url: productUrl,
                    prices: prices,
                    stock_text: stockText,
                    badge: badge
                });
            });

            // Deduplicate by product_url
            const seen = new Set();
            return results.filter(p => {
                if (seen.has(p.product_url)) return false;
                seen.add(p.product_url);
                return true;
            });
        }
    """)

    parsed = []
    for raw in products_js:
        name = raw.get("product_name", "").strip()
        if not name:
            continue

        url = BASE_URL + raw.get("product_url", "")
        stock_text = raw.get("stock_text", "")
        prices = raw.get("prices", [])

        # Parse prices — first price is current, second (if present) is old
        current_price = parse_price(prices[0]) if len(prices) > 0 else None
        old_price = parse_price(prices[1]) if len(prices) > 1 else None

        discount_pct = compute_discount_pct(current_price, old_price)

        brand = extract_brand(name)
        in_stock = is_in_stock(stock_text)

        parsed.append({
            "product_name": name,
            "category": category_name,
            "brand": brand,
            "current_price_kes": current_price,
            "old_price_kes": old_price,
            "discount_pct": discount_pct,
            "in_stock": in_stock,
            "product_url": url,
        })

    return parsed


async def scrape_category(browser: Browser, category: dict, conn) -> int:
    """
    Scrape a single category page. Opens a new browser context for isolation.
    Returns number of products inserted.
    """
    category_name = category["name"]
    category_url = BASE_URL + category["url"]
    logger.info("Scraping category: %s — %s", category_name, category_url)

    try:
        context = await browser.new_context(user_agent=USER_AGENT)
        page = await context.new_page()
        await page.goto(category_url, wait_until="domcontentloaded", timeout=30000)

        # Wait for product cards to appear
        try:
            await page.wait_for_selector('a[href*="/product/"]', timeout=15000)
        except Exception:
            logger.warning("[%s] No product links found — skipping.", category_name)
            return 0

        # Rate limit before scrolling
        await asyncio.sleep(random.uniform(1, 2))

        # Scroll to load all infinite-scroll pages
        await scroll_to_load_all(page, category_name)

        # Extract products
        products = await extract_products_from_page(page, category_name)
        logger.info("[%s] Extracted %d products.", category_name, len(products))

        if products:
            inserted = insert_products(conn, products)
            logger.info("[%s] Inserted %d rows.", category_name, inserted)
            return inserted

        return 0

    except Exception as exc:
        logger.error("[%s] Error during scraping: %s", category_name, exc, exc_info=True)
        return 0
    finally:
        await context.close()


CHROMIUM_ARGS = [
    "--no-sandbox",
    "--disable-dev-shm-usage",
    "--disable-gpu",
    "--disable-extensions",
]


async def run_scraper() -> dict[str, int]:
    """
    Main entry point. Launches a fresh Playwright browser per category to avoid
    OOM-kill cascades — if one Chromium dies, the next category still succeeds.
    Returns summary dict: {category_name: count}.
    """
    logger.info("Starting Saruk price tracker scrape.")
    conn = get_db_connection()
    ensure_schema(conn)

    summary: dict[str, int] = {}

    async with async_playwright() as pw:
        for category in CATEGORIES:
            # Fresh browser per category — isolates memory, prevents cascade failures
            browser = None
            try:
                browser = await pw.chromium.launch(
                    headless=True,
                    args=CHROMIUM_ARGS,
                )
                count = await scrape_category(browser, category, conn)
                summary[category["name"]] = count
            except Exception as exc:
                logger.error("[%s] Browser-level error: %s", category["name"], exc)
                summary[category["name"]] = 0
            finally:
                if browser:
                    try:
                        await browser.close()
                    except Exception:
                        pass
            # Rate limit between categories
            await asyncio.sleep(random.uniform(1, 2))

    conn.close()
    logger.info("Scrape complete. Summary: %s", summary)
    return summary


def main() -> dict[str, int]:
    """Synchronous wrapper for Airflow PythonOperator."""
    return asyncio.run(run_scraper())


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    result = main()
    print("Scrape summary:", result)

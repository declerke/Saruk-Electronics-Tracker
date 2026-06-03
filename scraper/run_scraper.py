"""
Standalone entry point for the Saruk scraper.
Called by the Airflow DAG via subprocess to avoid asyncio/fork issues.

Usage: python scraper/run_scraper.py
"""

import logging
import sys
from pathlib import Path

# Ensure the project root is on sys.path
sys.path.insert(0, str(Path(__file__).parent.parent))

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)-8s %(name)s: %(message)s",
)

from scraper.saruk_scraper import main  # noqa: E402

if __name__ == "__main__":
    result = main()
    total = sum(result.values())
    print(f"Scrape complete. Total inserted: {total}")
    for category, count in sorted(result.items()):
        print(f"  {category:<35} {count:4d} products")
    sys.exit(0)

# Saruk Electronics Price Tracker

Daily Playwright-powered price tracker for Kenya's Saruk electronics store — scrapes every category, stores time-series price history in PostgreSQL, transforms it with dbt, and visualises trends in Grafana.

---

## Architecture

```
saruk.co.ke (Next.js SPA)
       |
       v
  [Playwright]  — headless Chromium, scrolls infinite-load pages
       |
       v
 [PostgreSQL]   — raw.saruk_products (append-only time-series INSERT)
       |
       v
    [dbt]       — staging view + 3 mart tables
       |
       v
  [Grafana]     — provisioned dashboards: price trends, drop alerts, stock status

All orchestrated by Airflow 3.0 @daily DAG
```

---

## Key Design Decisions

| Decision | Rationale |
|---|---|
| **Playwright over requests** | Saruk is a Next.js SPA — server-side rendering returns empty product arrays; only a real browser can render the DOM |
| **Time-series INSERT over UPSERT** | Append-only design enables price trend analysis across multiple scrape dates; every run is a new snapshot |
| **PostgreSQL over DuckDB** | Native Grafana connector without requiring community plugins; supports concurrent writes from Airflow |
| **Grafana over Superset** | Ideal for time-series price monitoring with built-in alerting, sub-second refresh, and provisioned dashboards |

---

## Tech Stack

| Component | Technology | Role |
|---|---|---|
| Orchestration | Apache Airflow 3.0 | @daily DAG — scrape → dbt run → dbt test → summary |
| Scraper | Playwright 1.44 + Chromium | Headless browser scraping of Next.js SPA |
| Database | PostgreSQL 15 | Raw ingestion + dbt-transformed marts |
| Transformation | dbt-postgres 1.8 | Staging view, fact table, 2 mart tables |
| Visualisation | Grafana (provisioned) | Price trends, drop alerts, stock status |
| Containerisation | Docker + Docker Compose | Full stack — two Postgres instances, Airflow, Grafana |
| Testing | pytest 8.2 | Unit tests for scraper utility functions |
| CI Security | pip-audit via GitHub Actions | Dependency vulnerability scanning |

---

## Data Schema

### raw.saruk_products (source table)

| Column | Type | Description |
|---|---|---|
| product_id | SERIAL | Auto-incrementing primary key |
| product_name | VARCHAR(500) | Full product name as listed on saruk.co.ke |
| category | VARCHAR(100) | Category e.g. Laptops, Phones & Tablets |
| brand | VARCHAR(100) | Extracted brand name |
| current_price_kes | NUMERIC(12,2) | Selling price in Kenya Shillings at scrape time |
| old_price_kes | NUMERIC(12,2) | Original listed price (when on sale) |
| discount_pct | NUMERIC(5,2) | Computed discount percentage |
| in_stock | BOOLEAN | Stock availability at scrape time |
| product_url | TEXT | Full URL to product page |
| scraped_at | TIMESTAMPTZ | UTC timestamp of scrape |
| scrape_date | DATE | Calendar date of scrape (partition key) |

### dbt Models

| Model | Schema | Materialization | Description |
|---|---|---|---|
| stg_saruk_products | staging | View | Cleaned and type-cast staging layer |
| fct_price_history | marts | Table | Full time-series; one row per product per date |
| mart_latest_prices | marts | Table | Most recent price per unique product |
| mart_price_changes | marts | Table | Price deltas using LAG() across scrape dates |

---

## Pipeline Flow

1. Airflow schedules the `saruk_price_tracker` DAG at `@daily`
2. `scrape_saruk` task: Playwright launches headless Chromium, visits each of 22 category pages, scrolls infinite-load, extracts product cards, inserts rows into `raw.saruk_products`
3. `run_dbt_models` task: runs `dbt run` — staging view + 3 mart tables are created/refreshed
4. `run_dbt_tests` task: runs `dbt test` — not_null, accepted_values, expression_is_true assertions
5. `log_summary` task: queries PostgreSQL and logs product counts by category and date

---

## dbt Models

| Model | Layer | Description | Tests |
|---|---|---|---|
| stg_saruk_products | Staging (view) | Type-cast and filtered raw data | not_null on name/price/date/category; accepted_values on category; price > 0 |
| fct_price_history | Marts (table) | Full time-series with `days_on_market` derived column | not_null on name/price/date |
| mart_latest_prices | Marts (table) | Latest price snapshot per product URL (ROW_NUMBER window) | not_null on name/price/as_of_date |
| mart_price_changes | Marts (table) | LAG-based price delta table with change_direction | accepted_values: up/down/new/unchanged |

---

## Test Coverage

| Suite | Count | Command |
|---|---|---|
| pytest (scraper utils) | 36/36 passing | `pytest tests/ -v` |
| dbt tests | 13/13 passing | `dbt test` |

---

## Setup & Running

### Prerequisites
- Docker Desktop (with Compose v2)
- 4 GB RAM allocated to Docker

### Clone and configure

```bash
git clone https://github.com/declerke/Saruk-Electronics-Tracker.git
cd Saruk-Electronics-Tracker
cp .env.example .env
```

### Build and start

```bash
docker-compose build
docker-compose up -d
```

### Wait for Airflow to initialise (~60 seconds), then trigger the DAG

```bash
docker-compose exec airflow-webserver airflow dags trigger saruk_price_tracker
```

### Access services

| Service | URL | Credentials |
|---|---|---|
| Airflow | http://localhost:8082 | admin / admin123 |
| Grafana | http://localhost:3000 | admin / admin |
| PostgreSQL (app) | localhost:5433 | postgres / postgres |
| PostgreSQL (Airflow meta) | localhost:5438 | airflow / airflow |

### Verify data

```bash
docker-compose exec postgres psql -U postgres -d saruk_db \
  -c "SELECT category, COUNT(*) FROM raw.saruk_products GROUP BY category ORDER BY 2 DESC;"
```

---

## Sample Output

| product_name | category | current_price_kes | scrape_date |
|---|---|---|---|
| HP OmniBook 5 LaptopAI 16-AF1017wm Intel Core Ultra 7 255U | Laptops | 112,999.00 | 2026-06-03 |
| Lenovo ThinkPad X1 Yoga G2 Intel Core i5-7500U 8GB 256GB | Laptops | 29,999.00 | 2026-06-03 |
| Samsung 55" Crystal UHD Signage QMC Tizen OS Ultra-Slim | Monitors & Accessories | 114,999.00 | 2026-06-03 |
| Dell S2421HN 23.8" FHD 75Hz IPS Ultra-Thin Bezel Monitor | Monitors & Accessories | 27,999.00 | 2026-06-03 |
| Samsung 27" QHD ViewFinity S6 S60D Monitor | Monitors & Accessories | 54,999.00 | 2026-06-03 |

---

## Skills Demonstrated

- **Playwright** headless browser automation for Next.js SPA scraping
- **Airflow 3.0** `@daily` DAG scheduling with task dependency chains
- **dbt-postgres** time-series data modelling with LAG(), ROW_NUMBER(), window functions
- **Grafana** provisioned dashboards — datasources, panels, and alerts configured as code
- **PostgreSQL** schema design for append-only time-series price intelligence
- **Docker / Docker Compose** multi-service orchestration (Airflow + 2x Postgres + Grafana)
- **pytest** unit testing of scraper utility functions
- **Price intelligence** — discount detection, price trend analysis, drop alerting
- **Next.js scraping** — handling CSR-only SPAs with infinite scroll

---

## Project Stats

| Metric | Value |
|---|---|
| Products scraped (first run, 9/22 categories) | 1,167 raw rows |
| Unique products in mart_latest_prices | 522 |
| Categories covered | 22 |
| dbt models | 4 (1 staging view + 3 mart tables) |
| dbt tests passing | 13/13 |
| pytest passing | 36/36 |
| Grafana dashboards | 1 (4 panels) |

---

## License

MIT License — see [LICENSE](LICENSE) for details.

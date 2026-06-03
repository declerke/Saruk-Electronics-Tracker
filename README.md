# 🛒 Saruk Electronics Price Tracker: Daily Price Intelligence Pipeline for Kenya's Electronics Market

**Saruk Electronics Price Tracker** is a production-grade price intelligence pipeline that scrapes every product across all 22 categories on saruk.co.ke — Kenya's dedicated electronics retailer — using Playwright headless Chromium to render the Next.js client-side SPA, builds an append-only time-series price history in PostgreSQL, transforms it through a dbt modelling layer with LAG-based price change detection and ROW_NUMBER latest-price windowing, and surfaces price trends, drop alerts, and stock status across a provisioned Grafana dashboard — the complete analytical stack a retail analyst or procurement team would use to monitor Kenya's electronics pricing in real time.

| Metric | Value |
|--------|-------|
| Raw rows (first run, all 22 categories) | 1,861 |
| Unique products in mart_latest_prices | 1,788 |
| Categories scraped | 22 |
| Airflow tasks | 4 (scrape → dbt run → dbt test → summary) |
| dbt models | 4 (1 staging view · 3 mart tables) |
| dbt tests | 13 (all passing) |
| pytest tests | 36 (all passing) |
| Grafana dashboard panels | 4 |
| Cost to run | $0 — public website + local stack only |

---

## 🎯 Project Goal

Electronics pricing in Kenya is volatile — the same laptop can swing thousands of shillings week to week across retailers, and consumers and procurement teams have no structured way to monitor those movements. Saruk (saruk.co.ke) is one of Kenya's largest dedicated electronics stores, covering 22 product categories from laptops and phones through servers, cameras, and smart home devices. The site is built on Next.js with client-side rendering, meaning the product catalogue is invisible to conventional scrapers — only a real browser that executes JavaScript and triggers infinite scroll can see the actual product listings.

Saruk Electronics Price Tracker solves this by running Playwright headless Chromium daily against every category, storing each scrape as an immutable time-series snapshot in PostgreSQL rather than overwriting existing rows, and building a dbt model layer that reconstructs the full price history per product, identifies the latest price per unique URL using ROW_NUMBER window partitioning, and detects price movements using LAG across consecutive scrape dates. The result is a Grafana dashboard that shows average pricing by category over 30 days, flags products whose price has dropped more than 5% in the last 7 days, and tracks stock status — giving retail analysts a complete, automated view of Kenya's electronics market at zero ongoing cost.

---

## 🧬 System Architecture

1. **Scraping — Playwright Headless Chromium** — `scraper/saruk_scraper.py` launches a fresh Chromium browser per category using Playwright's async API; each category runs in an isolated browser context to prevent memory leaks from cascading across 22 categories; the scraper navigates to each category URL, waits for `a[href*="/product/"]` selectors to appear (confirming React has hydrated), scrolls three times to trigger infinite-load pagination, then evaluates a JavaScript `querySelectorAll` block inside the browser to extract product names, prices, URLs, and stock text directly from the rendered DOM; products are deduplicated by URL within each page before returning to Python for brand extraction, price parsing, and discount computation

2. **Brand and price extraction — `scraper/utils.py`** — `extract_brand()` scans each word in the product name against a 63-entry `BRAND_LOOKUP` dict (case-insensitive, punctuation-stripped) and tries two-word combos for brands like "Western Digital"; `parse_price()` strips all non-numeric characters with `re.sub`, removes comma separators, and calls `float()` directly — no intermediate `Decimal` conversion; `compute_discount_pct()` derives discount from current and old prices where both are non-null and old > current; `is_in_stock()` reads the SKU text block for "out of stock" case-insensitively

3. **PostgreSQL raw layer — append-only time-series** — `raw.saruk_products` receives a new INSERT batch on every DAG run; the table is never updated or truncated — each scrape date creates a new set of rows so the full price history accumulates over time; `psycopg2.extras.execute_values` batches the INSERT for efficiency; `scraped_at` (TIMESTAMPTZ) and `scrape_date` (DATE) are both recorded so analysts can query by calendar day or exact timestamp

4. **dbt transformation layer — 4 models** — `stg_saruk_products` (view) casts and cleans the raw layer, resolving brand via a SQL CASE fallback for any rows where the Python extractor returned NULL; `fct_price_history` (table) adds `days_on_market` (days since product first appeared), `previous_price_kes` via `LAG()` partitioned by `product_url` and ordered by `scrape_date`, `price_direction` (up/down/unchanged/null), and `rn_latest` (ROW_NUMBER descending by scrape_date) — the fact table is the single source of truth for all downstream marts; `mart_latest_prices` filters to `rn_latest = 1` to give the current price per product; `mart_price_changes` filters to rows where the price changed (or is new) and orders by absolute percentage change

5. **Grafana dashboard — provisioned as code** — datasource and dashboard are declared in `grafana/provisioning/` YAML and JSON files and loaded automatically on container start; the PostgreSQL datasource uses the Grafana 13 plugin (`grafana-postgresql-datasource`) with `database` declared in both the top-level field and `jsonData.database` (required in Grafana 13); the dashboard contains 4 panels: a time series panel for 30-day average price by category, a table panel for price drop alerts (>5% drop in 7 days), a bar gauge for stock status, and a stat panel for total product count

6. **Airflow 3.0 orchestration — 4-task @daily DAG** — `dags/saruk_pipeline.py` uses `BashOperator` for the scraper task rather than `PythonOperator` because Playwright's async event loop conflicts with Airflow 3.0's Task SDK event loop when run inside a `PythonOperator` callable; `run_dbt_models` and `run_dbt_tests` also use `BashOperator` invoking `dbt run` and `dbt test` directly; `log_summary` is a `PythonOperator` that queries PostgreSQL and logs daily product counts per category to the Airflow task log

---

## 🛠️ Technical Stack

| **Layer** | **Tool** | **Version** |
|---|---|---|
| Orchestration | Apache Airflow (LocalExecutor, AIP-72) | 3.0 |
| Scraper | Playwright + Chromium | 1.44.0 |
| Database | PostgreSQL | 15 |
| Transformation | dbt-postgres | 1.8 |
| Visualisation | Grafana | 13.0.2 |
| Containerisation | Docker Compose (7 services) | — |
| Testing | pytest | 8.2.2 |
| CI Security | pip-audit via GitHub Actions | — |
| Language | Python | 3.11 |

---

## 📊 Performance & Results

- **1,861 raw rows** inserted across all 22 categories on the first full pipeline run — categories range from 120 rows (Cameras, Apple Store, Office Electronics, Smartphone Accessories) to 27 rows (Laptop Bags) depending on catalogue depth
- **Full 4-task pipeline** completes in approximately **35 minutes** end-to-end — the Playwright scraper accounts for ~30 minutes (22 categories × 3 scroll iterations with rate-limiting delays); dbt run and test complete in under 30 seconds
- **1,788 unique products** tracked in `mart_latest_prices` after the first run; the gap between 1,861 raw rows and 1,788 mart rows reflects deduplication by `product_url` in the `rn_latest = 1` filter
- **dbt test suite (13 tests)** passes in under 10 seconds — `not_null` on product name, price, and scrape date; `accepted_values` on category names; `expression_is_true` for price > 0
- **36 pytest unit tests** all passing — 9 tests for `parse_price` covering KES-formatted strings, comma separators, and null inputs; 12 tests for `extract_brand` across Kenyan-market brands (Infinix, Tecno, Hisense); 9 tests for `compute_discount_pct`; 6 tests for `is_in_stock` including case-insensitive "out of stock" detection
- **Grafana price drop alert panel** populates after the second daily run when `LAG()` has a previous price to compare — on first run all `previous_price_kes` are NULL and the panel correctly shows no alerts

---

## 📸 Dashboard

### Grafana — Price Tracker Dashboard

![Grafana Dashboard](assets/grafana%20dashboard.png)

*Price Overview (30-day avg KES by category), Stock Status bar gauge, and Total Products Tracked stat panel. Price Drop Alerts panel populates after the second daily scrape when LAG() detects movements.*

### Airflow — Successful DAG Runs

![Airflow DAG](assets/succesful%20dag%20runs.png)

*`saruk_price_tracker` DAG — all 4 tasks completing successfully: `scrape_saruk` → `run_dbt_models` → `run_dbt_tests` → `log_summary`. BashOperator used throughout to avoid asyncio/fork conflicts with Airflow 3.0 Task SDK.*

---

## 📑 Categories Scraped

| Category | Products (first run) | Avg Price (KES) |
|---|---|---|
| Laptop Parts & Maintenance | 120 | 7,753 |
| Smartphone Accessories | 120 | 1,737 |
| Phone Parts & Maintenance | 120 | 13,524 |
| Cameras & Photography | 120 | 144,940 |
| Apple Store | 120 | 111,507 |
| Office Electronics | 120 | 57,208 |
| Networking & Smart Home | 119 | 15,163 |
| Storage Devices | 119 | 10,255 |
| Wearables | 117 | 15,514 |
| Monitors & Accessories | 90 | 87,420 |
| Computing Accessories | 90 | 6,651 |
| Projectors & Accessories | 90 | 42,130 |
| Phones & Tablets | 89 | 52,746 |
| Desktops | 81 | 126,876 |
| All In Ones | 77 | 96,816 |
| Gaming Essentials | 76 | 22,201 |
| Home Entertainment | 47 | 40,414 |
| Laptops | 30 | — |
| TVs & Accessories | 30 | — |
| Audio Devices | 30 | 13,922 |
| Servers & Accessories | 29 | 190,523 |
| Laptop Bags | 27 | 1,918 |

---

## 🧠 Key Design Decisions

- **Playwright over requests + BeautifulSoup** — Saruk is built on Next.js with client-side rendering. A standard `requests.get()` call to any category URL returns the Next.js shell HTML — the React component tree has not executed and the product catalogue is completely absent from the response. BeautifulSoup parses an empty DOM and returns zero product cards. Playwright launches a real Chromium browser, waits for the `a[href*="/product/"]` selector to appear (confirming React has hydrated and the API call to Saruk's product endpoint has resolved), then scrolls to trigger infinite-load pagination — the only approach that can see the actual product listings.

- **Fresh browser per category, not per session** — the scraper launches a new Chromium process for each of the 22 categories rather than reusing a single browser across the full run. Playwright's headless Chromium in Docker accumulates memory across page navigations — by category 10 or 12, a single long-running browser instance may exceed Docker's available RAM and be OOM-killed by the kernel, taking the entire run with it. Launching fresh per category means each Chromium process starts at ~200 MB, completes its work, and exits cleanly; if one category fails, the remaining 21 continue unaffected.

- **Append-only time-series INSERT over UPSERT** — `raw.saruk_products` uses `SERIAL PRIMARY KEY` with a plain INSERT on every run — no `ON CONFLICT`, no `UPDATE`, no `DELETE`. This is a deliberate time-series design: every scrape creates a new row for every product, so the table accumulates a complete price history across dates. An UPSERT (overwrite on product URL conflict) would destroy the historical record and make price trend analysis, LAG-based change detection, and vintage curves impossible. The mart layer reconstructs "latest price" via ROW_NUMBER window functions rather than relying on the table to maintain current state.

- **LAG() for price change detection rather than self-joins** — `mart_price_changes` detects price movements by comparing each row's `current_price_kes` to `LAG(current_price_kes) OVER (PARTITION BY product_url ORDER BY scrape_date)` in `fct_price_history`. A self-join approach (joining the table to itself on `product_url` with date offsets) requires two full table scans and a join condition that breaks down when scrape dates are irregular. The LAG window function executes in a single pass over the already-partitioned fact table, is robust to gaps in scrape history, and produces a clean `previous_price_kes` column that all downstream aggregations can reference without additional joins.

- **PostgreSQL over DuckDB** — Grafana's native PostgreSQL plugin (`grafana-postgresql-datasource`) connects directly to a running PostgreSQL instance with no additional configuration beyond host, port, database, and credentials. DuckDB would require either the Grafana DuckDB community plugin (not available in Grafana's default plugin registry) or an intermediate API layer. PostgreSQL also supports concurrent write connections from multiple Airflow tasks without file-locking constraints, making it more suitable for a multi-service Docker Compose stack where the scheduler, workers, and summary task all need database access simultaneously.

- **BashOperator for scraper and dbt tasks** — Airflow 3.0's Task SDK runs each task inside an event loop managed by the execution API server. Playwright's async API (`async_playwright`) requires its own `asyncio` event loop, which conflicts with the existing loop inside a `PythonOperator` callable — the `asyncio.run()` call raises `RuntimeError: This event loop is already running`. Running the scraper via `BashOperator` as a subprocess (`python scraper/run_scraper.py`) gives Playwright a clean process with no pre-existing event loop. The same pattern applies to `dbt run` and `dbt test`, which are invoked as shell commands rather than Python API calls to avoid dbt's own import-time side effects on the Airflow task environment.

---

## 📂 Project Structure

```text
Saruk-Electronics-Tracker/
├── dags/
│   └── saruk_pipeline.py              # Airflow DAG — 4 tasks, @daily, BashOperator for Playwright + dbt
├── scraper/
│   ├── __init__.py
│   ├── saruk_scraper.py               # Playwright async scraper — fresh browser per category, infinite scroll
│   ├── run_scraper.py                 # Standalone entry point called by BashOperator
│   └── utils.py                       # parse_price, extract_brand, compute_discount_pct, is_in_stock
├── dbt/
│   ├── models/
│   │   ├── staging/
│   │   │   └── stg_saruk_products.sql # Type-cast + brand resolution fallback (COALESCE + SQL CASE)
│   │   ├── marts/
│   │   │   ├── fct_price_history.sql  # Time-series fact table — LAG(), ROW_NUMBER(), days_on_market
│   │   │   ├── mart_latest_prices.sql # Latest price per product URL (rn_latest = 1)
│   │   │   └── mart_price_changes.sql # Price delta detection ordered by ABS(price_change_pct)
│   │   └── schema.yml                 # 13 dbt tests — not_null, accepted_values, expression_is_true
│   ├── dbt_project.yml                # Project config — schema: public_marts for mart tables
│   ├── profiles.yml                   # PostgreSQL connection via APP_DB_* env vars
│   └── packages.yml                   # dbt-utils dependency
├── grafana/
│   └── provisioning/
│       ├── dashboards/
│       │   ├── dashboard.yml          # File provider config — 30s reload interval
│       │   └── saruk_dashboard.json   # 4-panel dashboard — price trends, drop alerts, stock, count
│       └── datasources/
│           └── postgres.yml           # grafana-postgresql-datasource — database in jsonData (Grafana 13)
├── tests/
│   └── test_scraper.py                # 36 pytest tests — parse_price, extract_brand, discount, stock
├── assets/
│   ├── grafana dashboard.png          # Grafana price tracker dashboard
│   └── succesful dag runs.png         # Airflow DAG — 4/4 tasks SUCCESS
├── .github/
│   └── workflows/
│       └── security.yml               # pip-audit dependency vulnerability scan on every push
├── Dockerfile                         # Airflow image — Playwright, dbt-postgres, psycopg2
├── docker-compose.yml                 # 7 services: 2× postgres, init, api-server, scheduler,
│                                      #   dag-processor, triggerer, grafana
├── requirements.txt                   # Local dev dependencies
├── .env.example                       # APP_DB_* and AIRFLOW__ env var template
└── .gitignore                         # .env, .venv/, dbt/target/, dbt/dbt_packages/
```

---

## ⚙️ Installation & Setup

### Prerequisites

- Docker Desktop (4 GB RAM allocated to Docker — Playwright Chromium is memory-intensive)
- Git

### Steps

1. **Clone the repository**
   ```bash
   git clone https://github.com/declerke/Saruk-Electronics-Tracker.git
   cd Saruk-Electronics-Tracker
   ```

2. **Configure environment**
   ```bash
   cp .env.example .env
   ```

3. **Build and start all services**
   ```bash
   docker compose up -d
   ```
   First build installs Playwright, Chromium, dbt-postgres, and all Airflow providers (~4–6 minutes).

4. **Wait for Airflow to initialise (~60 seconds)**
   ```bash
   docker compose logs -f airflow-scheduler
   # Wait until: "Scheduler started"
   ```

5. **Trigger the pipeline**

   Get a JWT token and trigger via the Airflow API:
   ```bash
   TOKEN=$(curl -s -X POST http://localhost:8082/auth/token \
     -H "Content-Type: application/json" \
     -d '{"username":"admin","password":"admin"}' | python3 -c "import sys,json; print(json.load(sys.stdin)['access_token'])")

   curl -X POST http://localhost:8082/api/v2/dags/saruk_price_tracker/dagRuns \
     -H "Authorization: Bearer $TOKEN" \
     -H "Content-Type: application/json" \
     -d '{"logical_date":"2026-06-01T00:00:00Z"}'
   ```

   Or use the Airflow UI at `http://localhost:8082` — trigger the `saruk_price_tracker` DAG manually. The full pipeline takes approximately 35 minutes (Playwright scraping 22 categories).

6. **Access the stack**

   | Service | URL | Credentials |
   |---|---|---|
   | Grafana | http://localhost:3000 | admin / admin |
   | Airflow UI | http://localhost:8082 | admin / admin |
   | PostgreSQL (app data) | localhost:5433 | postgres / postgres |
   | PostgreSQL (Airflow meta) | localhost:5438 | airflow / airflow |

7. **Verify data**
   ```bash
   docker compose exec postgres psql -U postgres -d saruk_db \
     -c "SELECT category, COUNT(*) FROM raw.saruk_products GROUP BY category ORDER BY 2 DESC;"
   ```

---

## 🗄️ dbt Models

| Model | Layer | Type | Description |
|---|---|---|---|
| `stg_saruk_products` | Staging | View | Casts raw columns; resolves brand via `COALESCE(NULLIF(brand_raw,''), SQL CASE on first word)` — catches rows where Python extractor returned NULL |
| `fct_price_history` | Marts | Table | Full time-series fact table; adds `LAG(current_price_kes) OVER (PARTITION BY product_url ORDER BY scrape_date)` for previous price; `ROW_NUMBER() OVER (PARTITION BY product_url ORDER BY scrape_date DESC)` as `rn_latest`; `days_on_market` as days since product first appeared; `price_direction` (up/down/unchanged/null) |
| `mart_latest_prices` | Marts | Table | Filters `fct_price_history` to `rn_latest = 1` — one row per unique product URL at its most recent scrape date; primary source for Grafana's price overview and stock status panels |
| `mart_price_changes` | Marts | Table | Filters to rows where `previous_price_kes IS NULL OR current_price_kes <> previous_price_kes`; computes `price_change_kes`, `price_change_pct`, and `change_direction` (up/down/new); ordered by `ABS(price_change_pct) DESC` — source for Grafana's drop alerts panel |

**13 dbt tests — 13/13 PASS:**
- `not_null` on `product_name`, `current_price_kes`, `scrape_date`, `category` in staging and fact layers
- `accepted_values` on `category` (all 22 Saruk category names)
- `expression_is_true` asserting `current_price_kes > 0` across all layers
- `not_null` on `as_of_date` in `mart_latest_prices`
- `accepted_values` on `change_direction` (up / down / new / unchanged) in `mart_price_changes`

---

## 🎓 Skills Demonstrated

- **Playwright headless browser automation** — async Playwright with per-category browser isolation to prevent OOM cascades in Docker; `wait_for_selector` for React hydration detection; JavaScript `evaluate()` for DOM extraction from a Next.js SPA; infinite-scroll triggering via `window.scrollTo`

- **Apache Airflow 3.0 DAG design** — AIP-72 Task SDK operator imports (`airflow.providers.standard.operators.bash/python`); dag-processor as a separate required service in Airflow 3.0; `BashOperator` for subprocess isolation of Playwright's asyncio event loop; JWT authentication (`POST /auth/token`) replacing Airflow 2.x Basic Auth

- **Time-series data modelling** — append-only INSERT design for price history accumulation; LAG window function for price change detection across scrape dates; ROW_NUMBER with PARTITION BY for latest-price extraction without self-joins; `days_on_market` derived from `MIN(scrape_date) OVER (PARTITION BY product_url)`

- **dbt-postgres transformation layer** — 3-tier model architecture (staging → fact → mart); `COALESCE + NULLIF` brand resolution fallback; `schema: public_marts` configuration for mart separation from raw schema; 13 data quality tests including `accepted_values` on category enums and `expression_is_true` for price validation

- **Grafana provisioned dashboards** — datasource and dashboard declared as code in YAML/JSON provisioning files; Grafana 13 `grafana-postgresql-datasource` plugin with `jsonData.database` requirement; time series panel with `as_of_date::timestamptz` cast; bar gauge for multi-row table data; hardcoded datasource UID in panel definitions for reliable resolution

- **Docker Compose multi-service orchestration** — 7-service stack (2× PostgreSQL, airflow-init, api-server, scheduler, dag-processor, triggerer, Grafana); `service_completed_successfully` dependency on airflow-init; separate app and metadata PostgreSQL instances on different host ports (5433 and 5438); Playwright Chromium installed inside the Airflow image

- **Python unit testing** — 36 pytest tests across 4 utility functions; `pytest.approx` for floating-point price comparisons; edge case coverage for None inputs, empty strings, zero prices, and case-insensitive stock text; all tests runnable locally against `.venv` without Docker

- **Price intelligence analytics** — discount detection from current vs old price; brand extraction from unstructured product name strings against a 63-entry Kenya-market brand list; stock availability parsing from SKU text blocks; percentage price change computation with direction classification (up/down/new/unchanged)

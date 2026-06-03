"""
Saruk Electronics Price Tracker — Airflow 3.0 DAG.

Tasks (sequential):
  1. scrape_saruk     — BashOperator runs Playwright scraper as standalone script
  2. run_dbt_models   — BashOperator runs dbt run
  3. run_dbt_tests    — BashOperator runs dbt test
  4. log_summary      — PythonOperator queries PostgreSQL and logs summary

Using BashOperator for long-running subprocess tasks avoids asyncio/fork
interaction with the Airflow 3.0 task SDK event loop.
"""

from __future__ import annotations

import os
from datetime import datetime, timezone, timedelta

from airflow import DAG
from airflow.providers.standard.operators.bash import BashOperator
from airflow.providers.standard.operators.python import PythonOperator

DBT_DIR = "/opt/airflow/dbt"

default_args = {
    "owner": "airflow",
    "retries": 0,
    "depends_on_past": False,
}

AIRFLOW_ENV = (
    "APP_DB_HOST=${APP_DB_HOST:-postgres} "
    "APP_DB_PORT=${APP_DB_PORT:-5432} "
    "APP_DB_NAME=${APP_DB_NAME:-saruk_db} "
    "APP_DB_USER=${APP_DB_USER:-postgres} "
    "APP_DB_PASSWORD=${APP_DB_PASSWORD:-postgres} "
    "PYTHONPATH=/opt/airflow"
)


def _log_summary():
    """Query PostgreSQL and log product counts by category and scrape_date."""
    import logging
    import psycopg2

    logger = logging.getLogger(__name__)

    db_config = {
        "host": os.getenv("APP_DB_HOST", "postgres"),
        "port": int(os.getenv("APP_DB_PORT", "5432")),
        "dbname": os.getenv("APP_DB_NAME", "saruk_db"),
        "user": os.getenv("APP_DB_USER", "postgres"),
        "password": os.getenv("APP_DB_PASSWORD", "postgres"),
    }

    conn = psycopg2.connect(**db_config)
    try:
        with conn.cursor() as cur:
            import datetime as dt
            cur.execute("""
                SELECT category, COUNT(*) as cnt
                FROM raw.saruk_products
                WHERE scrape_date = CURRENT_DATE
                GROUP BY category
                ORDER BY cnt DESC;
            """)
            rows = cur.fetchall()
            logger.info("=== Today's Scrape Summary (%s) ===", dt.date.today())
            total = 0
            for category, cnt in rows:
                logger.info("  %-35s %4d products", category or "Uncategorized", cnt)
                total += cnt
            logger.info("  %-35s %4d products", "TOTAL", total)

            cur.execute("""
                SELECT scrape_date, COUNT(*) as daily_total
                FROM raw.saruk_products
                GROUP BY scrape_date
                ORDER BY scrape_date DESC
                LIMIT 7;
            """)
            history = cur.fetchall()
            logger.info("=== Recent Scrape History ===")
            for d, cnt in history:
                logger.info("  %s  %d products", d, cnt)
    finally:
        conn.close()


with DAG(
    dag_id="saruk_price_tracker",
    description="Daily Saruk electronics price tracker: scrape → dbt → Grafana",
    schedule="@daily",
    start_date=datetime(2026, 6, 1, tzinfo=timezone.utc),
    catchup=False,
    default_args=default_args,
    tags=["saruk", "price-tracker", "ecommerce"],
) as dag:

    scrape_task = BashOperator(
        task_id="scrape_saruk",
        bash_command=(
            f"{AIRFLOW_ENV} "
            "python /opt/airflow/scraper/run_scraper.py"
        ),
        execution_timeout=timedelta(minutes=30),
    )

    dbt_run_task = BashOperator(
        task_id="run_dbt_models",
        bash_command=(
            f"dbt run "
            f"--profiles-dir {DBT_DIR} "
            f"--project-dir {DBT_DIR}"
        ),
        execution_timeout=timedelta(minutes=15),
    )

    dbt_test_task = BashOperator(
        task_id="run_dbt_tests",
        bash_command=(
            f"dbt test "
            f"--profiles-dir {DBT_DIR} "
            f"--project-dir {DBT_DIR}"
        ),
        execution_timeout=timedelta(minutes=10),
    )

    summary_task = PythonOperator(
        task_id="log_summary",
        python_callable=_log_summary,
        execution_timeout=timedelta(minutes=5),
    )

    scrape_task >> dbt_run_task >> dbt_test_task >> summary_task

-- Fact table: full time-series price history.
-- One row per product per scrape_date.
-- days_on_market measures how long the product has been tracked.

WITH base AS (
    SELECT
        product_id,
        product_name,
        category,
        brand,
        current_price_kes,
        old_price_kes,
        discount_pct,
        in_stock,
        product_url,
        scraped_at,
        scrape_date
    FROM {{ ref('stg_saruk_products') }}
),

with_history AS (
    SELECT
        *,
        -- Days since product first appeared in the tracker
        (CURRENT_DATE - MIN(scrape_date) OVER (
            PARTITION BY product_url
        )) AS days_on_market,

        -- Previous scrape price for change tracking
        LAG(current_price_kes) OVER (
            PARTITION BY product_url
            ORDER BY scrape_date
        ) AS previous_price_kes,

        -- Row number for latest-price queries
        ROW_NUMBER() OVER (
            PARTITION BY product_url
            ORDER BY scrape_date DESC, scraped_at DESC
        ) AS rn_latest
    FROM base
)

SELECT
    product_id,
    product_name,
    category,
    brand,
    current_price_kes,
    old_price_kes,
    discount_pct,
    in_stock,
    product_url,
    scraped_at,
    scrape_date,
    days_on_market,
    previous_price_kes,
    CASE
        WHEN previous_price_kes IS NULL     THEN NULL
        WHEN current_price_kes > previous_price_kes  THEN 'up'
        WHEN current_price_kes < previous_price_kes  THEN 'down'
        ELSE 'unchanged'
    END AS price_direction,
    rn_latest
FROM with_history

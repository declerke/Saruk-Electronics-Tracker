-- Most recent price per product.
-- Uses ROW_NUMBER() OVER PARTITION BY product_url to pick the latest row.
-- This is the primary source for Grafana dashboards.

SELECT
    product_name,
    category,
    brand,
    current_price_kes,
    old_price_kes,
    discount_pct,
    in_stock,
    product_url,
    scrape_date AS as_of_date
FROM {{ ref('fct_price_history') }}
WHERE rn_latest = 1

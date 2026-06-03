-- Price change detection: products where price changed vs prior scrape_date.
-- Only includes rows with a known previous price (at least 2 scrapes of that product).
-- change_direction: 'up' | 'down' | 'new' (first time seen).

WITH changes AS (
    SELECT
        product_name,
        category,
        brand,
        product_url,
        previous_price_kes                         AS previous_price,
        current_price_kes                          AS current_price,
        (current_price_kes - previous_price_kes)   AS price_change_kes,
        CASE
            WHEN previous_price_kes > 0
            THEN ROUND(
                (current_price_kes - previous_price_kes) / previous_price_kes * 100,
                2
            )
            ELSE NULL
        END                                        AS price_change_pct,
        CASE
            WHEN previous_price_kes IS NULL              THEN 'new'
            WHEN current_price_kes > previous_price_kes  THEN 'up'
            WHEN current_price_kes < previous_price_kes  THEN 'down'
            ELSE 'unchanged'
        END                                        AS change_direction,
        scrape_date                                AS change_date
    FROM {{ ref('fct_price_history') }}
    WHERE rn_latest = 1
      AND (
            previous_price_kes IS NULL
         OR current_price_kes <> previous_price_kes
      )
)

SELECT
    product_name,
    category,
    brand,
    previous_price,
    current_price,
    price_change_kes,
    price_change_pct,
    change_direction,
    change_date,
    product_url
FROM changes
ORDER BY ABS(COALESCE(price_change_pct, 0)) DESC

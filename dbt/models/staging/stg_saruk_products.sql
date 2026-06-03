-- Staging model: clean and type-cast raw scraper output.
-- Brand extraction: first matched word against known brand list.
-- Discount computation: fills in where scraper returned NULL.

WITH raw AS (
    SELECT
        product_id,
        TRIM(product_name)                          AS product_name,
        TRIM(category)                              AS category,
        TRIM(brand)                                 AS brand_raw,
        CAST(current_price_kes AS NUMERIC(12,2))    AS current_price_kes,
        CAST(old_price_kes     AS NUMERIC(12,2))    AS old_price_kes,
        CAST(discount_pct      AS NUMERIC(5,2))     AS discount_pct_raw,
        in_stock,
        TRIM(product_url)                           AS product_url,
        scraped_at,
        scrape_date
    FROM {{ source('raw', 'saruk_products') }}
    WHERE product_name IS NOT NULL
      AND product_name <> ''
      AND current_price_kes > 0
),

brand_resolved AS (
    SELECT
        *,
        -- Use scraped brand; fall back to first capitalized word matching known brands
        COALESCE(
            NULLIF(brand_raw, ''),
            CASE
                WHEN SPLIT_PART(product_name, ' ', 1) = INITCAP(SPLIT_PART(product_name, ' ', 1))
                    AND SPLIT_PART(product_name, ' ', 1) IN (
                        'Apple','Samsung','Lenovo','HP','Dell','LG','Sony','Hisense','TCL',
                        'JBL','Bose','Sennheiser','Xiaomi','Infinix','Tecno','Itel','Oppo',
                        'Vivo','Realme','Huawei','Nokia','Motorola','Asus','Acer','MSI',
                        'Toshiba','Fujitsu','NEC','Panasonic','Sharp','Philips','Canon',
                        'Nikon','Fujifilm','GoPro','DJI','Epson','Brother','Logitech',
                        'Razer','Corsair','Kingston','Seagate','Sandisk','Transcend',
                        'Tenda','Ubiquiti','Cisco','Anker','Belkin','Baseus','Havit',
                        'Redragon','HyperX','Creative','Harman','Marshall','Yamaha',
                        'Denon','Marantz','ViewSonic','BenQ','AOC','Gigabyte','Crucial',
                        'Adata','Verbatim','Mikrotik','Netgear','Edifier'
                    )
                    THEN SPLIT_PART(product_name, ' ', 1)
                ELSE 'Other'
            END
        ) AS brand
    FROM raw
)

SELECT
    product_id,
    product_name,
    category,
    brand,
    current_price_kes,
    old_price_kes,
    -- Compute discount where scraper left it NULL
    COALESCE(
        discount_pct_raw,
        CASE
            WHEN old_price_kes IS NOT NULL
             AND old_price_kes > 0
             AND current_price_kes < old_price_kes
            THEN ROUND((old_price_kes - current_price_kes) / old_price_kes * 100, 2)
            ELSE NULL
        END
    ) AS discount_pct,
    in_stock,
    product_url,
    scraped_at,
    scrape_date
FROM brand_resolved

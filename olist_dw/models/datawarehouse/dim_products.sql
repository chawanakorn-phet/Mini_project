WITH source AS (
    SELECT
        p.product_id,
        COALESCE(t.product_category_name_english, p.product_category_name) AS category,
        p.product_category_name AS category_pt,
        p.product_weight_g,
        p.product_length_cm,
        p.product_height_cm,
        p.product_width_cm,
        p.product_photos_qty,
        current_localtimestamp() AS insertion_timestamp
    FROM {{ ref('stg_products') }} AS p
    LEFT JOIN {{ ref('stg_category_translation') }} AS t
        ON t.product_category_name = p.product_category_name
),

unique_source AS (
    SELECT
        *,
        ROW_NUMBER() OVER (PARTITION BY product_id) AS row_num
    FROM source
)

SELECT *
EXCLUDE (row_num)
FROM unique_source
WHERE row_num = 1

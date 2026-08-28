WITH source AS (
    SELECT
        r.review_id,
        r.order_id,
        o.customer_id,
        CAST(o.order_purchase_timestamp AS DATE) AS order_purchase_date,
        r.review_score,
        CAST(r.review_creation_date AS DATE) AS review_creation_date,
        CASE WHEN r.review_comment_message IS NOT NULL THEN 1 ELSE 0 END AS has_comment,
        current_localtimestamp() AS insertion_timestamp
    FROM {{ ref('stg_order_reviews') }} AS r
    LEFT JOIN {{ ref('stg_orders') }} AS o
        ON o.order_id = r.order_id
),

unique_source AS (
    SELECT
        *,
        ROW_NUMBER() OVER (PARTITION BY review_id) AS row_number
    FROM source
)

SELECT *
EXCLUDE (row_number)
FROM unique_source
WHERE row_number = 1

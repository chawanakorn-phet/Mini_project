{{ config(
    partition_by = ["order_purchase_date"]
) }}

WITH source AS (
    SELECT
        oi.order_id,
        oi.order_item_id,
        oi.product_id,
        oi.seller_id,
        o.customer_id,
        o.order_status,
        CAST(o.order_purchase_timestamp AS DATE) AS order_purchase_date,
        o.order_purchase_timestamp,
        o.order_approved_at,
        o.order_delivered_customer_date,
        o.order_estimated_delivery_date,
        oi.price,
        oi.freight_value,
        (oi.price + oi.freight_value) AS total_item_value,
        DATE_DIFF(
            'day',
            CAST(o.order_purchase_timestamp AS DATE),
            CAST(o.order_delivered_customer_date AS DATE)
        ) AS delivery_days,
        current_localtimestamp() AS insertion_timestamp
    FROM {{ ref('stg_order_items') }} AS oi
    LEFT JOIN {{ ref('stg_orders') }} AS o
        ON o.order_id = oi.order_id
),

unique_source AS (
    SELECT
        *,
        ROW_NUMBER() OVER (
            PARTITION BY order_id, order_item_id
        ) AS row_number
    FROM source
)

SELECT *
EXCLUDE (row_number)
FROM unique_source
WHERE row_number = 1

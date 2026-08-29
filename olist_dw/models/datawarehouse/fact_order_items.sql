{{ config(
    partition_by = ["order_purchase_date"]
) }}

WITH geo_customer AS (
    SELECT customer_id, avg_lat, avg_lng FROM {{ ref('dim_customers') }}
),

geo_seller AS (
    SELECT seller_id, avg_lat, avg_lng FROM {{ ref('dim_sellers') }}
),

source AS (
    SELECT
        oi.order_id,
        oi.order_item_id,
        oi.product_id,
        oi.seller_id,
        o.customer_id,
        o.order_status,
        CAST(o.order_purchase_timestamp AS DATE) AS order_purchase_date,
        o.order_purchase_timestamp,
        date_part('hour', o.order_purchase_timestamp) AS order_purchase_hour,
        o.order_approved_at,
        o.order_delivered_carrier_date,
        o.order_delivered_customer_date,
        o.order_estimated_delivery_date,
        oi.shipping_limit_date,
        oi.price,
        oi.freight_value,
        (oi.price + oi.freight_value) AS total_item_value,
        DATE_DIFF(
            'day',
            CAST(o.order_purchase_timestamp AS DATE),
            CAST(o.order_delivered_customer_date AS DATE)
        ) AS delivery_days,
        DATE_DIFF(
            'day',
            CAST(o.order_approved_at AS DATE),
            CAST(o.order_delivered_carrier_date AS DATE)
        ) AS seller_processing_days,
        DATE_DIFF(
            'day',
            CAST(o.order_delivered_carrier_date AS DATE),
            CAST(o.order_delivered_customer_date AS DATE)
        ) AS carrier_transit_days,
        CASE
            WHEN gc.avg_lat IS NULL OR gs.avg_lat IS NULL THEN NULL
            ELSE 6371 * acos(
                LEAST(1.0, GREATEST(-1.0,
                    cos(radians(gc.avg_lat)) * cos(radians(gs.avg_lat))
                        * cos(radians(gs.avg_lng) - radians(gc.avg_lng))
                        + sin(radians(gc.avg_lat)) * sin(radians(gs.avg_lat))
                ))
            )
        END AS buyer_seller_distance_km,
        current_localtimestamp() AS insertion_timestamp
    FROM {{ ref('stg_order_items') }} AS oi
    LEFT JOIN {{ ref('stg_orders') }} AS o
        ON o.order_id = oi.order_id
    LEFT JOIN geo_customer AS gc
        ON gc.customer_id = o.customer_id
    LEFT JOIN geo_seller AS gs
        ON gs.seller_id = oi.seller_id
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

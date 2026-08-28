WITH source AS (
    SELECT
        op.order_id,
        op.payment_sequential,
        o.customer_id,
        CAST(o.order_purchase_timestamp AS DATE) AS order_purchase_date,
        op.payment_type,
        op.payment_installments,
        op.payment_value,
        current_localtimestamp() AS insertion_timestamp
    FROM {{ ref('stg_order_payments') }} AS op
    LEFT JOIN {{ ref('stg_orders') }} AS o
        ON o.order_id = op.order_id
),

unique_source AS (
    SELECT
        *,
        ROW_NUMBER() OVER (
            PARTITION BY order_id, payment_sequential
        ) AS row_number
    FROM source
)

SELECT *
EXCLUDE (row_number)
FROM unique_source
WHERE row_number = 1

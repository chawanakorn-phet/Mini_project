WITH geo AS (
    SELECT
        geolocation_zip_code_prefix AS zip_code_prefix,
        AVG(geolocation_lat) AS avg_lat,
        AVG(geolocation_lng) AS avg_lng
    FROM {{ ref('stg_geolocation') }}
    GROUP BY geolocation_zip_code_prefix
),

source AS (
    SELECT
        c.customer_id,
        c.customer_unique_id,
        c.customer_zip_code_prefix AS zip_code_prefix,
        c.customer_city AS city,
        c.customer_state AS state,
        g.avg_lat,
        g.avg_lng,
        current_localtimestamp() AS insertion_timestamp
    FROM {{ ref('stg_customers') }} AS c
    LEFT JOIN geo AS g
        ON g.zip_code_prefix = c.customer_zip_code_prefix
),

unique_source AS (
    SELECT
        *,
        ROW_NUMBER() OVER (PARTITION BY customer_id) AS row_num
    FROM source
)

SELECT *
EXCLUDE (row_num)
FROM unique_source
WHERE row_num = 1

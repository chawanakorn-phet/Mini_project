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
        s.seller_id,
        s.seller_zip_code_prefix AS zip_code_prefix,
        s.seller_city AS city,
        s.seller_state AS state,
        g.avg_lat,
        g.avg_lng,
        current_localtimestamp() AS insertion_timestamp
    FROM {{ ref('stg_sellers') }} AS s
    LEFT JOIN geo AS g
        ON g.zip_code_prefix = s.seller_zip_code_prefix
),

unique_source AS (
    SELECT
        *,
        ROW_NUMBER() OVER (PARTITION BY seller_id) AS row_num
    FROM source
)

SELECT *
EXCLUDE (row_num)
FROM unique_source
WHERE row_num = 1

with source as (

    select * from {{ source('olist', 'product_category_name_translation') }}
)
select
    *,
    current_localtimestamp() as ingestion_timestamp
from source

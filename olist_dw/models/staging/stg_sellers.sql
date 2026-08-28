with source as (

    select * from {{ source('olist', 'olist_sellers_dataset') }}
)
select
    *,
    current_localtimestamp() as ingestion_timestamp
from source

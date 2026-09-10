with source as (

    select * from {{ source('olist', 'product_category_name_translation') }}
)
select
    *,
    -- The Olist export is a static Kaggle snapshot, and this model is a view,
    -- so a fixed literal (not now()) records when the snapshot was loaded into
    -- the project rather than when a query happened to run.
    cast('2018-11-01 00:00:00' as timestamp) as ingestion_timestamp
from source

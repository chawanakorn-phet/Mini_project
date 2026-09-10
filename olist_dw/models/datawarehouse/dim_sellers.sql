-- Seller dimension for fact_order_items.
--
-- Mirrors dim_customers deliberately: the same shape, the same cleaning, and a
-- geography_key into the same conformed dim_geography. Because both sides of
-- the marketplace point at one geography dimension, a query can compare where
-- goods are sold FROM against where they are sold TO without reconciling two
-- different location schemes.

with sellers as (

    select * from {{ ref('stg_sellers') }}
),

geography as (

    select geography_key, zip_code_prefix from {{ ref('dim_geography') }}
),

joined as (

    select
        s.seller_id,
        s.seller_zip_code_prefix                            as zip_code_prefix,
        coalesce(g.geography_key, -1)                       as geography_key,
        lower(trim(s.seller_city))                          as city,
        upper(trim(s.seller_state))                         as state
    from sellers as s
    left join geography as g on g.zip_code_prefix = s.seller_zip_code_prefix
),

deduplicated as (

    select
        *,
        row_number() over (partition by seller_id order by seller_id) as row_num
    from joined
)

select
    cast(row_number() over (order by seller_id) as integer) as seller_key,
    * exclude (row_num)
from deduplicated
where row_num = 1

union all

select -1, 'unknown', null, -1, 'unknown', 'XX'

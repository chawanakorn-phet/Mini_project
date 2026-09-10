-- Conformed customer dimension -- shared by all three facts.
--
-- A quirk of the source that has to be handled here: customer_id is issued
-- fresh for every order, so it does NOT identify a person. customer_unique_id
-- does. Both are kept: customer_id is the key the facts join on, while
-- customer_unique_id is what repeat-purchase and lifetime-value analysis must
-- group by. Confusing these two is the single easiest way to get a wrong
-- answer out of this dataset, so the distinction is explicit here.
--
-- Location is NOT copied in as loose columns; instead the row carries a
-- geography_key into the conformed dim_geography, so customer and seller
-- locations roll up through exactly the same hierarchy.

with customers as (

    select * from {{ ref('stg_customers') }}
),

geography as (

    select geography_key, zip_code_prefix from {{ ref('dim_geography') }}
),

joined as (

    select
        c.customer_id,
        c.customer_unique_id,
        c.customer_zip_code_prefix                          as zip_code_prefix,
        coalesce(g.geography_key, -1)                       as geography_key,
        lower(trim(c.customer_city))                        as city,
        upper(trim(c.customer_state))                       as state
    from customers as c
    left join geography as g on g.zip_code_prefix = c.customer_zip_code_prefix
),

deduplicated as (

    select
        *,
        row_number() over (partition by customer_id order by customer_id) as row_num
    from joined
)

select
    cast(row_number() over (order by customer_id) as integer) as customer_key,
    * exclude (row_num)
from deduplicated
where row_num = 1

union all

select -1, 'unknown', 'unknown', null, -1, 'unknown', 'XX'

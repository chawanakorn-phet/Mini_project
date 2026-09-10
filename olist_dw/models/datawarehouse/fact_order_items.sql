-- FACT 1 of 3 -- what was sold.
--
-- Grain: one row per product line on an order (order_id + order_item_id).
--        Stated once and obeyed everywhere: every measure below is true at the
--        level of a single product line, never at the level of a whole order.
--
-- Connects to SIX dimensions through ELEVEN foreign keys, because two of those
-- dimensions role-play:
--     dim_date        x5  purchased / approved / to carrier / delivered / promised
--     dim_geography   x2  buyer location / seller location
--     dim_products, dim_customers, dim_sellers, dim_order_status  x1 each
--
-- The role-playing geography keys are what make buyer-to-seller distance
-- computable: both sides resolve through the SAME conformed dimension, so the
-- coordinates are directly comparable.
--
-- Orders that were never delivered have no delivery timestamp. Those rows are
-- kept and pointed at the date dimension's Unknown member (-1) rather than
-- dropped, so revenue totals stay complete and "not yet delivered" remains a
-- visible, countable state instead of a silent gap.

with items as (

    select * from {{ ref('stg_order_items') }}
),

orders as (

    select * from {{ ref('stg_orders') }}
),

customer as (

    select customer_key, customer_id, geography_key from {{ ref('dim_customers') }}
),

seller as (

    select seller_key, seller_id, geography_key from {{ ref('dim_sellers') }}
),

geography as (

    select geography_key, latitude, longitude from {{ ref('dim_geography') }}
),

joined as (

    select
        -- Degenerate dimensions: order identifiers with no attributes of their
        -- own, so they live on the fact rather than in a dimension table.
        i.order_id,
        i.order_item_id,

        -- dim_date, role-playing five times
        coalesce(d_purchase.date_key,  -1)                  as purchase_date_key,
        coalesce(d_approved.date_key,  -1)                  as approved_date_key,
        coalesce(d_carrier.date_key,   -1)                  as carrier_date_key,
        coalesce(d_delivered.date_key, -1)                  as delivered_date_key,
        coalesce(d_estimated.date_key, -1)                  as estimated_date_key,

        -- the remaining dimensions
        coalesce(dp.product_key,       -1)                  as product_key,
        coalesce(dc.customer_key,      -1)                  as customer_key,
        coalesce(ds.seller_key,        -1)                  as seller_key,
        coalesce(dos.order_status_key, -1)                  as order_status_key,

        -- dim_geography, role-playing twice
        coalesce(dc.geography_key,     -1)                  as customer_geography_key,
        coalesce(ds.geography_key,     -1)                  as seller_geography_key,

        -- Additive measures -- safe to SUM across every dimension
        i.price,
        i.freight_value,
        i.price + i.freight_value                           as total_item_value,

        -- Non-additive measures -- durations and distances. Averaging them is
        -- meaningful; summing them across rows is not.
        date_diff('day', cast(o.order_purchase_timestamp as date),
                         cast(o.order_delivered_customer_date as date))
                                                            as delivery_days,
        date_diff('day', cast(o.order_approved_at as date),
                         cast(o.order_delivered_carrier_date as date))
                                                            as seller_processing_days,
        date_diff('day', cast(o.order_delivered_carrier_date as date),
                         cast(o.order_delivered_customer_date as date))
                                                            as carrier_transit_days,
        -- positive = arrived after the date the customer was promised
        date_diff('day', cast(o.order_estimated_delivery_date as date),
                         cast(o.order_delivered_customer_date as date))
                                                            as delivery_delay_days,

        -- Great-circle distance between buyer and seller, in kilometres.
        -- LEAST/GREATEST clamp the cosine into [-1, 1]; floating point can
        -- otherwise push it a hair outside the domain and make acos() fail.
        case
            when gc.latitude is null or gs.latitude is null then null
            else 6371 * acos(
                least(1.0, greatest(-1.0,
                    cos(radians(gc.latitude)) * cos(radians(gs.latitude))
                        * cos(radians(gs.longitude) - radians(gc.longitude))
                    + sin(radians(gc.latitude)) * sin(radians(gs.latitude))
                ))
            )
        end                                                 as buyer_seller_distance_km,

        -- Semi-additive flag: counting late deliveries is meaningful, but the
        -- count only means something within a fixed set of delivered orders.
        case
            when o.order_delivered_customer_date is null
              or o.order_estimated_delivery_date is null then null
            when o.order_delivered_customer_date > o.order_estimated_delivery_date
                then 1
            else 0
        end                                                 as is_late_delivery,

        cast(date_part('hour', o.order_purchase_timestamp) as integer)
                                                            as purchase_hour,

        current_localtimestamp()                            as insertion_timestamp

    from items as i
    left join orders as o on o.order_id = i.order_id

    left join {{ ref('dim_date') }} as d_purchase
        on d_purchase.full_date  = cast(o.order_purchase_timestamp as date)
    left join {{ ref('dim_date') }} as d_approved
        on d_approved.full_date  = cast(o.order_approved_at as date)
    left join {{ ref('dim_date') }} as d_carrier
        on d_carrier.full_date   = cast(o.order_delivered_carrier_date as date)
    left join {{ ref('dim_date') }} as d_delivered
        on d_delivered.full_date = cast(o.order_delivered_customer_date as date)
    left join {{ ref('dim_date') }} as d_estimated
        on d_estimated.full_date = cast(o.order_estimated_delivery_date as date)

    left join {{ ref('dim_products') }}     as dp  on dp.product_id   = i.product_id
    left join customer                     as dc  on dc.customer_id  = o.customer_id
    left join seller                       as ds  on ds.seller_id    = i.seller_id
    left join {{ ref('dim_order_status') }} as dos on dos.order_status = o.order_status

    left join geography as gc on gc.geography_key = dc.geography_key
    left join geography as gs on gs.geography_key = ds.geography_key
),

deduplicated as (

    select
        *,
        row_number() over (
            partition by order_id, order_item_id
            order by order_item_id
        ) as row_num
    from joined
)

select * exclude (row_num)
from deduplicated
where row_num = 1

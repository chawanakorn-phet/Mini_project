-- FACT 2 of 3 -- how it was paid for.
--
-- Grain: one row per payment transaction (order_id + payment_sequential).
--        This is a DIFFERENT grain from fact_order_items: one order can be
--        split across several payments (a voucher plus a card, say) while also
--        containing several product lines. That mismatch is precisely why
--        these are two fact tables and not one -- joining them at row level
--        would multiply the rows together and inflate both totals.
--
-- Connects to FOUR dimensions: dim_date, dim_customers, dim_geography and
-- dim_order_status are all shared with fact_order_items, plus dim_payment_type
-- which belongs to this fact alone. Those shared dimensions are the join path
-- for the drill-across question "what did the basket cost versus what did the
-- customer actually pay?"

with payments as (

    select * from {{ ref('stg_order_payments') }}
),

orders as (

    select * from {{ ref('stg_orders') }}
),

customer as (

    select customer_key, customer_id, geography_key from {{ ref('dim_customers') }}
),

joined as (

    select
        -- Degenerate dimensions
        p.order_id,
        p.payment_sequential,

        -- Foreign keys
        coalesce(d_purchase.date_key,   -1)                 as purchase_date_key,
        coalesce(dc.customer_key,       -1)                 as customer_key,
        coalesce(dc.geography_key,      -1)                 as customer_geography_key,
        coalesce(dpt.payment_type_key,  -1)                 as payment_type_key,
        coalesce(dos.order_status_key,  -1)                 as order_status_key,

        -- Additive measure
        p.payment_value,

        -- Non-additive: a count of instalments describes one transaction.
        -- Summing it across transactions is meaningless; average it instead.
        p.payment_installments,
        case when p.payment_installments > 0
             then round(p.payment_value / p.payment_installments, 2)
        end                                                 as instalment_amount,

        -- Flags for slicing
        p.payment_sequential > 1                            as is_split_payment,
        p.payment_installments > 1                          as is_instalment_plan,

        current_localtimestamp()                            as insertion_timestamp

    from payments as p
    left join orders as o on o.order_id = p.order_id

    left join {{ ref('dim_date') }} as d_purchase
        on d_purchase.full_date = cast(o.order_purchase_timestamp as date)
    left join customer                       as dc  on dc.customer_id   = o.customer_id
    left join {{ ref('dim_payment_type') }}  as dpt on dpt.payment_type = p.payment_type
    left join {{ ref('dim_order_status') }}  as dos on dos.order_status = o.order_status
),

deduplicated as (

    select
        *,
        row_number() over (
            partition by order_id, payment_sequential
            order by payment_sequential
        ) as row_num
    from joined
)

select * exclude (row_num)
from deduplicated
where row_num = 1

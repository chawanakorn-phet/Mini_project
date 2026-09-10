-- Conformed order-status dimension -- shared by all three facts.
--
-- The source stores status as a bare string on the order header. Promoting it
-- to a dimension puts the behaviour of each status (is it finished? was it
-- cancelled? where does it sit in the lifecycle?) in one place instead of
-- repeating CASE expressions in every query, and gives the dashboard a
-- readable label plus a sensible sort order.

with statuses as (

    select distinct order_status from {{ ref('stg_orders') }}
)

select
    cast(row_number() over (order by order_status) as integer) as order_status_key,
    order_status,
    case order_status
        when 'created'     then 'Created'
        when 'approved'    then 'Payment approved'
        when 'processing'  then 'Being prepared'
        when 'invoiced'    then 'Invoiced'
        when 'shipped'     then 'Shipped'
        when 'delivered'   then 'Delivered'
        when 'canceled'    then 'Cancelled'
        when 'unavailable' then 'Unavailable'
        else order_status
    end                                                     as status_label,
    order_status = 'delivered'                              as is_delivered,
    order_status in ('canceled', 'unavailable')             as is_cancelled,
    -- position in the order lifecycle, so charts sort in a sensible order
    case order_status
        when 'created'     then 1
        when 'approved'    then 2
        when 'invoiced'    then 3
        when 'processing'  then 4
        when 'shipped'     then 5
        when 'delivered'   then 6
        when 'canceled'    then 7
        when 'unavailable' then 8
        else 9
    end                                                     as lifecycle_step
from statuses

union all

select -1, 'unknown', 'Unknown', false, false, 9

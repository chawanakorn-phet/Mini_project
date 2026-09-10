-- fact_order_items claims a grain of one row per product line on an order.
select order_id, order_item_id, count(*) as n
from {{ ref('fact_order_items') }}
group by 1, 2
having count(*) > 1

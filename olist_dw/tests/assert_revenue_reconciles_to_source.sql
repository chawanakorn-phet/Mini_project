-- Total price + freight in the fact must equal the same total in staging.
with warehouse as (
    select round(sum(total_item_value), 2) as total from {{ ref('fact_order_items') }}
),
source as (
    select round(sum(price + freight_value), 2) as total from {{ ref('stg_order_items') }}
)
select w.total as warehouse_total, s.total as source_total
from warehouse as w cross join source as s
where w.total <> s.total

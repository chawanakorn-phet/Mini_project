-- fact_order_payments claims a grain of one row per payment transaction.
select order_id, payment_sequential, count(*) as n
from {{ ref('fact_order_payments') }}
group by 1, 2
having count(*) > 1

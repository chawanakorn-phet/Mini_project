-- fact_order_reviews claims a grain of one review PER ORDER. Deliberately
-- (review_id, order_id): Olist reuses a review_id across orders, so
-- partitioning on review_id alone would drop 814 genuine rows.
select review_id, order_id, count(*) as n
from {{ ref('fact_order_reviews') }}
group by 1, 2
having count(*) > 1

-- =====================================================================
-- Olist Data Warehouse
-- Analytical Queries — Business Questions Q1–Q15
-------------------------------------------------

-- Source: dim_* / fact_* tables only
-- Grain-aware design:
--   fact_order_items    = 1 row per order item
--   fact_order_payments = 1 row per payment transaction
--   fact_order_reviews  = 1 row per review-order pair
------------------------------------------------------

-- IMPORTANT:
-- Some questions require order-level aggregation before joining to
-- reviews/payments in order to avoid double counting.
-- =====================================================================

-- =====================================================================
-- Q1 — Which product category has the highest total sales
--      and the highest quantity sold?
--------------------------------------

-- Quantity = number of order-item rows because the source dataset
-- does not contain an explicit quantity column.
-- =====================================================================

select
dp.category as product_category,
count(*) as quantity_sold,
round(sum(f.price), 2) as total_revenue
from {{ ref('fact_order_items') }} f
join {{ ref('dim_products') }} dp
on dp.product_id = f.product_id
group by 1
order by total_revenue desc;

-- =====================================================================
-- Q2 — How do sales and number of orders change by month and year?
-------------------------------------------------------------------

-- Revenue = SUM(price)
-- Orders  = COUNT(DISTINCT order_id)
-- =====================================================================

select
extract(year from f.order_purchase_date) as year,
extract(month from f.order_purchase_date) as month,
strftime(f.order_purchase_date, '%Y-%m') as year_month,
count(distinct f.order_id) as n_orders,
round(sum(f.price), 2) as total_revenue
from {{ ref('fact_order_items') }} f
where f.order_purchase_date is not null
group by 1, 2, 3
order by year, month;

-- =====================================================================
-- Q3 — Which product category has the highest average price per item,
--      and how many items were sold?
-------------------------------------

-- Average price = AVG(price)
-- Quantity sold = COUNT(*)
-- =====================================================================

select
dp.category as product_category,
round(avg(f.price), 2) as avg_price_per_item,
count(*) as quantity_sold,
round(sum(f.price), 2) as total_revenue
from {{ ref('fact_order_items') }} f
join {{ ref('dim_products') }} dp
on dp.product_id = f.product_id
where f.price is not null
group by 1
having count(*) >= 30
order by avg_price_per_item desc;

-- =====================================================================
-- Q4 — Which customer state and city generate the highest total sales?
-- =====================================================================

select
dc.state as customer_state,
dc.city as customer_city,
count(distinct f.order_id) as n_orders,
count(distinct dc.customer_unique_id) as n_customers,
round(sum(f.price), 2) as total_revenue
from {{ ref('fact_order_items') }} f
join {{ ref('dim_customers') }} dc
on dc.customer_id = f.customer_id
group by 1, 2
order by total_revenue desc;

-- =====================================================================
-- Q5 — What percentage of customers are repeat buyers?
-------------------------------------------------------

-- A repeat customer = customer_unique_id with more than one order.
-- customer_unique_id is used instead of customer_id because the same
-- real customer can have multiple customer_id values across orders.
-- =====================================================================

with customer_orders as (
select
dc.customer_unique_id,
count(distinct f.order_id) as n_orders
from {{ ref('fact_order_items') }} f
join {{ ref('dim_customers') }} dc
on dc.customer_id = f.customer_id
group by 1
),
customer_segments as (
select
case
when n_orders > 1 then 'Repeat customer'
else 'One-time customer'
end as customer_segment
from customer_orders
)
select
customer_segment,
count(*) as n_customers,
round(
100.0 * count(*) / sum(count(*)) over (),
2
) as pct_of_customers
from customer_segments
group by 1
order by
case
when customer_segment = 'Repeat customer' then 1
else 2
end;

-- =====================================================================
-- Q6 — Do customers with more orders have a higher average order value?
------------------------------------------------------------------------

-- Step 1: calculate order value at order grain.
-- Step 2: calculate order frequency at customer grain.
-- Step 3: compare average order value between frequency groups.
-- =====================================================================

with customer_orders as (
select
dc.customer_unique_id,
f.order_id,
sum(f.price) as order_value
from {{ ref('fact_order_items') }} f
join {{ ref('dim_customers') }} dc
on dc.customer_id = f.customer_id
group by 1, 2
),
customer_summary as (
select
customer_unique_id,
count(distinct order_id) as n_orders,
avg(order_value) as avg_order_value
from customer_orders
group by 1
)
select
case
when n_orders = 1 then '1 order'
when n_orders = 2 then '2 orders'
else '3+ orders'
end as purchase_frequency_group,
count(*) as n_customers,
round(avg(avg_order_value), 2) as avg_order_value
from customer_summary
group by 1
order by
case
when purchase_frequency_group = '1 order' then 1
when purchase_frequency_group = '2 orders' then 2
else 3
end;

-- =====================================================================
-- Q7 — Which customer group has the highest customer value
--      and purchase frequency using RFM Analysis?
--------------------------------------------------

-- R = Recency
-- F = Frequency
-- M = Monetary
---------------

-- Customers are scored into quintiles:
--   5 = highest value
--   1 = lowest value
---------------------

-- The final segment combines R, F and M scores.
-- =====================================================================

with customer_orders as (
select
dc.customer_unique_id,
f.order_id,
max(f.order_purchase_date) as order_date,
sum(f.price) as order_value
from {{ ref('fact_order_items') }} f
join {{ ref('dim_customers') }} dc
on dc.customer_id = f.customer_id
group by 1, 2
),
rfm_base as (
select
customer_unique_id,
date_diff(
'day',
max(order_date),
(select max(order_date) from customer_orders)
) as recency_days,
count(distinct order_id) as frequency,
sum(order_value) as monetary
from customer_orders
group by 1
),
rfm_scores as (
select
*,
6 - ntile(5) over (
order by recency_days desc
) as recency_score,
ntile(5) over (
order by frequency
) as frequency_score,
ntile(5) over (
order by monetary
) as monetary_score
from rfm_base
),
rfm_segmented as (
select
*,
recency_score
+ frequency_score
+ monetary_score as rfm_score
from rfm_scores
)
select
case
when rfm_score >= 13 then 'Champions'
when rfm_score >= 10 then 'High Value'
when rfm_score >= 7 then 'Potential'
else 'Low Value'
end as customer_group,
count(*) as n_customers,
round(avg(recency_days), 1) as avg_recency_days,
round(avg(frequency), 2) as avg_frequency,
round(avg(monetary), 2) as avg_monetary,
round(sum(monetary), 2) as total_monetary
from rfm_segmented
group by 1
order by total_monetary desc;

-- =====================================================================
-- Q8 — Which payment method is used most frequently,
--      and what is its average payment value?
----------------------------------------------

-- n_transactions = number of payment transactions
-- n_orders       = number of distinct orders using the method
-- =====================================================================

select
payment_type,
count(*) as n_transactions,
count(distinct order_id) as n_orders,
round(avg(payment_value), 2) as avg_payment_value,
round(sum(payment_value), 2) as total_payment_value
from {{ ref('fact_order_payments') }}
where payment_type != 'not_defined'
group by 1
order by n_orders desc;

-- =====================================================================
-- Q9 — Which seller state/city has the highest average preparation time?
-------------------------------------------------------------------------

-- Preparation time:
-- order_approved_at → order_delivered_carrier_date
---------------------------------------------------

-- Because fact_order_items is item grain, first reduce to one row
-- per order + seller before calculating averages.
-- =====================================================================

with order_seller as (
select
order_id,
seller_id,
max(seller_processing_days) as seller_processing_days
from {{ ref('fact_order_items') }}
where seller_processing_days is not null
and seller_processing_days >= 0
group by 1, 2
)
select
ds.state as seller_state,
ds.city as seller_city,
count(*) as n_orders,
round(avg(os.seller_processing_days), 2)
as avg_preparation_days
from order_seller os
join {{ ref('dim_sellers') }} ds
on ds.seller_id = os.seller_id
group by 1, 2
having count(*) >= 20
order by avg_preparation_days desc;

-- =====================================================================
-- Q10 — How do shipping time and delivery delay differ by month?
-----------------------------------------------------------------

-- Shipping/transit time:
-- delivered_customer_date - delivered_carrier_date
---------------------------------------------------

-- Delivery delay:
-- delivered_customer_date - estimated_delivery_date
----------------------------------------------------

-- Positive delay = delivered late
-- Negative delay = delivered early
-----------------------------------

-- Calculated at order grain to avoid item-level weighting.
-- =====================================================================

with order_delivery as (
select
order_id,
max(order_purchase_date) as order_purchase_date,
max(carrier_transit_days) as carrier_transit_days,
max(delivery_delay_days) as delivery_delay_days,
max(order_delivered_customer_date)
as delivered_customer_date
from {{ ref('fact_order_items') }}
where order_delivered_customer_date is not null
group by 1
)
select
extract(year from order_purchase_date) as year,
extract(month from order_purchase_date) as month,
strftime(order_purchase_date, '%Y-%m') as year_month,
count(*) as n_orders,
round(avg(carrier_transit_days), 2)
as avg_shipping_days,
round(avg(delivery_delay_days), 2)
as avg_delivery_delay_days,
round(
100.0 * avg(
case
when delivery_delay_days > 0 then 1
else 0
end
),
2
) as late_delivery_pct
from order_delivery
where order_purchase_date is not null
group by 1, 2, 3
order by year, month;

-- =====================================================================
-- Q11 — Which product category has the highest freight cost
--       as a percentage of product price?
-- =====================================================================

select
dp.category as product_category,
round(sum(f.freight_value), 2) as total_freight,
round(sum(f.price), 2) as total_product_price,
round(
100.0 * sum(f.freight_value)
/ nullif(sum(f.price), 0),
2
) as freight_pct_of_price,
count(*) as quantity_sold
from {{ ref('fact_order_items') }} f
join {{ ref('dim_products') }} dp
on dp.product_id = f.product_id
group by 1
having count(*) >= 30
order by freight_pct_of_price desc;

-- =====================================================================
-- Q12 — Which product categories have the highest and lowest
--       average review scores?
-------------------------------

## -- Review is an order-level measure while product category is item-level.

-- To avoid counting one review multiple times when an order contains
-- multiple items, first create distinct order-category combinations.
-- Each order contributes at most one review score to a category.
-- =====================================================================

with order_categories as (
select distinct
f.order_id,
dp.category as product_category
from {{ ref('fact_order_items') }} f
join {{ ref('dim_products') }} dp
on dp.product_id = f.product_id
),
category_reviews as (
select
oc.product_category,
r.order_id,
r.review_score
from order_categories oc
join {{ ref('fact_order_reviews') }} r
on r.order_id = oc.order_id
)
select
product_category,
count(*) as n_orders_reviewed,
round(avg(review_score), 2) as avg_review_score
from category_reviews
group by 1
having count(*) >= 30
order by avg_review_score desc;

-- =====================================================================
-- Q13 — How do review scores differ among customers in each state?
-------------------------------------------------------------------

-- One review is counted once per order/customer.
-- =====================================================================

with order_reviews as (
select
r.order_id,
max(r.review_score) as review_score
from {{ ref('fact_order_reviews') }} r
group by 1
)
select
dc.state as customer_state,
count(*) as n_orders_reviewed,
round(avg(orv.review_score), 2) as avg_review_score,
round(
100.0 * sum(
case when orv.review_score >= 4 then 1 else 0 end
) / count(*),
2
) as positive_review_pct
from order_reviews orv
join {{ ref('fact_order_items') }} f
on f.order_id = orv.order_id
join {{ ref('dim_customers') }} dc
on dc.customer_id = f.customer_id
group by 1
having count(*) >= 30
order by avg_review_score desc;

-- =====================================================================
-- Q14 — What percentage of total revenue is generated by the
--       top 10% of sellers?
----------------------------

-- Sellers are ranked by total revenue.
-- The top 10% are selected using CEIL(total_sellers * 0.10).
-- =====================================================================

with seller_revenue as (
select
seller_id,
sum(price) as revenue
from {{ ref('fact_order_items') }}
group by 1
),
ranked_sellers as (
select
seller_id,
revenue,
row_number() over (
order by revenue desc
) as seller_rank,
count(*) over () as total_sellers
from seller_revenue
),
top_sellers as (
select
seller_id,
revenue
from ranked_sellers
where seller_rank <= ceil(total_sellers * 0.10)
)
select
count(*) as top_10_pct_seller_count,
round(sum(revenue), 2) as top_10_pct_revenue,
round(
100.0 * sum(revenue)
/ (select sum(revenue) from seller_revenue),
2
) as top_10_pct_revenue_share
from top_sellers;

-- =====================================================================
-- Q15 — Which product pairs are purchased together most frequently?
--------------------------------------------------------------------

## -- Product pairs are generated from items within the same order.

-- a.product_id < b.product_id prevents:
--   A + B
--   B + A
-- from being counted as two different pairs.
---------------------------------------------

-- DISTINCT prevents multiple quantities/lines of the same product
-- from creating duplicate pair counts within one order.
-- =====================================================================

with order_products as (
select distinct
f.order_id,
f.product_id
from {{ ref('fact_order_items') }} f
),
product_pairs as (
select
a.order_id,
a.product_id as product_a,
b.product_id as product_b
from order_products a
join order_products b
on a.order_id = b.order_id
and a.product_id < b.product_id
)
select
pp.product_a,
dp_a.category as category_a,
pp.product_b,
dp_b.category as category_b,
count(*) as n_orders_together
from product_pairs pp
join {{ ref('dim_products') }} dp_a
on dp_a.product_id = pp.product_a
join {{ ref('dim_products') }} dp_b
on dp_b.product_id = pp.product_b
group by 1, 2, 3, 4
order by n_orders_together desc
limit 20;

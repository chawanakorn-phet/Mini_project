-- Analytical Queries -- one per Business Question (see README.md section 2)
--
-- These live in dbt's analyses folder: they use dbt ref() macros like a
-- normal model, but dbt never materializes them as tables -- "dbt compile"
-- turns each into runnable SQL under target/compiled/.../analyses/, and
-- "dbt show --select analytical_queries" (dbt 1.5+) will run the LAST
-- statement in the file -- to run a different query, comment out the
-- others' final SELECT or run the compiled SQL directly against dev.duckdb.
--
-- Every query below is built only from dim_*/fact_* tables.


-- =====================================================================
-- Q1 — Which product category sells the most, by quantity AND by revenue?
-- Dimension: dim_products | Measures: COUNT(*) quantity, SUM(price) revenue
-- =====================================================================
select
    dp.category as product_category,
    count(*) as quantity,
    sum(f.price) as revenue
from {{ ref('fact_order_items') }} f
join {{ ref('dim_products') }} dp on dp.product_id = f.product_id
group by 1
order by revenue desc
limit 10;


-- =====================================================================
-- Q2 — Peak order hour, and month-over-month revenue growth
-- Dimension: dim_date | Measures: SUM(price), COUNT(order_id)
-- =====================================================================
select
    f.order_purchase_hour as hour,
    count(distinct f.order_id) as orders,
    sum(f.price) as revenue
from {{ ref('fact_order_items') }} f
group by 1
order by 1;

with monthly as (
    select date_trunc('month', order_purchase_date) as month, sum(price) as revenue
    from {{ ref('fact_order_items') }}
    where order_purchase_date >= date '2017-01-01'
    group by 1
)
select
    month,
    revenue,
    100.0 * (revenue - lag(revenue) over (order by month))
        / nullif(lag(revenue) over (order by month), 0) as mom_pct
from monthly
order by month;


-- =====================================================================
-- Q3 — Which payment method is used most, and which drives the highest AOV?
-- Dimension: (payment_type attribute) | Measures: COUNT(order_id), AVG(payment_value)
-- =====================================================================
select
    payment_type,
    count(distinct order_id) as n_orders,
    round(avg(payment_value), 2) as avg_order_value
from {{ ref('fact_order_payments') }}
where payment_type != 'not_defined'
group by 1
order by n_orders desc;


-- =====================================================================
-- Q4 — Repeat customer rate + RFM: how much revenue comes from the top quintile?
-- Dimension: dim_customers | Measures: SUM(price) monetary, COUNT(order_id) frequency,
--            MAX(order_purchase_date) recency
-- =====================================================================
with customer_orders as (
    select dc.customer_unique_id, f.order_id, max(f.order_purchase_date) as order_date, sum(f.price) as order_value
    from {{ ref('fact_order_items') }} f
    join {{ ref('dim_customers') }} dc on dc.customer_id = f.customer_id
    group by 1, 2
),
rfm as (
    select
        customer_unique_id,
        date_diff('day', max(order_date), (select max(order_date) from customer_orders)) as recency_days,
        count(distinct order_id) as frequency,
        sum(order_value) as monetary
    from customer_orders
    group by 1
)
select
    ntile(5) over (order by monetary) as monetary_quintile,
    count(*) as n_customers,
    round(100.0 * sum(monetary) / sum(sum(monetary)) over (), 1) as pct_of_revenue
from rfm
group by 1
order by 1 desc;


-- =====================================================================
-- Q5 — How much more do frequent buyers spend per order?
-- Dimension: dim_customers | Measures: COUNT(order_id), AVG(order_value)
-- =====================================================================
with customer_orders as (
    select dc.customer_unique_id, f.order_id, sum(f.price) as order_value
    from {{ ref('fact_order_items') }} f
    join {{ ref('dim_customers') }} dc on dc.customer_id = f.customer_id
    group by 1, 2
)
select
    case when count(distinct order_id) = 1 then '1 order'
         when count(distinct order_id) = 2 then '2 orders'
         else '3+ orders' end as bucket,
    count(*) as n_customers,
    round(avg(order_value), 2) as avg_order_value
from customer_orders
group by customer_unique_id
;
-- (wrap the above in an outer aggregate by `bucket` when running standalone;
--  see dashboard_app.py::load_frequency_buckets for the fully aggregated version)


-- =====================================================================
-- Q6 — Where are most customers, and which state is the fastest-growing new market?
-- Dimension: dim_customers, dim_date | Measure: COUNT(customer_unique_id)
-- =====================================================================
select
    dc.state as customer_state,
    count(distinct f.customer_id) as customers,
    sum(f.price) as revenue
from {{ ref('fact_order_items') }} f
join {{ ref('dim_customers') }} dc on dc.customer_id = f.customer_id
group by 1
order by revenue desc;

with first_orders as (
    select dc.customer_unique_id, dc.state, min(f.order_purchase_date) as first_order_date
    from {{ ref('fact_order_items') }} f
    join {{ ref('dim_customers') }} dc on dc.customer_id = f.customer_id
    group by 1, 2
)
select
    state,
    sum(case when first_order_date < date '2017-10-01' then 1 else 0 end) as new_customers_early,
    sum(case when first_order_date >= date '2017-10-01' then 1 else 0 end) as new_customers_recent
from first_orders
where first_order_date >= date '2017-01-01'
group by 1
order by new_customers_recent desc;


-- =====================================================================
-- Q7 — Actual vs estimated delivery date: how many days off, and review impact?
-- Dimension: dim_date (order_estimated/delivered dates) | Measure: AVG(review_score)
-- =====================================================================
select
    case when f.order_delivered_customer_date > f.order_estimated_delivery_date
         then 'Late' else 'On-time' end as status,
    count(*) as n,
    round(avg(r.review_score), 2) as avg_review_score
from {{ ref('fact_order_items') }} f
join {{ ref('fact_order_reviews') }} r on r.order_id = f.order_id
where f.order_delivered_customer_date is not null and f.order_estimated_delivery_date is not null
group by 1;


-- =====================================================================
-- Q8 — Freight as a % of price, by category
-- Dimension: dim_products | Measures: SUM(freight_value), SUM(price)
-- =====================================================================
select
    dp.category as product_category,
    round(100.0 * sum(f.freight_value) / nullif(sum(f.price), 0), 1) as freight_pct_of_price
from {{ ref('fact_order_items') }} f
join {{ ref('dim_products') }} dp on dp.product_id = f.product_id
group by 1
having count(*) >= 30
order by freight_pct_of_price desc
limit 10;


-- =====================================================================
-- Q9 — Which seller->customer routes have the worst late-delivery rate,
--       and is it the seller's or the carrier's fault?
-- Dimension: dim_sellers, dim_customers | Measures: AVG(seller_processing_days), AVG(carrier_transit_days)
-- =====================================================================
select
    ds.state as seller_state,
    dc.state as customer_state,
    count(*) as n_orders,
    round(100.0 * sum(case when f.order_delivered_customer_date > f.order_estimated_delivery_date then 1 else 0 end)
        / count(*), 1) as late_pct,
    round(avg(f.seller_processing_days), 1) as avg_seller_processing_days,
    round(avg(f.carrier_transit_days), 1) as avg_carrier_transit_days
from {{ ref('fact_order_items') }} f
join {{ ref('dim_sellers') }} ds on ds.seller_id = f.seller_id
join {{ ref('dim_customers') }} dc on dc.customer_id = f.customer_id
where f.order_delivered_customer_date is not null and f.order_estimated_delivery_date is not null
group by 1, 2
having count(*) >= 20
order by late_pct desc
limit 10;


-- =====================================================================
-- Q10 — Does buyer-seller distance affect review score?
-- Dimension: dim_customers, dim_sellers | Measures: AVG(buyer_seller_distance_km), AVG(review_score)
-- =====================================================================
select
    case
        when f.buyer_seller_distance_km < 500 then '< 500 km'
        when f.buyer_seller_distance_km < 1500 then '500-1500 km'
        else '> 1500 km'
    end as distance_bucket,
    round(avg(f.buyer_seller_distance_km), 0) as avg_km,
    round(avg(r.review_score), 2) as avg_review_score
from {{ ref('fact_order_items') }} f
join {{ ref('fact_order_reviews') }} r on r.order_id = f.order_id
where f.buyer_seller_distance_km is not null
group by 1
order by 1;


-- =====================================================================
-- Q11 — Highest-revenue categories vs their average review score
-- Dimension: dim_products | Measures: SUM(price), AVG(review_score)
-- =====================================================================
select
    dp.category as product_category,
    sum(f.price) as revenue,
    round(avg(r.review_score), 2) as avg_review_score
from {{ ref('fact_order_items') }} f
join {{ ref('dim_products') }} dp on dp.product_id = f.product_id
join {{ ref('fact_order_reviews') }} r on r.order_id = f.order_id
group by 1
having count(*) >= 30
order by revenue desc
limit 15;


-- =====================================================================
-- Q12 — Do product-page attributes (photos, description length) affect review score?
-- Dimension: dim_products | Measures: product_photos_qty, product_description_length, AVG(review_score)
-- =====================================================================
select
    case when dp.product_photos_qty <= 1 then '0-1 photo'
         when dp.product_photos_qty <= 3 then '2-3 photos'
         else '4+ photos' end as photo_bucket,
    round(avg(r.review_score), 2) as avg_review_score
from {{ ref('fact_order_items') }} f
join {{ ref('dim_products') }} dp on dp.product_id = f.product_id
join {{ ref('fact_order_reviews') }} r on r.order_id = f.order_id
where dp.product_photos_qty is not null
group by 1
order by 1;


-- =====================================================================
-- Q13 — Market Basket Analysis: which categories are bought together most often?
-- Dimension: dim_products | Measure: COUNT(*) order co-occurrence
-- =====================================================================
with order_cats as (
    select distinct f.order_id, dp.category
    from {{ ref('fact_order_items') }} f
    join {{ ref('dim_products') }} dp on dp.product_id = f.product_id
)
select
    a.category as category_a,
    b.category as category_b,
    count(*) as n_orders_together
from order_cats a
join order_cats b on a.order_id = b.order_id and a.category < b.category
group by 1, 2
order by n_orders_together desc
limit 10;


-- =====================================================================
-- Q14 — Is platform revenue concentrated in the top 10% of sellers? (Pareto 80/20)
-- Dimension: dim_sellers | Measure: SUM(price)
-- =====================================================================
with seller_revenue as (
    select seller_id, sum(price) as revenue
    from {{ ref('fact_order_items') }}
    group by 1
),
ranked as (
    select
        seller_id,
        revenue,
        row_number() over (order by revenue desc) as rnk,
        count(*) over () as total_sellers
    from seller_revenue
)
select
    100.0 * rnk / total_sellers as pct_sellers,
    100.0 * sum(revenue) over (order by rnk) / sum(revenue) over () as cum_pct_revenue
from ranked
order by rnk;


-- =====================================================================
-- Q15 — Does seller fulfillment speed affect their review score?
-- Dimension: dim_sellers | Measures: AVG(seller_processing_days), AVG(review_score)
-- =====================================================================
select
    case when f.seller_processing_days <= 1 then 'Fast (<=1 day)'
         when f.seller_processing_days <= 3 then 'Medium (2-3 days)'
         else 'Slow (>3 days)' end as speed_bucket,
    round(avg(r.review_score), 2) as avg_review_score
from {{ ref('fact_order_items') }} f
join {{ ref('fact_order_reviews') }} r on r.order_id = f.order_id
where f.seller_processing_days is not null and f.seller_processing_days >= 0
group by 1
order by 1;

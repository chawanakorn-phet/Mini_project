-- ============================================================================
-- ANALYTICAL QUERIES -- one per business question (see README section 2).
--
-- These live in dbt's analyses/ folder: they use ref() macros like a normal
-- model, but dbt never materialises them. "dbt compile" turns each into
-- runnable SQL under target/compiled/.../analyses/, which can then be run
-- directly against dev.duckdb.
--
-- Every query reads ONLY from dim_* / fact_* tables -- never from staging.
--
-- Each question header names the fact table, the dimension(s) it travels
-- through, and the measure(s) it aggregates, so the link from question to
-- model is explicit.
--
-- Questions 13, 14 and 15 are DRILL-ACROSS queries: they aggregate two fact
-- tables to a common grain and join the results on a CONFORMED dimension.
-- They are why this warehouse is a fact constellation and not a single star.
-- ============================================================================


-- ============================================================================
-- THEME A -- SALES & REVENUE
-- ============================================================================

-- ----------------------------------------------------------------------------
-- Q1. Which product category earns the most, by units and by revenue -- and is
--     it the same category on both measures?
--     Fact: fact_order_items | Dimension: dim_products (category)
--     Measures: SUM(price) additive, COUNT(*) additive
-- ----------------------------------------------------------------------------
select
    dp.category                                            as product_category,
    count(*)                                               as items_sold,
    round(sum(f.price), 2)                                 as revenue,
    round(sum(f.freight_value), 2)                         as freight_collected
from {{ ref('fact_order_items') }} as f
join {{ ref('dim_products') }} as dp on dp.product_key = f.product_key
group by 1
order by revenue desc
limit 10;


-- ----------------------------------------------------------------------------
-- Q2. How did monthly revenue grow, and which hour of day sees the most orders?
--     Fact: fact_order_items | Dimension: dim_date (year_month roll-up)
--     Measures: SUM(price), COUNT(DISTINCT order_id), month-over-month growth %
-- ----------------------------------------------------------------------------
with monthly as (
    select
        dd.year_month,
        sum(f.price)                    as revenue,
        count(distinct f.order_id)      as orders
    from {{ ref('fact_order_items') }} as f
    join {{ ref('dim_date') }} as dd on dd.date_key = f.purchase_date_key
    where dd.date_key <> -1
    group by 1
)
select
    year_month,
    round(revenue, 2)  as revenue,
    orders,
    round(100.0 * (revenue - lag(revenue) over (order by year_month))
        / nullif(lag(revenue) over (order by year_month), 0), 1) as mom_growth_pct
from monthly
order by year_month;

-- companion: orders by hour of day
select
    f.purchase_hour                    as hour_of_day,
    count(distinct f.order_id)         as orders,
    round(sum(f.price), 2)             as revenue
from {{ ref('fact_order_items') }} as f
where f.purchase_hour is not null
group by 1
order by orders desc;


-- ----------------------------------------------------------------------------
-- Q3. Which payment method is used most, and which drives the highest average
--     ticket?
--     Fact: fact_order_payments | Dimension: dim_payment_type
--     Measures: COUNT(DISTINCT order_id), AVG(payment_value) non-additive
-- ----------------------------------------------------------------------------
select
    dpt.payment_label,
    count(distinct fp.order_id)                            as orders,
    round(sum(fp.payment_value), 2)                        as total_paid,
    round(avg(fp.payment_value), 2)                        as avg_transaction
from {{ ref('fact_order_payments') }} as fp
join {{ ref('dim_payment_type') }} as dpt on dpt.payment_type_key = fp.payment_type_key
where dpt.is_valid_method
group by 1
order by orders desc;


-- ----------------------------------------------------------------------------
-- Q4. Do instalment plans go with bigger baskets?
--     Fact: fact_order_payments | Dimension: (payment_installments banded)
--     Measures: COUNT(DISTINCT order_id), AVG(payment_value)
-- ----------------------------------------------------------------------------
select
    case
        when fp.payment_installments <= 1 then '1 (pay in full)'
        when fp.payment_installments <= 3 then '2-3'
        when fp.payment_installments <= 6 then '4-6'
        when fp.payment_installments <= 12 then '7-12'
        else '13+'
    end                                                   as instalments,
    count(distinct fp.order_id)                            as orders,
    round(avg(fp.payment_value), 2)                        as avg_payment,
    round(avg(fp.instalment_amount), 2)                    as avg_per_instalment
from {{ ref('fact_order_payments') }} as fp
where fp.payment_installments is not null
group by 1
order by min(fp.payment_installments);


-- ============================================================================
-- THEME B -- CUSTOMERS
-- ============================================================================

-- ----------------------------------------------------------------------------
-- Q5. What share of customers buy more than once, and how much of revenue do
--     repeat buyers account for?
--     Fact: fact_order_items | Dimension: dim_customers (customer_unique_id)
--     Measures: COUNT(DISTINCT order_id) frequency, SUM(price) monetary
-- ----------------------------------------------------------------------------
with per_person as (
    select
        dc.customer_unique_id,
        count(distinct f.order_id)      as orders,
        sum(f.price)                    as revenue
    from {{ ref('fact_order_items') }} as f
    join {{ ref('dim_customers') }} as dc on dc.customer_key = f.customer_key
    group by 1
)
select
    case when orders = 1 then 'One-time' else 'Repeat (2+)' end as customer_group,
    count(*)                                               as customers,
    round(100.0 * count(*) / sum(count(*)) over (), 1)     as pct_of_customers,
    round(sum(revenue), 2)                                 as revenue,
    round(100.0 * sum(revenue) / sum(sum(revenue)) over (), 1) as pct_of_revenue
from per_person
group by 1;


-- ----------------------------------------------------------------------------
-- Q6. Is revenue concentrated in the top 10% of customers (Pareto 80/20)?
--     Fact: fact_order_items | Dimension: dim_customers
--     Measure: SUM(price) with a cumulative window
-- ----------------------------------------------------------------------------
with per_person as (
    select dc.customer_unique_id, sum(f.price) as revenue
    from {{ ref('fact_order_items') }} as f
    join {{ ref('dim_customers') }} as dc on dc.customer_key = f.customer_key
    group by 1
),
ranked as (
    select
        revenue,
        row_number() over (order by revenue desc)          as rnk,
        count(*)     over ()                               as total_customers,
        sum(revenue) over (order by revenue desc
            rows between unbounded preceding and current row) as running_rev,
        sum(revenue) over ()                               as total_rev
    from per_person
),
bands as (
    select 100.0 * rnk / total_customers as pct_customers,
           100.0 * running_rev / total_rev as pct_revenue
    from ranked
)
select 'Top 1%'  as bucket, round(max(pct_revenue), 1) as pct_of_revenue from bands where pct_customers <= 1
union all select 'Top 5%',  round(max(pct_revenue), 1) from bands where pct_customers <= 5
union all select 'Top 10%', round(max(pct_revenue), 1) from bands where pct_customers <= 10
union all select 'Top 20%', round(max(pct_revenue), 1) from bands where pct_customers <= 20;


-- ============================================================================
-- THEME C -- GEOGRAPHY  (the conformed dim_geography earns its keep here)
-- ============================================================================

-- ----------------------------------------------------------------------------
-- Q7. Which region and state generate the most revenue?
--     Fact: fact_order_items | Dimension: dim_geography via customer_geography_key
--           (Region -> State hierarchy)
--     Measure: SUM(price), COUNT(DISTINCT order_id)
-- ----------------------------------------------------------------------------
select
    dg.region,
    dg.state,
    count(distinct f.order_id)                             as orders,
    round(sum(f.price), 2)                                 as revenue,
    round(sum(f.price) / count(distinct f.order_id), 2)    as avg_order_value
from {{ ref('fact_order_items') }} as f
join {{ ref('dim_geography') }} as dg on dg.geography_key = f.customer_geography_key
where dg.geography_key <> -1
group by 1, 2
order by revenue desc
limit 15;


-- ----------------------------------------------------------------------------
-- Q8. Does the distance between buyer and seller affect the review score?
--     Fact: fact_order_items (buyer_seller_distance_km, computed from the two
--           role-playing geography keys) joined to fact_order_reviews on order.
--     Measures: AVG(buyer_seller_distance_km), AVG(review_score)
-- ----------------------------------------------------------------------------
with item_distance as (
    select order_id, avg(buyer_seller_distance_km) as distance_km
    from {{ ref('fact_order_items') }}
    where buyer_seller_distance_km is not null
    group by 1
),
order_score as (
    select order_id, avg(review_score) as review_score
    from {{ ref('fact_order_reviews') }}
    group by 1
)
select
    case
        when d.distance_km < 100  then '1. under 100 km'
        when d.distance_km < 500  then '2. 100-500 km'
        when d.distance_km < 1500 then '3. 500-1500 km'
        else '4. over 1500 km'
    end                                                   as distance_band,
    count(*)                                               as orders,
    round(avg(d.distance_km), 0)                           as avg_km,
    round(avg(s.review_score), 2)                          as avg_review_score
from item_distance as d
join order_score  as s on s.order_id = d.order_id
group by 1
order by 1;


-- ============================================================================
-- THEME D -- DELIVERY  (dim_date role-playing does the work here)
-- ============================================================================

-- ----------------------------------------------------------------------------
-- Q9. On average, how many days does delivery take, and how is that split
--     between the seller preparing the parcel and the carrier moving it?
--     Fact: fact_order_items | Dimension: dim_date (purchased / to-carrier /
--           delivered roles)
--     Measures: AVG(delivery_days), AVG(seller_processing_days),
--               AVG(carrier_transit_days) -- all non-additive
-- ----------------------------------------------------------------------------
select
    dd.year,
    round(avg(f.delivery_days), 1)                         as avg_total_days,
    round(avg(f.seller_processing_days), 1)                as avg_seller_days,
    round(avg(f.carrier_transit_days), 1)                  as avg_carrier_days,
    count(*)                                               as delivered_items
from {{ ref('fact_order_items') }} as f
join {{ ref('dim_date') }} as dd on dd.date_key = f.delivered_date_key
where dd.date_key <> -1
group by 1
order by 1;


-- ----------------------------------------------------------------------------
-- Q10. How often do parcels arrive after the promised date, and by how many
--      days -- broken down by region?
--      Fact: fact_order_items | Dimensions: dim_date (delivered vs estimated
--            roles), dim_geography
--      Measures: AVG(delivery_delay_days), rate of is_late_delivery (semi-additive)
-- ----------------------------------------------------------------------------
select
    dg.region,
    count(*)                                               as delivered_items,
    round(100.0 * avg(f.is_late_delivery), 1)              as late_rate_pct,
    round(avg(f.delivery_delay_days), 1)                   as avg_delay_days,
    round(avg(case when f.is_late_delivery = 1
                   then f.delivery_delay_days end), 1)     as avg_delay_when_late
from {{ ref('fact_order_items') }} as f
join {{ ref('dim_geography') }} as dg on dg.geography_key = f.customer_geography_key
where f.is_late_delivery is not null
  and dg.geography_key <> -1
group by 1
order by late_rate_pct desc;


-- ============================================================================
-- THEME E -- PRODUCTS & OPERATIONS
-- ============================================================================

-- ----------------------------------------------------------------------------
-- Q11. Which categories carry the highest freight cost as a share of price?
--      Fact: fact_order_items | Dimension: dim_products (category, size_band)
--      Measures: SUM(freight_value), SUM(price), ratio (non-additive)
-- ----------------------------------------------------------------------------
select
    dp.category,
    dp.size_band,
    count(*)                                               as items_sold,
    round(sum(f.price), 2)                                 as revenue,
    round(sum(f.freight_value), 2)                         as freight,
    round(100.0 * sum(f.freight_value) / nullif(sum(f.price), 0), 1) as freight_pct_of_price
from {{ ref('fact_order_items') }} as f
join {{ ref('dim_products') }} as dp on dp.product_key = f.product_key
group by 1, 2
having count(*) >= 50
order by freight_pct_of_price desc
limit 15;


-- ----------------------------------------------------------------------------
-- Q12. Where do orders drop out of the lifecycle -- what is the mix of order
--      statuses, and how much revenue sits in non-delivered states?
--      Fact: fact_order_items | Dimension: dim_order_status (lifecycle_step)
--      Measures: COUNT(DISTINCT order_id), SUM(price)
-- ----------------------------------------------------------------------------
select
    dos.lifecycle_step,
    dos.status_label,
    count(distinct f.order_id)                             as orders,
    round(sum(f.price), 2)                                 as revenue,
    round(100.0 * sum(f.price) / sum(sum(f.price)) over (), 2) as pct_of_revenue
from {{ ref('fact_order_items') }} as f
join {{ ref('dim_order_status') }} as dos on dos.order_status_key = f.order_status_key
group by 1, 2
order by dos.lifecycle_step;


-- ============================================================================
-- THEME F -- DRILL-ACROSS: questions that need TWO fact tables.
--
-- Each query aggregates two facts separately to their common grain, then joins
-- on a CONFORMED dimension. Aggregating first is essential -- joining the raw
-- facts would multiply rows together and inflate every total.
-- ============================================================================

-- ----------------------------------------------------------------------------
-- Q13. DRILL-ACROSS (fact_order_items + fact_order_payments, conformed on the
--      order and dim_date).
--      Does the amount a customer pays match the value of the items in the
--      basket, and does the gap grow with instalment plans (interest)?
--      Neither fact can answer this: item value lives in fact_order_items,
--      the amount paid lives in fact_order_payments, and they sit at
--      different grains.
-- ----------------------------------------------------------------------------
with basket as (
    select order_id, sum(total_item_value) as basket_value
    from {{ ref('fact_order_items') }}
    group by 1
),
paid as (
    select
        order_id,
        sum(payment_value)        as amount_paid,
        max(payment_installments) as max_instalments
    from {{ ref('fact_order_payments') }}
    group by 1
)
select
    case
        when p.max_instalments <= 1 then '1 (pay in full)'
        when p.max_instalments <= 6 then '2-6'
        else '7+'
    end                                                   as instalments,
    count(*)                                               as orders,
    round(avg(b.basket_value), 2)                          as avg_basket_value,
    round(avg(p.amount_paid), 2)                           as avg_amount_paid,
    round(avg(p.amount_paid - b.basket_value), 2)          as avg_gap
from basket as b
join paid as p on p.order_id = b.order_id
group by 1
order by 1;


-- ----------------------------------------------------------------------------
-- Q14. DRILL-ACROSS (fact_order_items + fact_order_reviews, conformed on the
--      order, dim_customers and dim_date).
--      How much does a late delivery cost in review score, and does the size
--      of the delay matter?
-- ----------------------------------------------------------------------------
with delivery as (
    select
        order_id,
        max(is_late_delivery)    as was_late,
        avg(delivery_delay_days) as delay_days,
        avg(delivery_days)       as delivery_days
    from {{ ref('fact_order_items') }}
    where is_late_delivery is not null
    group by 1
),
review as (
    select order_id, avg(review_score) as review_score
    from {{ ref('fact_order_reviews') }}
    group by 1
)
select
    case
        when d.was_late = 0                       then 'On time or early'
        when d.delay_days < 3                     then 'Late by 1-2 days'
        when d.delay_days < 7                     then 'Late by 3-6 days'
        else 'Late by a week or more'
    end                                                   as delivery_outcome,
    count(*)                                               as orders,
    round(avg(d.delivery_days), 1)                         as avg_delivery_days,
    round(avg(r.review_score), 2)                          as avg_review_score
from delivery as d
join review as r on r.order_id = d.order_id
group by 1
order by avg_review_score desc;


-- ----------------------------------------------------------------------------
-- Q15. DRILL-ACROSS (fact_order_payments + fact_order_reviews, conformed on the
--      order, dim_customers and dim_date).
--      Are customers who pay in instalments more or less satisfied than those
--      who pay in full?
-- ----------------------------------------------------------------------------
with payment as (
    select
        order_id,
        max(payment_installments)                          as max_instalments,
        bool_or(is_instalment_plan)                        as used_instalments
    from {{ ref('fact_order_payments') }}
    group by 1
),
review as (
    select
        order_id,
        avg(review_score)  as review_score,
        avg(has_comment)   as comment_rate
    from {{ ref('fact_order_reviews') }}
    group by 1
)
select
    case when p.used_instalments then 'Paid in instalments' else 'Paid in full' end as payment_style,
    count(*)                                               as orders,
    round(avg(p.max_instalments), 1)                       as avg_instalments,
    round(avg(r.review_score), 2)                          as avg_review_score,
    round(100.0 * avg(r.comment_rate), 1)                  as pct_left_a_comment
from payment as p
join review as r on r.order_id = p.order_id
group by 1
order by avg_review_score desc;

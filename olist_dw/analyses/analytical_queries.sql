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
-- Each question header names the fact table(s), the dimension(s) it travels
-- through, and the measure(s) it aggregates, so the link from question to
-- model is explicit.
--
-- Q6, Q12 and Q13 are DRILL-ACROSS queries: they aggregate two fact tables to
-- a common grain and join the results on a CONFORMED dimension. They are why
-- this warehouse is a fact constellation and not a single star -- no one fact
-- can answer them.
-- ============================================================================


-- ============================================================================
-- Q1. หมวดหมู่สินค้าใดมียอดขายรวมและจำนวนสินค้าที่ขายสูงที่สุด?
--     Fact: fact_order_items | Dimension: dim_products (category)
--     Measures: SUM(price) additive, COUNT(*) additive
-- ============================================================================
select
    dp.category                                            as product_category,
    count(*)                                               as items_sold,
    round(sum(f.price), 2)                                 as total_revenue,
    round(sum(f.freight_value), 2)                         as total_freight
from {{ ref('fact_order_items') }} as f
join {{ ref('dim_products') }} as dp on dp.product_key = f.product_key
group by 1
order by total_revenue desc
limit 15;


-- ============================================================================
-- Q2. ยอดขายและจำนวนคำสั่งซื้อมีแนวโน้มเปลี่ยนแปลงอย่างไรในแต่ละเดือนและปี?
--     Fact: fact_order_items | Dimension: dim_date (year, month roll-up)
--     Measures: SUM(price), COUNT(DISTINCT order_id), month-over-month growth %
-- ============================================================================
with monthly as (
    select
        dd.year,
        dd.year_month,
        sum(f.price)                   as revenue,
        count(distinct f.order_id)     as orders
    from {{ ref('fact_order_items') }} as f
    join {{ ref('dim_date') }} as dd on dd.date_key = f.purchase_date_key
    where dd.date_key <> -1
    group by 1, 2
)
select
    year_month,
    round(revenue, 2)  as revenue,
    orders,
    round(100.0 * (revenue - lag(revenue) over (order by year_month))
        / nullif(lag(revenue) over (order by year_month), 0), 1) as mom_growth_pct
from monthly
order by year_month;

-- companion: totals per year
select
    dd.year,
    round(sum(f.price), 2)             as revenue,
    count(distinct f.order_id)         as orders
from {{ ref('fact_order_items') }} as f
join {{ ref('dim_date') }} as dd on dd.date_key = f.purchase_date_key
where dd.date_key <> -1
group by 1
order by 1;


-- ============================================================================
-- Q3. หมวดหมู่สินค้าใดมีราคาเฉลี่ยต่อชิ้นสูงที่สุด และมีจำนวนการขายมากน้อยเพียงใด?
--     Fact: fact_order_items | Dimension: dim_products (category)
--     Measures: AVG(price) non-additive, COUNT(*) additive
--     (HAVING COUNT >= 30 กันหมวดหมู่ที่มีตัวอย่างน้อยเกินไป)
-- ============================================================================
select
    dp.category                                            as product_category,
    count(*)                                               as items_sold,
    round(avg(f.price), 2)                                 as avg_price_per_item,
    round(min(f.price), 2)                                 as min_price,
    round(max(f.price), 2)                                 as max_price
from {{ ref('fact_order_items') }} as f
join {{ ref('dim_products') }} as dp on dp.product_key = f.product_key
group by 1
having count(*) >= 30
order by avg_price_per_item desc
limit 15;


-- ============================================================================
-- Q4. ลูกค้าในรัฐและเมืองใดสร้างยอดขายรวมสูงที่สุด?
--     Fact: fact_order_items | Dimension: dim_geography via customer_geography_key
--           (Region -> State -> City hierarchy)
--     Measures: SUM(price), COUNT(DISTINCT order_id)
-- ============================================================================
select
    dg.region,
    dg.state,
    dg.city,
    count(distinct f.order_id)                             as orders,
    round(sum(f.price), 2)                                 as total_revenue
from {{ ref('fact_order_items') }} as f
join {{ ref('dim_geography') }} as dg on dg.geography_key = f.customer_geography_key
where dg.geography_key <> -1
group by 1, 2, 3
order by total_revenue desc
limit 20;


-- ============================================================================
-- Q5. ลูกค้าที่กลับมาซื้อซ้ำคิดเป็นกี่เปอร์เซ็นต์ของลูกค้าทั้งหมด?
--     Fact: fact_order_items | Dimension: dim_customers (customer_unique_id)
--     Measure: COUNT(DISTINCT order_id) per person
-- ============================================================================
with per_person as (
    select
        dc.customer_unique_id,
        count(distinct f.order_id)     as orders,
        sum(f.price)                   as revenue
    from {{ ref('fact_order_items') }} as f
    join {{ ref('dim_customers') }} as dc on dc.customer_key = f.customer_key
    group by 1
)
select
    case when orders = 1 then 'One-time buyer' else 'Repeat buyer (2+)' end as customer_group,
    count(*)                                               as customers,
    round(100.0 * count(*) / sum(count(*)) over (), 1)     as pct_of_customers,
    round(sum(revenue), 2)                                 as revenue,
    round(100.0 * sum(revenue) / sum(sum(revenue)) over (), 1) as pct_of_revenue
from per_person
group by 1
order by customers desc;


-- ============================================================================
-- Q6. DRILL-ACROSS (fact_order_items + fact_order_payments, conformed on the
--     order and dim_date).
--     ยอดที่ลูกค้าจ่ายจริงตรงกับมูลค่าสินค้าในตะกร้าหรือไม่ และช่องว่างขยายตาม
--     จำนวนงวดผ่อนไหม (ดอกเบี้ย)?
--     Item value lives in fact_order_items -- amount paid lives in
--     fact_order_payments -- the two sit at different grains, so this cannot be
--     answered from either fact alone.
-- ============================================================================
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
        when p.max_instalments <= 3 then '2-3'
        when p.max_instalments <= 6 then '4-6'
        when p.max_instalments <= 12 then '7-12'
        else '13+'
    end                                                   as instalments,
    count(*)                                               as orders,
    round(avg(b.basket_value), 2)                          as avg_basket_value,
    round(avg(p.amount_paid), 2)                           as avg_amount_paid,
    round(avg(p.amount_paid - b.basket_value), 2)          as avg_gap
from basket as b
join paid as p on p.order_id = b.order_id
group by 1
order by min(p.max_instalments);


-- ============================================================================
-- Q7. RFM Analysis: ลูกค้ากลุ่มใดมีมูลค่า (Monetary) และความถี่ (Frequency)
--     ในการซื้อสูงที่สุด?
--     Fact: fact_order_items | Dimension: dim_customers + dim_date
--     Measures: Recency = days since last order, Frequency = COUNT(order_id),
--               Monetary = SUM(price)  -- then NTILE(5) quintiles
-- ============================================================================
with customer_orders as (
    select
        dc.customer_unique_id,
        f.order_id,
        max(dd.full_date)  as order_date,
        sum(f.price)       as order_value
    from {{ ref('fact_order_items') }} as f
    join {{ ref('dim_customers') }} as dc on dc.customer_key   = f.customer_key
    join {{ ref('dim_date') }}      as dd on dd.date_key        = f.purchase_date_key
    where dd.date_key <> -1
    group by 1, 2
),
rfm as (
    select
        customer_unique_id,
        date_diff('day', max(order_date),
                  (select max(order_date) from customer_orders)) as recency_days,
        count(distinct order_id)                                 as frequency,
        sum(order_value)                                         as monetary
    from customer_orders
    group by 1
),
scored as (
    select
        customer_unique_id,
        recency_days,
        frequency,
        monetary,
        ntile(5) over (order by monetary) as monetary_quintile
    from rfm
)
select
    monetary_quintile,
    count(*)                                               as customers,
    round(avg(recency_days), 0)                            as avg_recency_days,
    round(avg(frequency), 2)                               as avg_frequency,
    round(avg(monetary), 2)                                as avg_monetary,
    round(100.0 * sum(monetary) / sum(sum(monetary)) over (), 1) as pct_of_revenue
from scored
group by 1
order by monetary_quintile desc;


-- ============================================================================
-- Q8. วิธีการชำระเงินใดถูกใช้งานมากที่สุด และมีมูลค่าการชำระเงินเฉลี่ยเท่าใด?
--     Fact: fact_order_payments | Dimension: dim_payment_type
--     Measures: COUNT(DISTINCT order_id), AVG(payment_value) non-additive
-- ============================================================================
select
    dpt.payment_label,
    count(distinct fp.order_id)                            as orders,
    round(sum(fp.payment_value), 2)                        as total_paid,
    round(avg(fp.payment_value), 2)                        as avg_payment_value,
    round(avg(fp.payment_installments), 1)                 as avg_installments
from {{ ref('fact_order_payments') }} as fp
join {{ ref('dim_payment_type') }} as dpt on dpt.payment_type_key = fp.payment_type_key
where dpt.is_valid_method
group by 1
order by orders desc;


-- ============================================================================
-- Q9. ผู้ขายในรัฐหรือเมืองใดมีระยะเวลาเตรียมสินค้าเฉลี่ยสูงที่สุด?
--     Fact: fact_order_items | Dimension: dim_sellers (state)
--     Measure: AVG(seller_processing_days) non-additive
--     (HAVING COUNT >= 50 -- ผู้ขายกระจายรายเมืองมาก จึงสรุปที่ระดับรัฐ)
-- ============================================================================
select
    ds.state                                               as seller_state,
    count(distinct ds.seller_id)                           as sellers,
    count(*)                                               as items_shipped,
    round(avg(f.seller_processing_days), 1)                as avg_processing_days,
    round(avg(f.carrier_transit_days), 1)                  as avg_carrier_days
from {{ ref('fact_order_items') }} as f
join {{ ref('dim_sellers') }} as ds on ds.seller_key = f.seller_key
where f.seller_processing_days is not null
  and ds.seller_id <> 'unknown'
group by 1
having count(*) >= 50
order by avg_processing_days desc;


-- ============================================================================
-- Q10. ระยะเวลาขนส่งและความล่าช้าในการจัดส่งแตกต่างกันอย่างไรในแต่ละเดือน?
--      Fact: fact_order_items | Dimension: dim_date (delivered date role)
--      Measures: AVG(delivery_days), AVG(carrier_transit_days),
--                AVG(delivery_delay_days), rate of is_late_delivery
-- ============================================================================
select
    dd.year_month,
    count(*)                                               as delivered_items,
    round(avg(f.delivery_days), 1)                         as avg_delivery_days,
    round(avg(f.carrier_transit_days), 1)                  as avg_carrier_days,
    round(100.0 * avg(f.is_late_delivery), 1)              as late_rate_pct,
    round(avg(f.delivery_delay_days), 1)                   as avg_delay_days
from {{ ref('fact_order_items') }} as f
join {{ ref('dim_date') }} as dd on dd.date_key = f.delivered_date_key
where dd.date_key <> -1
  and f.delivery_days is not null
group by 1
order by 1;


-- ============================================================================
-- Q11. หมวดหมู่สินค้าใดมีสัดส่วนค่าจัดส่งต่อราคาสินค้าสูงที่สุด?
--      Fact: fact_order_items | Dimension: dim_products (category, size_band)
--      Measures: SUM(freight_value), SUM(price), ratio (non-additive)
-- ============================================================================
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


-- ============================================================================
-- Q12. DRILL-ACROSS (fact_order_items + fact_order_reviews, conformed on the
--      order and dim_products).
--      หมวดหมู่สินค้าใดมีคะแนนรีวิวเฉลี่ยสูงที่สุดและต่ำที่สุด?
--      Category lives on fact_order_items -- the review score lives on
--      fact_order_reviews -- they are joined at the order grain.
-- ============================================================================
with order_category as (
    -- each order's dominant category (by item count)
    select order_id, category
    from (
        select
            f.order_id,
            dp.category,
            row_number() over (
                partition by f.order_id order by count(*) desc
            ) as rn
        from {{ ref('fact_order_items') }} as f
        join {{ ref('dim_products') }} as dp on dp.product_key = f.product_key
        group by 1, 2
    )
    where rn = 1
),
order_score as (
    select order_id, avg(review_score) as review_score
    from {{ ref('fact_order_reviews') }}
    group by 1
)
select
    oc.category                                            as product_category,
    count(*)                                               as orders_reviewed,
    round(avg(os.review_score), 2)                         as avg_review_score
from order_category as oc
join order_score    as os on os.order_id = oc.order_id
group by 1
having count(*) >= 50
order by avg_review_score desc;


-- ============================================================================
-- Q13. DRILL-ACROSS (fact_order_items + fact_order_reviews, conformed on the
--      order, dim_customers and dim_date).
--      คะแนนรีวิวได้รับผลกระทบจากอะไรมากกว่ากัน -- การส่งช้า หรือระยะทาง
--      ระหว่างผู้ซื้อกับผู้ขาย?
--      buyer_seller_distance_km is computed from the two role-playing geography
--      keys on fact_order_items -- the review score lives on fact_order_reviews.
-- ============================================================================
-- 13a -- by late/on-time
with delivery as (
    select
        order_id,
        max(is_late_delivery)    as was_late,
        avg(delivery_delay_days) as delay_days
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
        when d.was_late = 0            then '1. On time or early'
        when d.delay_days < 3          then '2. Late 1-2 days'
        when d.delay_days < 7          then '3. Late 3-6 days'
        else                               '4. Late a week or more'
    end                                                   as delivery_outcome,
    count(*)                                               as orders,
    round(avg(r.review_score), 2)                          as avg_review_score
from delivery as d
join review   as r on r.order_id = d.order_id
group by 1
order by 1;

-- 13b -- by buyer-seller distance
with dist as (
    select order_id, avg(buyer_seller_distance_km) as distance_km
    from {{ ref('fact_order_items') }}
    where buyer_seller_distance_km is not null
    group by 1
),
review as (
    select order_id, avg(review_score) as review_score
    from {{ ref('fact_order_reviews') }}
    group by 1
)
select
    case
        when d.distance_km < 100  then '1. under 100 km'
        when d.distance_km < 500  then '2. 100-500 km'
        when d.distance_km < 1500 then '3. 500-1500 km'
        else                           '4. over 1500 km'
    end                                                   as distance_band,
    count(*)                                               as orders,
    round(avg(d.distance_km), 0)                           as avg_km,
    round(avg(r.review_score), 2)                          as avg_review_score
from dist   as d
join review as r on r.order_id = d.order_id
group by 1
order by 1;


-- ============================================================================
-- Q14. ผู้ขายกลุ่ม Top 10% สร้างยอดขายคิดเป็นกี่เปอร์เซ็นต์ของยอดขายทั้งหมด?
--      (Pareto 80/20)
--      Fact: fact_order_items | Dimension: dim_sellers
--      Measure: SUM(price) with a cumulative window
-- ============================================================================
with seller_revenue as (
    select f.seller_key, sum(f.price) as revenue
    from {{ ref('fact_order_items') }} as f
    group by 1
),
ranked as (
    select
        revenue,
        row_number() over (order by revenue desc)          as rnk,
        count(*)     over ()                               as total_sellers,
        sum(revenue) over (order by revenue desc
            rows between unbounded preceding and current row) as running_revenue,
        sum(revenue) over ()                               as total_revenue
    from seller_revenue
),
bands as (
    select
        100.0 * rnk / total_sellers            as pct_sellers,
        100.0 * running_revenue / total_revenue as pct_revenue
    from ranked
)
select 'Top 1%'  as seller_bucket, round(max(pct_revenue), 1) as pct_of_total_revenue from bands where pct_sellers <=  1
union all
select 'Top 5%',  round(max(pct_revenue), 1) from bands where pct_sellers <=  5
union all
select 'Top 10%', round(max(pct_revenue), 1) from bands where pct_sellers <= 10
union all
select 'Top 20%', round(max(pct_revenue), 1) from bands where pct_sellers <= 20;


-- ============================================================================
-- Q15. Market Basket Analysis: สินค้าคู่ (หมวดหมู่) ใดถูกซื้อร่วมกันบ่อยที่สุด?
--      Fact: fact_order_items (self-join on order_id) | Dimension: dim_products
--      Measure: COUNT(*) co-occurrence
-- ============================================================================
with order_categories as (
    select distinct f.order_id, dp.category
    from {{ ref('fact_order_items') }} as f
    join {{ ref('dim_products') }} as dp on dp.product_key = f.product_key
    where dp.category <> 'unknown'
)
select
    a.category                                             as category_a,
    b.category                                             as category_b,
    count(*)                                               as orders_bought_together
from order_categories as a
join order_categories as b
    on a.order_id = b.order_id
   and a.category < b.category
group by 1, 2
order by orders_bought_together desc
limit 15;

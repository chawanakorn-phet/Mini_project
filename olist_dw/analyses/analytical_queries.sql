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
-- Q5, Q9 and Q15 are DRILL-ACROSS queries: they aggregate two fact tables to
-- a common grain (the order) and join the results on a CONFORMED dimension
-- (the order_id itself, plus dim_products for Q15). They are why this
-- warehouse is a fact constellation and not a single star -- no one fact
-- can answer them.
-- ============================================================================


-- ============================================================================
-- Q1. แต่ละเดือนหมวดหมู่สินค้าใดสร้างยอดขายสูงที่สุด?
--     Fact: fact_order_items | Dimension: dim_products (category) + dim_date (month)
--     Measure: SUM(price) -- pick the category with the highest sum per month
-- ============================================================================
with monthly_category as (
    select
        d.year,
        d.month,
        d.month_name,
        p.category,
        sum(f.price) as revenue
    from {{ ref('fact_order_items') }} as f
    join {{ ref('dim_date') }} as d on d.date_key = f.purchase_date_key
    join {{ ref('dim_products') }} as p on p.product_key = f.product_key
    where p.category <> 'unknown'
    group by 1, 2, 3, 4
),
ranked as (
    select
        *,
        row_number() over (partition by year, month order by revenue desc) as rn
    from monthly_category
)
select year, month, month_name, category as top_category, round(revenue, 2) as revenue
from ranked
where rn = 1
order by year, month;


-- ============================================================================
-- Q2. ในแต่ละปี เดือนใดมียอดขายสูงที่สุด?
--     Fact: fact_order_items | Dimension: dim_date (year -> month)
--     Measure: SUM(price) -- pick the month with the highest sum per year
-- ============================================================================
with monthly as (
    select d.year, d.month, d.month_name, sum(f.price) as revenue
    from {{ ref('fact_order_items') }} as f
    join {{ ref('dim_date') }} as d on d.date_key = f.purchase_date_key
    group by 1, 2, 3
),
ranked as (
    select *, row_number() over (partition by year order by revenue desc) as rn
    from monthly
)
select year, month, month_name, round(revenue, 2) as revenue
from ranked
where rn = 1
order by year;


-- ============================================================================
-- Q3. แต่ละปีสินค้าแต่ละหมวดหมู่มียอดขายแตกต่างกันเท่าใด?
--     Fact: fact_order_items | Dimension: dim_products (category) + dim_date (year)
--     Measure: SUM(price) เทียบข้ามปี -- top 8 categories by all-time revenue
-- ============================================================================
with yearly_category as (
    select d.year, p.category, sum(f.price) as revenue
    from {{ ref('fact_order_items') }} as f
    join {{ ref('dim_date') }} as d on d.date_key = f.purchase_date_key
    join {{ ref('dim_products') }} as p on p.product_key = f.product_key
    where p.category <> 'unknown'
    group by 1, 2
),
top_categories as (
    select category
    from yearly_category
    group by category
    order by sum(revenue) desc
    limit 8
)
select yc.year, yc.category, round(yc.revenue, 2) as revenue
from yearly_category as yc
join top_categories as tc on tc.category = yc.category
order by yc.category, yc.year;


-- ============================================================================
-- Q4. หมวดหมู่สินค้าใดที่ถูกยกเลิกมากที่สุด?
--     Fact: fact_order_items | Dimension: dim_products (category) + dim_order_status
--     Measure: COUNT(*) เฉพาะสถานะ canceled
--
--     ข้อนี้เดิมตั้งเป็น "ระยะเวลาจัดส่งมีผลต่อการยกเลิกไหม" แต่ตรวจข้อมูลจริงแล้วพบว่า
--     ออเดอร์ที่ถูกยกเลิกมีแค่ 542 จาก 112,650 แถว (0.5%) และมีเพียง 7 แถวที่มีค่า
--     delivery_days (ถูกยกเลิกก่อนจัดส่งจริง จึงไม่มีวันที่ส่งของให้คำนวณ) -- ตัวอย่างน้อย
--     เกินจะสรุปแนวโน้มได้ จึงเปลี่ยนตัวแปรต้นเป็นหมวดหมู่สินค้าแทน
-- ============================================================================
select
    p.category,
    count(*) as cancelled_items
from {{ ref('fact_order_items') }} as f
join {{ ref('dim_order_status') }} as os on os.order_status_key = f.order_status_key
join {{ ref('dim_products') }} as p on p.product_key = f.product_key
where os.order_status = 'canceled'
  and p.category <> 'unknown'
group by 1
order by cancelled_items desc
limit 15;


-- ============================================================================
-- Q5. DRILL-ACROSS (fact_order_items + fact_order_reviews, conformed on the
--     order).
--     ระยะเวลาขนส่งสินค้ามีผลต่อคะแนนรีวิวหรือไม่?
--     Delivery time lives on fact_order_items -- the review score lives on
--     fact_order_reviews -- they are joined at the order grain.
-- ============================================================================
with delivery as (
    select order_id, avg(delivery_days) as delivery_days
    from {{ ref('fact_order_items') }}
    where delivery_days is not null
    group by 1
),
review as (
    select order_id, avg(review_score) as review_score
    from {{ ref('fact_order_reviews') }}
    group by 1
)
select
    case
        when d.delivery_days < 7  then '1. น้อยกว่า 7 วัน'
        when d.delivery_days < 14 then '2. 7-13 วัน'
        when d.delivery_days < 21 then '3. 14-20 วัน'
        else '4. 21 วันขึ้นไป'
    end as delivery_bucket,
    count(*) as orders,
    round(avg(r.review_score), 2) as avg_review_score
from delivery as d
join review as r on r.order_id = d.order_id
group by 1
order by 1;


-- ============================================================================
-- Q6. ราคาสินค้ามีผลต่อค่าส่งหรือไม่?
--     Fact: fact_order_items | Measure: price (bucket) vs AVG(freight_value)
-- ============================================================================
select
    case
        when price < 50   then '1. ต่ำกว่า R$50'
        when price < 100  then '2. R$50-99'
        when price < 200  then '3. R$100-199'
        when price < 400  then '4. R$200-399'
        else '5. R$400 ขึ้นไป'
    end as price_bucket,
    count(*) as items,
    round(avg(freight_value), 2) as avg_freight
from {{ ref('fact_order_items') }}
group by 1
order by 1;


-- ============================================================================
-- Q7. ขนาดสินค้ามีผลต่อค่าส่งหรือไม่?
--     Fact: fact_order_items | Dimension: dim_products (size_band)
--     Measure: AVG(freight_value) ต่อ size_band
-- ============================================================================
select
    p.size_band,
    count(*) as items,
    round(avg(f.freight_value), 2) as avg_freight
from {{ ref('fact_order_items') }} as f
join {{ ref('dim_products') }} as p on p.product_key = f.product_key
where p.size_band <> 'Unknown'
group by 1
order by avg_freight;


-- ============================================================================
-- Q8. น้ำหนักสินค้ามีผลต่อค่าส่งหรือไม่?
--     Fact: fact_order_items | Dimension: dim_products (weight_g, bucket)
--     Measure: AVG(freight_value)
-- ============================================================================
select
    case
        when p.weight_g < 500   then '1. น้อยกว่า 500 กรัม'
        when p.weight_g < 2000  then '2. 500 กรัม - 2 กก.'
        when p.weight_g < 5000  then '3. 2-5 กก.'
        when p.weight_g < 10000 then '4. 5-10 กก.'
        else '5. มากกว่า 10 กก.'
    end as weight_bucket,
    count(*) as items,
    round(avg(f.freight_value), 2) as avg_freight
from {{ ref('fact_order_items') }} as f
join {{ ref('dim_products') }} as p on p.product_key = f.product_key
where p.weight_g is not null
group by 1
order by 1;


-- ============================================================================
-- Q9. DRILL-ACROSS (fact_order_items + fact_order_reviews, conformed on the
--     order).
--     ค่าส่งมีผลต่อคะแนนรีวิวหรือไม่?
--     Freight % of basket value lives on fact_order_items -- the review score
--     lives on fact_order_reviews.
-- ============================================================================
with freight as (
    select order_id, sum(freight_value) as freight_value, sum(price) as basket_value
    from {{ ref('fact_order_items') }}
    group by 1
),
review as (
    select order_id, avg(review_score) as review_score
    from {{ ref('fact_order_reviews') }}
    group by 1
)
select
    case
        when 100.0 * f.freight_value / nullif(f.basket_value, 0) < 10 then '1. ต่ำกว่า 10%'
        when 100.0 * f.freight_value / nullif(f.basket_value, 0) < 20 then '2. 10-19%'
        when 100.0 * f.freight_value / nullif(f.basket_value, 0) < 30 then '3. 20-29%'
        else '4. 30% ขึ้นไป'
    end as freight_pct_bucket,
    count(*) as orders,
    round(avg(r.review_score), 2) as avg_review_score
from freight as f
join review as r on r.order_id = f.order_id
where f.basket_value > 0
group by 1
order by 1;


-- ============================================================================
-- Q10. ในแต่ละเดือน วิธีการชำระเงินใดถูกใช้มากที่สุด?
--      Fact: fact_order_payments | Dimension: dim_payment_type + dim_date (month)
--      Measure: COUNT(DISTINCT order_id) ต่อวิธีต่อเดือน
-- ============================================================================
select
    d.year,
    d.month,
    d.month_name,
    pt.payment_label,
    count(distinct fp.order_id) as orders
from {{ ref('fact_order_payments') }} as fp
join {{ ref('dim_date') }} as d on d.date_key = fp.purchase_date_key
join {{ ref('dim_payment_type') }} as pt on pt.payment_type_key = fp.payment_type_key
where pt.is_valid_method
group by 1, 2, 3, 4
order by 1, 2, orders desc;


-- ============================================================================
-- Q11. จำนวนรูปภาพของสินค้ามีผลต่อยอดคำสั่งซื้อหรือไม่?
--      Fact: fact_order_items | Dimension: dim_products (photos_qty, bucket)
--      Measure: COUNT(DISTINCT order_id), SUM(price)
-- ============================================================================
select
    case
        when p.photos_qty = 0  then '0 รูป'
        when p.photos_qty <= 2 then '1-2 รูป'
        when p.photos_qty <= 4 then '3-4 รูป'
        when p.photos_qty <= 6 then '5-6 รูป'
        else '7 รูปขึ้นไป'
    end as photo_bucket,
    min(p.photos_qty)               as sort_key,
    count(distinct f.order_id)      as orders,
    round(sum(f.price), 2)          as revenue
from {{ ref('fact_order_items') }} as f
join {{ ref('dim_products') }} as p on p.product_key = f.product_key
where p.photos_qty is not null
group by 1
order by sort_key;


-- ============================================================================
-- Q12. ช่วงเวลาไหนของวันที่มีปริมาณคำสั่งซื้อมากที่สุด?
--      Fact: fact_order_items | Dimension: dim_date (purchase_hour)
--      Measure: COUNT(DISTINCT order_id)
-- ============================================================================
select
    f.purchase_hour,
    count(distinct f.order_id) as orders
from {{ ref('fact_order_items') }} as f
where f.purchase_hour is not null
group by 1
order by 1;


-- ============================================================================
-- Q13. ในแต่ละเดือนสินค้าประเภทใดขายได้เยอะที่สุด (นับเป็นจำนวนชิ้น)?
--      Fact: fact_order_items | Dimension: dim_products (category) + dim_date (month)
--      Measure: COUNT(*) -- จำนวนชิ้น, ไม่ใช่มูลค่าเงินแบบ Q1
-- ============================================================================
with monthly_category as (
    select
        d.year,
        d.month,
        d.month_name,
        p.category,
        count(*) as units_sold
    from {{ ref('fact_order_items') }} as f
    join {{ ref('dim_date') }} as d on d.date_key = f.purchase_date_key
    join {{ ref('dim_products') }} as p on p.product_key = f.product_key
    where p.category <> 'unknown'
    group by 1, 2, 3, 4
),
ranked as (
    select
        *,
        row_number() over (partition by year, month order by units_sold desc) as rn
    from monthly_category
)
select year, month, month_name, category as top_category, units_sold
from ranked
where rn = 1
order by year, month;


-- ============================================================================
-- Q14. ขนาดสินค้ามีผลทำให้การส่งเกิดการล่าช้าหรือไม่?
--      Fact: fact_order_items | Dimension: dim_products (size_band)
--      Measure: AVG(is_late_delivery), AVG(delivery_delay_days) ต่อ size_band
-- ============================================================================
select
    p.size_band,
    count(*) as items,
    round(100.0 * avg(f.is_late_delivery), 1) as late_rate_pct,
    round(avg(case when f.is_late_delivery = 1 then f.delivery_delay_days end), 1) as avg_days_late
from {{ ref('fact_order_items') }} as f
join {{ ref('dim_products') }} as p on p.product_key = f.product_key
where p.size_band <> 'Unknown' and f.is_late_delivery is not null
group by 1
order by late_rate_pct desc;


-- ============================================================================
-- Q15. DRILL-ACROSS (fact_order_items + fact_order_payments, conformed on the
--      order and dim_products).
--      หมวดหมู่สินค้าใดมีการชำระแบบผ่อนสูงสุด?
--      Category lives on fact_order_items -- installments live on
--      fact_order_payments -- joined at the order grain.
-- ============================================================================
with order_category as (
    -- each order's dominant category (by item count)
    select order_id, category
    from (
        select
            f.order_id,
            p.category,
            row_number() over (
                partition by f.order_id order by count(*) desc
            ) as rn
        from {{ ref('fact_order_items') }} as f
        join {{ ref('dim_products') }} as p on p.product_key = f.product_key
        where p.category <> 'unknown'
        group by 1, 2
    )
    where rn = 1
),
order_payment as (
    select order_id, max(payment_installments) as installments
    from {{ ref('fact_order_payments') }}
    group by 1
)
select
    oc.category,
    count(*) as orders,
    round(avg(op.installments), 2) as avg_installments,
    round(100.0 * avg(case when op.installments > 1 then 1 else 0 end), 1) as pct_installment_orders
from order_category as oc
join order_payment as op on op.order_id = oc.order_id
group by 1
having count(*) >= 50
order by avg_installments desc
limit 15;

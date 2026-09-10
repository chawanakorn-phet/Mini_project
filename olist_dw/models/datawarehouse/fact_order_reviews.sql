-- FACT 3 of 3 -- how the customer felt about it.
--
-- Grain: one row per review PER ORDER (review_id + order_id). A third distinct
--        grain: a review belongs to a whole order, not to a product line and
--        not to a payment. Storing a review score on fact_order_items would
--        repeat it once per product line and double-count every average.
--
--        review_id alone is NOT the grain, which is easy to get wrong. Olist
--        reuses one review_id across several orders when a single survey
--        covers more than one purchase: 789 review_ids span 1,412 orders.
--        Partitioning on review_id alone silently discards 814 genuine
--        order-review pairs. The pair (review_id, order_id) is exactly unique
--        across all 99,224 source rows, so that is the declared grain, and
--        tests/assert_fact_order_reviews_grain_is_unique.sql holds it there.
--        Note also that 547 orders carry more than one review.
--
-- Connects to THREE dimensions, with dim_date role-playing three times
-- (order purchased / survey sent / customer answered). dim_customers,
-- dim_geography, dim_date and dim_order_status are all shared with the other
-- two facts, which is the join path for "does slow delivery lower the score?"
-- and "are instalment buyers happier?"
--
-- review_score is NON-ADDITIVE: it is an ordinal 1-5 rating, so it may be
-- averaged but never summed.

with reviews as (

    select * from {{ ref('stg_order_reviews') }}
),

orders as (

    select * from {{ ref('stg_orders') }}
),

customer as (

    select customer_key, customer_id, geography_key from {{ ref('dim_customers') }}
),

joined as (

    select
        -- Degenerate dimensions
        r.review_id,
        r.order_id,

        -- dim_date, role-playing three times
        coalesce(d_purchase.date_key, -1)                   as purchase_date_key,
        coalesce(d_created.date_key,  -1)                   as review_created_date_key,
        coalesce(d_answer.date_key,   -1)                   as review_answered_date_key,

        -- the remaining dimensions
        coalesce(dc.customer_key,      -1)                  as customer_key,
        coalesce(dc.geography_key,     -1)                  as customer_geography_key,
        coalesce(dos.order_status_key, -1)                  as order_status_key,

        -- Non-additive: an ordinal rating. AVG is meaningful, SUM is not.
        r.review_score,

        -- Non-additive: hours the customer took to answer the survey.
        date_diff('hour', r.review_creation_date, r.review_answer_timestamp)
                                                            as response_hours,

        -- Semi-additive flags: countable within a fixed set of reviews.
        case when r.review_comment_message is not null then 1 else 0 end
                                                            as has_comment,
        length(coalesce(r.review_comment_message, ''))      as comment_length,
        case when r.review_score >= 4 then 1 else 0 end      as is_positive,
        case when r.review_score <= 2 then 1 else 0 end      as is_negative,

        current_localtimestamp()                            as insertion_timestamp

    from reviews as r
    left join orders as o on o.order_id = r.order_id

    left join {{ ref('dim_date') }} as d_purchase
        on d_purchase.full_date = cast(o.order_purchase_timestamp as date)
    left join {{ ref('dim_date') }} as d_created
        on d_created.full_date  = cast(r.review_creation_date as date)
    left join {{ ref('dim_date') }} as d_answer
        on d_answer.full_date   = cast(r.review_answer_timestamp as date)

    left join customer                      as dc  on dc.customer_id  = o.customer_id
    left join {{ ref('dim_order_status') }} as dos on dos.order_status = o.order_status
),

deduplicated as (

    select
        *,
        row_number() over (
            partition by review_id, order_id
            order by order_id
        ) as row_num
    from joined
)

select * exclude (row_num)
from deduplicated
where row_num = 1

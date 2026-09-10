-- Each fact must hold exactly as many rows as its staged source.
with counts as (
    select 'fact_order_items' as table_name,
           (select count(*) from {{ ref('fact_order_items') }})  as warehouse_rows,
           (select count(*) from {{ ref('stg_order_items') }})   as source_rows
    union all
    select 'fact_order_payments',
           (select count(*) from {{ ref('fact_order_payments') }}),
           (select count(*) from {{ ref('stg_order_payments') }})
    union all
    select 'fact_order_reviews',
           (select count(*) from {{ ref('fact_order_reviews') }}),
           (select count(*) from {{ ref('stg_order_reviews') }})
)
select * from counts where warehouse_rows <> source_rows

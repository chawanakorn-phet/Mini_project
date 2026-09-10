-- Conformed date dimension -- shared by ALL THREE fact tables.
--
-- It also ROLE-PLAYS: fact_order_items joins to it five separate times
-- (purchased / approved / handed to carrier / delivered / promised), and
-- fact_order_reviews joins to it three times. One physical table, many
-- logical roles -- that is what a role-playing dimension means, and it is why
-- the old model's single unused dim_date was a problem.
--
-- The source has no date table, so we generate one spanning the full range of
-- the data (Sep 2016 - Oct 2018), padded to whole calendar years.
--
-- Surrogate key is the YYYYMMDD integer. Row -1 is the "Unknown" member, used
-- when a fact has no date -- an order that was never delivered, for example --
-- so those rows stay in the fact and totals remain complete.

with calendar as (

    select d as full_date
    from generate_series(date '2016-01-01', date '2018-12-31', interval 1 day) as t(d)
),

built as (

    select
        cast(strftime(full_date, '%Y%m%d') as integer)      as date_key,
        full_date,
        cast(date_part('year', full_date) as integer)       as year,
        cast(date_part('quarter', full_date) as integer)    as quarter,
        strftime(full_date, '%Y') || '-Q'
            || cast(date_part('quarter', full_date) as varchar) as year_quarter,
        cast(date_part('month', full_date) as integer)      as month,
        monthname(full_date)                                as month_name,
        strftime(full_date, '%Y-%m')                        as year_month,
        cast(date_part('day', full_date) as integer)        as day_of_month,
        cast(date_part('dow', full_date) as integer)        as day_of_week,
        dayname(full_date)                                  as day_name,
        case when date_part('dow', full_date) in (0, 6)
             then true else false end                       as is_weekend,
        cast(date_part('week', full_date) as integer)       as week_of_year
    from calendar
)

select * from built

union all

select -1, null, null, null, 'Unknown', null, 'Unknown', 'Unknown',
       null, null, 'Unknown', null, null

-- Conformed geography dimension -- the biggest structural change from the old
-- model.
--
-- The source keeps location as loose columns on both the customer and the
-- seller table, plus a 1,000,163-row geolocation lookup holding many
-- coordinate rows per zip prefix. Modelling location ONCE, here, means:
--
--   * customer location and seller location become the SAME dimension, so
--     "which state buys" and "which state sells" roll up identically;
--   * fact_order_items ROLE-PLAYS it twice (buyer geography, seller geography),
--     which is what makes buyer-to-seller distance analysis possible;
--   * all three facts share it, which makes it conformed.
--
-- Cleaning done here:
--   * the many coordinates per zip prefix are averaged down to a single point;
--   * city names are lower-cased and trimmed, because the source spells the
--     same city with inconsistent casing and spacing;
--   * Brazilian states roll up into their five official regions, giving a real
--     hierarchy: Region -> State -> City -> Zip prefix.

with geolocation as (

    select * from {{ ref('stg_geolocation') }}
),

per_zip as (

    select
        geolocation_zip_code_prefix                         as zip_code_prefix,
        avg(geolocation_lat)                                as latitude,
        avg(geolocation_lng)                                as longitude,
        -- the most frequently recorded city/state for this prefix
        mode(lower(trim(geolocation_city)))                 as city,
        mode(upper(trim(geolocation_state)))                as state
    from geolocation
    group by 1
)

select
    cast(row_number() over (order by zip_code_prefix) as integer) as geography_key,
    zip_code_prefix,
    city,
    state,
    case
        when state in ('AC', 'AP', 'AM', 'PA', 'RO', 'RR', 'TO')            then 'Norte'
        when state in ('AL', 'BA', 'CE', 'MA', 'PB', 'PE', 'PI', 'RN', 'SE') then 'Nordeste'
        when state in ('DF', 'GO', 'MT', 'MS')                              then 'Centro-Oeste'
        when state in ('ES', 'MG', 'RJ', 'SP')                              then 'Sudeste'
        when state in ('PR', 'RS', 'SC')                                    then 'Sul'
        else 'Unknown'
    end                                                     as region,
    latitude,
    longitude
from per_zip

union all

select -1, -1, 'unknown', 'XX', 'Unknown', null, null

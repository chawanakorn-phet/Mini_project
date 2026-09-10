-- Product dimension for fact_order_items.
--
-- Cleaning and enrichment done here:
--   * category names are translated to English by joining the source's own
--     translation table; COALESCE keeps the Portuguese name when no
--     translation exists, so the column is never NULL and never silently
--     drops a product from a category roll-up;
--   * the source misspells two column names ("lenght"); they are corrected
--     here so nothing downstream has to repeat the typo;
--   * package volume is derived from the three dimension columns, and a
--     readable size band is banded off it -- freight cost in this dataset is
--     driven by size, so this turns a raw number into something a business
--     reader can group by.

with products as (

    select * from {{ ref('stg_products') }}
),

translation as (

    select * from {{ ref('stg_category_translation') }}
),

joined as (

    select
        p.product_id,
        coalesce(t.product_category_name_english,
                 p.product_category_name,
                 'unknown')                                 as category,
        coalesce(p.product_category_name, 'unknown')        as category_pt,
        p.product_photos_qty                                as photos_qty,
        p.product_name_lenght                               as name_length,
        p.product_description_lenght                        as description_length,
        p.product_weight_g                                  as weight_g,
        p.product_length_cm                                 as length_cm,
        p.product_height_cm                                 as height_cm,
        p.product_width_cm                                  as width_cm,
        p.product_length_cm * p.product_height_cm * p.product_width_cm
                                                            as volume_cm3,
        case
            when p.product_length_cm * p.product_height_cm * p.product_width_cm is null
                then 'Unknown'
            when p.product_length_cm * p.product_height_cm * p.product_width_cm <  5000
                then 'Small'
            when p.product_length_cm * p.product_height_cm * p.product_width_cm < 20000
                then 'Medium'
            else 'Large'
        end                                                 as size_band
    from products as p
    left join translation as t
        on t.product_category_name = p.product_category_name
),

deduplicated as (

    select
        *,
        row_number() over (partition by product_id order by product_id) as row_num
    from joined
)

select
    cast(row_number() over (order by product_id) as integer) as product_key,
    * exclude (row_num)
from deduplicated
where row_num = 1

union all

select -1, 'unknown', 'unknown', 'unknown', null, null, null, null, null, null,
       null, null, 'Unknown'

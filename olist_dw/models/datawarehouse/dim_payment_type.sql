-- Payment-method dimension for fact_order_payments.
--
-- The old model left payment_type as a raw string sitting on the fact table.
-- Lifting it into a dimension gives payment behaviour a home of its own: a
-- readable label for the dashboard, whether the method supports instalments,
-- and whether it is a real method or the source's "not_defined" placeholder
-- (3 rows) that should be excluded from analysis.

with types as (

    select distinct payment_type from {{ ref('stg_order_payments') }}
)

select
    cast(row_number() over (order by payment_type) as integer) as payment_type_key,
    payment_type,
    case payment_type
        when 'credit_card' then 'Credit card'
        when 'boleto'      then 'Boleto (bank slip)'
        when 'voucher'     then 'Voucher'
        when 'debit_card'  then 'Debit card'
        when 'not_defined' then 'Not defined'
        else replace(payment_type, '_', ' ')
    end                                                     as payment_label,
    payment_type = 'credit_card'                            as supports_instalments,
    payment_type <> 'not_defined'                           as is_valid_method
from types

union all

select -1, 'unknown', 'Unknown', false, false

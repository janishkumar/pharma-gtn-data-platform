-- One row per state x NDC x quarter x utilization type (FFSU fee-for-service, MCOU managed care).
-- Measures arrive zero-padded ("00000000226.000") and empty on suppressed rows.
select
    upper(trim(utilization_type))                               as utilization_type,
    upper(trim(state))                                          as state,
    lpad(trim(ndc), 11, '0')                                    as ndc,
    cast(year as integer)                                       as year,
    cast(quarter as integer)                                    as quarter,
    make_date(cast(year as integer), cast(quarter as integer) * 3 - 2, 1) as quarter_start,
    lower(trim(suppression_used)) = 'true'                      as is_suppressed,
    trim(product_name)                                          as product_name,
    try_cast(units_reimbursed as double)                        as units,
    try_cast(number_of_prescriptions as double)                 as prescriptions,
    try_cast(total_amount_reimbursed as double)                 as total_reimbursed,
    try_cast(medicaid_amount_reimbursed as double)              as medicaid_reimbursed
from {{ source('raw', 'sdud') }}
-- 'XX' rows are CMS's national totals; keeping them would double count.
where upper(trim(state)) <> 'XX'

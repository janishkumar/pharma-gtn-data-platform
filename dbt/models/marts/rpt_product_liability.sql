-- Product-level liability by year for the dashboard's product table.
select
    year,
    product_name,
    coalesce(labeler_name, '(not in MDRP file)')          as labeler_name,
    rebate_category,
    count(distinct ndc)                                   as ndcs,
    sum(units) filter (where not is_suppressed)           as units,
    sum(medicaid_reimbursed)                              as medicaid_reimbursed,
    sum(liability_point)                                  as liability_point,
    sum(liability_point) / nullif(sum(medicaid_reimbursed), 0) as rebate_to_reimbursed
from {{ ref('fct_rebate_liability') }}
group by all

-- Small aggregate the dashboard reads: year x quarter x state x labeler x category.
select
    year,
    quarter,
    quarter_start,
    state,
    coalesce(labeler_name, '(not in MDRP file)')   as labeler_name,
    coalesce(rebate_category, '?')                 as rebate_category,
    amp_source,
    sum(units) filter (where not is_suppressed)    as units,
    sum(medicaid_reimbursed)                       as medicaid_reimbursed,
    sum(liability_point)                           as liability_point,
    sum(liability_high)                            as liability_high,
    count(*)                                       as lines
from {{ ref('fct_rebate_liability') }}
group by all

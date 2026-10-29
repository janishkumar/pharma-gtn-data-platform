-- FUL weighted average of AMPs per NDC per quarter. Median of the months, not the mean: FUL has
-- isolated bad months (February 2023 carries $1.97M per gram for two NDCs).
select
    ndc,
    make_date(year, (month - 1) // 3 * 3 + 1, 1)  as quarter_start,
    median(weighted_avg_amp)                      as ful_amp,
    mode(mdr_unit_type)                           as mdr_unit_type
from {{ ref('stg_ful') }}
group by all

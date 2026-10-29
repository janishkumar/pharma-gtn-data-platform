-- Mean FUL weighted average of AMPs per NDC per quarter.
select
    ndc,
    make_date(year, (month - 1) // 3 * 3 + 1, 1)  as quarter_start,
    avg(weighted_avg_amp)                         as ful_amp,
    mode(mdr_unit_type)                           as mdr_unit_type
from {{ ref('stg_ful') }}
group by all

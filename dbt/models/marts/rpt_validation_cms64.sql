-- Bottom-up estimate vs what states reported to CMS as national (statutory) drug rebate
-- offsets on the CMS-64. CMS-64 is cash collected in the federal fiscal year, including
-- prior-period adjustments; the estimate is accrued on calendar-year utilization.
with reported as (
    select
        year,
        -sum(total_computable) as cms64_national_rebate_offset
    from {{ ref('stg_cms64') }}
    where service_category = 'Drug Rebate Offset - National'
    group by all
),

estimated as (
    select year, quarters, liability_point, liability_high
    from {{ ref('rpt_sensitivity') }}
    where is_base
)

select
    r.year,
    r.cms64_national_rebate_offset,
    e.quarters,
    e.liability_point                                   as estimate_point,
    e.liability_high                                    as estimate_high,
    e.liability_point / r.cms64_national_rebate_offset  as point_to_reported
from reported as r
join estimated as e using (year)

-- Yearly liability under every scenario in seeds/rebate_scenarios.csv.
with units as (
    select
        ndc,
        quarter_start,
        sum(case when not is_suppressed then units end)                       as units_point,
        sum(case when is_suppressed
                 then {{ var('suppressed_max_rx') }} * median_units_per_rx end) as units_suppressed_high
    from {{ ref('int_utilization') }}
    group by all
),

scenarios as (
    select * from {{ ref('rebate_scenarios') }}
)

select
    year(u.quarter_start)                                         as year,
    count(distinct quarter(u.quarter_start))                      as quarters,
    s.scenario,
    s.is_base,
    s.amp_nadac_factor,
    s.bp_discount,
    s.pre_nadac_excess_growth,
    sum(u.units_point * r.ura)                                    as liability_point,
    sum(u.units_point * r.ura) + coalesce(sum(u.units_suppressed_high * r.ura), 0) as liability_high,
    sum(case when r.amp is not null then u.units_point end) / sum(u.units_point) as priced_unit_share
from units as u
join {{ ref('int_ura') }} as r using (ndc, quarter_start)
join scenarios as s using (scenario)
group by all

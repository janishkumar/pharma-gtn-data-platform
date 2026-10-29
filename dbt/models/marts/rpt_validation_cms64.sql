-- Checks against what states reported to CMS on the CMS-64 (data.medicaid.gov carries 2016).
-- 1. Gross: SDUD fee-for-service spend vs the CMS-64 "Prescribed Drugs" line, which covers
--    fee-for-service only (managed-care drug spend sits inside capitation payments).
-- 2. Rebates: the base estimate vs the "Drug Rebate Offset - National" line. The file doesn't say
--    whether that offset includes rebates on managed-care utilization, so both the fee-for-service
--    and the total estimate are shown. CMS-64 is cash collected in the federal fiscal year,
--    including prior-period adjustments; the estimate is accrued on calendar-year utilization.
with reported as (
    select
        year,
        sum(total_computable) filter (where service_category = 'Prescribed Drugs')
            as cms64_prescribed_drugs,
        -sum(total_computable) filter (where service_category = 'Drug Rebate Offset - National')
            as cms64_national_rebate_offset
    from {{ ref('stg_cms64') }}
    group by all
),

estimated as (
    select
        year,
        count(distinct quarter)                                             as quarters,
        sum(medicaid_reimbursed) filter (where utilization_type = 'FFSU')   as sdud_ffs_reimbursed,
        sum(liability_point) filter (where utilization_type = 'FFSU')       as estimate_ffs_point,
        sum(liability_point)                                                as estimate_point,
        sum(liability_high)                                                 as estimate_high
    from {{ ref('fct_rebate_liability') }}
    group by all
)

select
    r.year,
    e.quarters,
    r.cms64_prescribed_drugs,
    e.sdud_ffs_reimbursed,
    e.sdud_ffs_reimbursed / r.cms64_prescribed_drugs           as ffs_gross_ratio,
    r.cms64_national_rebate_offset,
    e.estimate_ffs_point,
    e.estimate_point,
    e.estimate_high,
    e.estimate_ffs_point / r.cms64_national_rebate_offset      as ffs_estimate_to_offset,
    e.estimate_point / r.cms64_national_rebate_offset          as total_estimate_to_offset
from reported as r
join estimated as e using (year)

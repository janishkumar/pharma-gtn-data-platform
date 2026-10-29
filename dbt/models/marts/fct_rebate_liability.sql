-- Base-scenario Medicaid rebate liability at the grain of the state invoice line:
-- state x NDC x quarter x utilization type.
with util as (
    select * from {{ ref('int_utilization') }}
),

ura as (
    select * from {{ ref('int_ura') }} where is_base
),

products as (
    select * from {{ ref('int_product_quarter') }}
)

select
    util.state,
    util.ndc,
    util.year,
    util.quarter,
    util.quarter_start,
    util.utilization_type,
    p.labeler_name,
    coalesce(p.product_name, util.product_name)          as product_name,
    ura.rebate_category,
    ura.category_source,
    ura.amp_source,
    util.is_suppressed,
    util.units,
    util.prescriptions,
    util.medicaid_reimbursed,
    ura.amp                                               as amp_per_unit,
    ura.basic_per_unit,
    ura.additional_per_unit,
    ura.ura                                               as ura_per_unit,
    ura.is_capped,
    -- Point excludes suppressed rows; high adds them at the maximum suppressed volume.
    case when util.is_suppressed then 0 else util.units * ura.ura end as liability_point,
    case
        when util.is_suppressed
        then {{ var('suppressed_max_rx') }} * util.median_units_per_rx * ura.ura
        else util.units * ura.ura
    end                                                   as liability_high
from util
left join ura using (ndc, quarter_start)
left join products as p using (ndc, quarter_start)

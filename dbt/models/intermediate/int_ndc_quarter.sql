-- Everything the rebate formula needs for one NDC in one quarter (design section 5).
with products as (
    select * from {{ ref('int_product_quarter') }}
),

nadac as (
    select * from {{ ref('int_nadac_quarterly') }}
),

cpi as (
    select * from {{ ref('int_cpi_quarterly') }}
),

-- National Medicaid paid per unit: the price of last resort for NDCs NADAC doesn't survey
-- (mostly clinic-administered drugs). Includes dispensing fees, so it overstates AMP for
-- cheap drugs; it only applies where neither FUL nor NADAC has a price.
reimbursed as (
    select
        ndc,
        quarter_start,
        sum(total_reimbursed) / sum(units) as reimbursed_per_unit
    from {{ ref('stg_sdud') }}
    where not is_suppressed and units > 0 and total_reimbursed > 0
    group by all
),

base as (
    select
        p.*,
        n.nadac_per_unit                          as nadac_q,
        n.pricing_unit                            as nadac_pricing_unit,
        n.classification                          as nadac_classification,
        -- Drop a FUL AMP more than 10x away from NADAC either way: a unit or data error, not a price.
        case
            when n.nadac_per_unit is null
                or f.ful_amp / n.nadac_per_unit between 0.1 and 10 then f.ful_amp
        end                                       as ful_amp,
        f.ful_amp is not null and n.nadac_per_unit is not null
            and f.ful_amp / n.nadac_per_unit not between 0.1 and 10 as ful_rejected,
        r.reimbursed_per_unit,
        -- MDRP unit types TAB, CAP, SUP, TDP and AHF are all priced per each in NADAC.
        case p.unit_type when 'ML' then 'ML' when 'GM' then 'GM' else 'EA' end as expected_unit
    from products as p
    left join nadac as n using (ndc, quarter_start)
    left join {{ ref('int_ful_quarterly') }} as f using (ndc, quarter_start)
    left join reimbursed as r using (ndc, quarter_start)
),

categorised as (
    select
        *,
        -- No MDRP record: fall back to NADAC's brand/generic classification.
        coalesce(
            drug_category,
            case nadac_classification when 'G' then 'N' when 'B' then 'S' end
        )                                                         as rebate_category,
        case
            when drug_category is not null then 'MDRP'
            when nadac_classification in ('G', 'B') then 'NADAC'
            else 'NONE'
        end                                                       as category_source,
        nadac_q is not null
            and (unit_type is null or nadac_pricing_unit = expected_unit) as nadac_unit_ok
    from base
),

with_baseline as (
    select
        *,
        -- Baseline is the first full quarter after launch, floored at 1990 Q3 for
        -- innovators and 2014 Q3 for non-innovators (the statutory baselines).
        greatest(
            date_trunc('quarter', coalesce(market_date, date '1990-07-01') - interval 1 day)::date
                + interval 3 month,
            case when rebate_category = 'N' then date '2014-07-01' else date '1990-07-01' end
        )::date as baseline_quarter
    from categorised
)

select
    b.*,
    anchor.quarter_start   as anchor_quarter,
    anchor.nadac_per_unit  as nadac_anchor,
    cpi_q.cpi_u            as cpi_q,
    cpi_anchor.cpi_u       as cpi_anchor
from with_baseline as b
-- Anchor: the first NADAC observation on or after the baseline quarter.
asof left join nadac as anchor
    on b.ndc = anchor.ndc and anchor.quarter_start >= b.baseline_quarter
left join cpi as cpi_q on cpi_q.quarter_start = b.quarter_start
left join cpi as cpi_anchor on cpi_anchor.quarter_start = anchor.quarter_start

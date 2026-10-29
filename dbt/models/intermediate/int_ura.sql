-- Estimated unit rebate amount (URA) per NDC per quarter for every scenario.
with inputs as (
    select * from {{ ref('int_ndc_quarter') }}
),

scenarios as (
    select * from {{ ref('rebate_scenarios') }}
),

amp as (
    select
        i.*,
        s.scenario,
        s.is_base,
        s.bp_discount,
        s.pre_nadac_excess_growth,
        case
            when i.rebate_category = 'N' and i.ful_amp is not null then i.ful_amp
            when i.nadac_unit_ok then i.nadac_q * s.amp_nadac_factor
            when i.nadac_q is null then i.reimbursed_per_unit * s.amp_nadac_factor
        end as amp,
        case
            when i.rebate_category = 'N' and i.ful_amp is not null then 'FUL'
            when i.nadac_unit_ok then 'NADAC'
            when i.nadac_q is not null then 'UNIT_MISMATCH'
            when i.reimbursed_per_unit is not null then 'REIMBURSED'
            else 'NONE'
        end as amp_source
    from inputs as i
    cross join scenarios as s
),

rates as (
    select
        *,
        case
            when rebate_category = 'N' then 0.13
            else greatest(
                case when is_clotting_factor or is_pediatric then 0.171 else 0.231 end,
                bp_discount
            )
        end as basic_pct,
        -- Inflation penalty as a share of AMP. Prices before the first NADAC observation are
        -- assumed to grow at CPI plus the scenario's excess growth, so the base case is a
        -- lower bound for drugs launched before NADAC began (late 2013).
        case
            when rebate_category in ('S', 'I')
                or (rebate_category = 'N' and quarter_start >= date '2017-01-01')
            then case
                when nadac_q > 0 and nadac_anchor > 0 and cpi_anchor > 0
                    and quarter_start >= anchor_quarter
                then greatest(
                    0,
                    1 - (nadac_anchor / nadac_q) * (cpi_q / cpi_anchor)
                        / pow(1 + pre_nadac_excess_growth,
                              date_diff('month', baseline_quarter, anchor_quarter) / 12.0)
                )
                else 0
            end
            else 0
        end as penalty_pct
    from amp
)

select
    ndc,
    quarter_start,
    scenario,
    is_base,
    rebate_category,
    category_source,
    amp_source,
    amp,
    basic_pct,
    penalty_pct,
    amp * basic_pct                                   as basic_per_unit,
    amp * penalty_pct                                 as additional_per_unit,
    quarter_start < date '2024-01-01'
        and basic_pct + penalty_pct > 1               as is_capped,
    case
        when cod_status in ('05', '06') then 0       -- DESI 5/6: not rebate-eligible
        when quarter_start < date '2024-01-01' then amp * least(basic_pct + penalty_pct, 1)
        else amp * (basic_pct + penalty_pct)          -- cap removed from 2024 Q1
    end                                               as ura
from rates

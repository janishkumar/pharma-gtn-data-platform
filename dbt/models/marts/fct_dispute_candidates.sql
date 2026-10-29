-- Utilization lines a manufacturer's Medicaid team would question before paying the invoice
-- (design section 6). One row per line per reason; dollars at stake = base liability.
with lines as (
    select
        l.*,
        u.median_units_per_rx,
        p.market_date,
        p.termination_date,
        p.cod_status,
        case when n.nadac_unit_ok then n.nadac_q end as nadac_q
    from {{ ref('fct_rebate_liability') }} as l
    join {{ ref('int_utilization') }} as u
        using (state, ndc, quarter_start, utilization_type)
    left join {{ ref('int_product_quarter') }} as p using (ndc, quarter_start)
    left join {{ ref('int_ndc_quarter') }} as n using (ndc, quarter_start)
    where not l.is_suppressed and l.units > 0
),

flagged as (
    select *, 'UOM_OUTLIER' as reason_code,
        format('{:.1f} units/Rx vs national median {:.1f}', units / prescriptions,
               median_units_per_rx) as reason_detail
    from lines
    where prescriptions > 0
      and units / prescriptions > {{ var('uom_multiple') }} * median_units_per_rx

    union all
    select *, 'TERMINATED_NDC', format('terminated {}', termination_date)
    from lines
    where termination_date is not null and quarter_start > termination_date

    union all
    select *, 'PRE_MARKET', format('market date {}', market_date)
    from lines
    where market_date is not null and quarter_start + interval 3 month <= market_date

    union all
    select *, 'NOT_COD', format('COD status {} (DESI 5/6)', cod_status)
    from lines
    where cod_status in ('05', '06')

    union all
    select *, 'PRICE_OUTLIER',
        format('paid {:.2f}/unit vs NADAC {:.2f}', medicaid_reimbursed / units, nadac_q)
    from lines
    where nadac_q > 0 and medicaid_reimbursed > 0
      and (medicaid_reimbursed / units / nadac_q < {{ var('price_ratio_low') }}
        or medicaid_reimbursed / units / nadac_q > {{ var('price_ratio_high') }})
)

select
    state,
    ndc,
    year,
    quarter,
    quarter_start,
    utilization_type,
    labeler_name,
    product_name,
    reason_code,
    reason_detail,
    units,
    prescriptions,
    medicaid_reimbursed,
    ura_per_unit,
    liability_point as dollars_at_stake
from flagged

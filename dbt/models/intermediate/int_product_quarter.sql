-- Product attributes for every NDC-quarter that appears in utilization: the latest MDRP
-- snapshot at or before the quarter, else the earliest one after it.
with ndc_quarters as (
    select distinct ndc, quarter_start from {{ ref('stg_sdud') }}
),

products as (
    select * from {{ ref('stg_drug_products') }}
),

earliest as (
    select distinct on (ndc) * from products order by ndc, quarter_start
),

prior as (
    select
        nq.ndc,
        nq.quarter_start,
        p.quarter_start as snapshot_quarter,
        p.* exclude (ndc, quarter_start, year, quarter)
    from ndc_quarters as nq
    asof left join products as p
        on nq.ndc = p.ndc and nq.quarter_start >= p.quarter_start
)

select
    prior.ndc,
    prior.quarter_start,
    coalesce(prior.snapshot_quarter, e.quarter_start)       as snapshot_quarter,
    coalesce(prior.labeler_name, e.labeler_name)            as labeler_name,
    coalesce(prior.product_name, e.product_name)            as product_name,
    coalesce(prior.drug_category, e.drug_category)          as drug_category,
    coalesce(prior.cod_status, e.cod_status)                as cod_status,
    coalesce(prior.unit_type, e.unit_type)                  as unit_type,
    coalesce(prior.units_per_pkg, e.units_per_pkg)          as units_per_pkg,
    coalesce(prior.market_date, e.market_date)              as market_date,
    coalesce(prior.termination_date, e.termination_date)    as termination_date,
    coalesce(prior.is_clotting_factor, e.is_clotting_factor, false) as is_clotting_factor,
    coalesce(prior.is_pediatric, e.is_pediatric, false)     as is_pediatric,
    coalesce(prior.is_line_extension, e.is_line_extension, false) as is_line_extension
from prior
left join earliest as e
    on prior.snapshot_quarter is null and prior.ndc = e.ndc

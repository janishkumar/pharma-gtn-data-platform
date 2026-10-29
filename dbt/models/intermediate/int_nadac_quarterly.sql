-- Mean NADAC per unit across the weekly snapshots taken in each quarter.
select
    ndc,
    date_trunc('quarter', as_of_date)::date  as quarter_start,
    avg(nadac_per_unit)                      as nadac_per_unit,
    mode(pricing_unit)                       as pricing_unit,
    mode(classification)                     as classification
from {{ ref('stg_nadac') }}
group by all

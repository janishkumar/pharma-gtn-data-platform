-- Utilization rows plus the national median units per prescription for the NDC-quarter,
-- used both to impute suppressed rows and to spot unit-of-measure errors.
with sdud as (
    select * from {{ ref('stg_sdud') }}
),

medians as (
    select
        ndc,
        quarter_start,
        median(units / prescriptions) as median_units_per_rx
    from sdud
    where not is_suppressed and prescriptions > 0 and units > 0
    group by all
)

select
    sdud.*,
    medians.median_units_per_rx
from sdud
left join medians using (ndc, quarter_start)

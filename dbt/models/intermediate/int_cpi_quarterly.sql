-- CPI-U used for a rebate quarter is the month before the quarter starts. BLS skipped
-- October 2025, so fall back to the latest published month on or before that.
with quarters as (
    select
        q::date                         as quarter_start,
        (q - interval 1 month)::date    as cpi_month
    from unnest(generate_series(
        date '1990-01-01', date_trunc('quarter', current_date)::date, interval 3 month
    )) as t(q)
)

select
    quarters.quarter_start,
    cpi.month_start as cpi_month,
    cpi.cpi_u
from quarters
asof left join {{ ref('stg_cpi_u') }} as cpi
    on quarters.cpi_month >= cpi.month_start

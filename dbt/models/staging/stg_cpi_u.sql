select
    year,
    month,
    make_date(year, month, 1) as month_start,
    cpi_u
from {{ source('raw', 'cpi_u') }}

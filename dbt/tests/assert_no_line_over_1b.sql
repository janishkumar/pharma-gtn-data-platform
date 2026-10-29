-- No single state invoice line can plausibly carry $1B of rebate. A row this large means a bad
-- price or unit upstream (this test caught a $1.97M-per-gram FUL row).
select state, ndc, quarter_start, utilization_type, liability_high
from {{ ref('fct_rebate_liability') }}
where liability_high > 1e9

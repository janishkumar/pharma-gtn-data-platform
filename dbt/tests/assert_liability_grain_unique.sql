-- One liability row per state invoice line.
select state, ndc, quarter_start, utilization_type, count(*) as n
from {{ ref('fct_rebate_liability') }}
group by all
having count(*) > 1

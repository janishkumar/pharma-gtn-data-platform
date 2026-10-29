-- Weekly NADAC snapshots. Yearly files overlap at the boundaries, so dedupe on the snapshot key.
select distinct on (ndc, as_of_date)
    lpad(trim(ndc), 11, '0')                                   as ndc,
    trim(ndc_description)                                      as ndc_description,
    try_cast(nadac_per_unit as double)                         as nadac_per_unit,
    try_strptime(trim(effective_date), '%m/%d/%Y')::date       as effective_date,
    try_strptime(trim(as_of_date), '%m/%d/%Y')::date           as as_of_date,
    upper(trim(pricing_unit))                                  as pricing_unit,
    upper(trim(classification_for_rate_setting))               as classification
from {{ source('raw', 'nadac') }}
where try_cast(nadac_per_unit as double) > 0
order by ndc, as_of_date, effective_date desc

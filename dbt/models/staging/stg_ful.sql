-- FUL publishes the weighted average of AMPs per product group; the only public AMP figure.
select
    replace(trim(ndc), '-', '')                                as ndc,
    cast(year as integer)                                      as year,
    cast(month as integer)                                     as month,
    upper(trim(mdr_unit_type))                                 as mdr_unit_type,
    try_cast(weighted_average_of_amps as double)               as weighted_avg_amp
from {{ source('raw', 'ful') }}
where try_cast(weighted_average_of_amps as double) > 0

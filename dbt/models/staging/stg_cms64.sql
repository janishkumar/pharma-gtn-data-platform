select
    cast(year as integer)                                       as year,
    trim(program)                                               as program,
    trim(service_category)                                      as service_category,
    try_cast(total_computable as double)                        as total_computable,
    try_cast(federal_share as double)                           as federal_share
from {{ source('raw', 'cms64') }}

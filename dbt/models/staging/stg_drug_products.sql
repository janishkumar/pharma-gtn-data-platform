-- Quarterly snapshots of every NDC in the Medicaid Drug Rebate Program.
select
    lpad(trim(ndc), 11, '0')                                    as ndc,
    cast(year as integer)                                       as year,
    cast(quarter as integer)                                    as quarter,
    make_date(cast(year as integer), cast(quarter as integer) * 3 - 2, 1) as quarter_start,
    trim(labeler_name)                                          as labeler_name,
    trim(fda_product_name)                                      as product_name,
    upper(trim(drug_category))                                  as drug_category,
    nullif(lpad(trim(cod_status), 2, '0'), '00')                as cod_status,
    upper(trim(unit_type))                                      as unit_type,
    try_cast(units_per_pkg_size as double)                      as units_per_pkg,
    try_strptime(trim(market_date), '%m/%d/%Y')::date           as market_date,
    try_strptime(trim(termination_date), '%m/%d/%Y')::date      as termination_date,
    upper(trim(clotting_factor_indicator)) = 'Y'                as is_clotting_factor,
    upper(trim(pediatric_indicator)) = 'Y'                      as is_pediatric,
    upper(trim(line_extension_drug_indicator)) = 'Y'            as is_line_extension
from {{ source('raw', 'drug_products') }}

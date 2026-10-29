-- NDCs must stay 11-digit text everywhere; a cast to integer would drop leading zeros.
select 'sdud' as source, ndc from {{ ref('stg_sdud') }} where not regexp_full_match(ndc, '\d{11}')
union all
select 'nadac', ndc from {{ ref('stg_nadac') }} where not regexp_full_match(ndc, '\d{11}')
union all
select 'drug_products', ndc from {{ ref('stg_drug_products') }} where not regexp_full_match(ndc, '\d{11}')

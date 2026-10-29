-- Price and product NDCs must stay 11-digit text; a cast to integer would drop leading zeros.
-- (Malformed NDCs on utilization lines are real invoice errors: they surface as INVALID_NDC
-- dispute candidates instead of failing the build.)
select 'nadac' as source, ndc from {{ ref('stg_nadac') }} where not regexp_full_match(ndc, '\d{11}')
union all
select 'drug_products', ndc from {{ ref('stg_drug_products') }} where not regexp_full_match(ndc, '\d{11}')
union all
select 'sdud', ndc from {{ ref('stg_sdud') }}
where regexp_full_match(ndc, '\d+') and length(ndc) <> 11

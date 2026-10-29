"""Public CMS datasets the platform loads, and how to find them in the data.medicaid.gov catalog."""

from __future__ import annotations

import re
from dataclasses import dataclass


@dataclass(frozen=True)
class SourceSpec:
    name: str
    title_regex: str  # matched against the catalog title; group 1 is the year for yearly sources
    yearly: bool
    columns: tuple[str, ...]  # normalised column names the file must contain


@dataclass(frozen=True)
class Resource:
    source: str
    year: int | None
    url: str
    modified: str


SDUD_COLUMNS = (
    "utilization_type", "state", "ndc", "labeler_code", "product_code", "package_size",
    "year", "quarter", "suppression_used", "product_name", "units_reimbursed",
    "number_of_prescriptions", "total_amount_reimbursed", "medicaid_amount_reimbursed",
    "non_medicaid_amount_reimbursed",
)

NADAC_COLUMNS = (
    "ndc_description", "ndc", "nadac_per_unit", "effective_date", "pricing_unit",
    "pharmacy_type_indicator", "otc", "explanation_code", "classification_for_rate_setting",
    "corresponding_generic_drug_nadac_per_unit", "corresponding_generic_drug_effective_date",
    "as_of_date",
)

FUL_COLUMNS = (
    "product_group", "ingredient", "strength", "dosage", "route", "mdr_unit_type",
    "weighted_average_of_amps", "aca_ful", "package_size", "ndc", "a_rated",
    "multiplier_greater_than_175_percent_of_weighted_avg_of_amps", "year", "month",
)

DRUG_PRODUCTS_COLUMNS = (
    "year", "quarter", "labeler_name", "ndc", "labeler_code", "product_code",
    "package_size_code", "drug_category", "drug_type_indicator", "termination_date",
    "unit_type", "units_per_pkg_size", "fda_approval_date", "market_date",
    "fda_therapeutic_equivalence_code", "fda_product_name", "clotting_factor_indicator",
    "pediatric_indicator", "package_size_intro_date", "purchased_product_date", "cod_status",
    "fda_application_number", "reactivation_date", "line_extension_drug_indicator",
)

CMS64_COLUMNS = (
    "year", "program", "notes", "service_category", "total_computable", "federal_share",
    "federal_share_medicaid", "federal_share_arra", "federal_share_bipp", "state_share",
)

SOURCES: dict[str, SourceSpec] = {
    s.name: s
    for s in (
        SourceSpec("sdud", r"^State Drug Utilization Data (\d{4})$", True, SDUD_COLUMNS),
        SourceSpec(
            "nadac", r"^NADAC \(National Average Drug Acquisition Cost\) (\d{4})$", True,
            NADAC_COLUMNS,
        ),
        SourceSpec("ful", r"^ACA Federal Upper Limits$", False, FUL_COLUMNS),
        SourceSpec(
            "drug_products", r"^Drug Products in the Medicaid Drug Rebate Program$", False,
            DRUG_PRODUCTS_COLUMNS,
        ),
        SourceSpec(
            "cms64", r"^Medicaid Financial Management Data . National Totals$", False,
            CMS64_COLUMNS,
        ),
    )
}

# SDUD 2016 is the validation year (the only CMS-64 year on data.medicaid.gov); 2021+ is the
# current view. NADAC goes back to 2013 because inflation-penalty baselines need early prices.
DEFAULT_YEARS: dict[str, set[int] | None] = {
    "sdud": {2016} | set(range(2021, 2100)),
    "nadac": set(range(2013, 2100)),
}


def normalise_column(name: str) -> str:
    """'NADAC Per Unit' and 'NADAC_Per_Unit' both become 'nadac_per_unit'."""
    return re.sub(r"[^a-z0-9]+", "_", name.strip().lower()).strip("_")


def resolve(catalog: list[dict], spec: SourceSpec, years: set[int] | None = None) -> list[Resource]:
    """Find the download URLs for one source in the DKAN catalog, newest year first."""
    pattern = re.compile(spec.title_regex)
    found: list[Resource] = []
    for item in catalog:
        match = pattern.match(item.get("title", "").strip())
        if not match:
            continue
        year = int(match.group(1)) if spec.yearly else None
        if years is not None and year is not None and year not in years:
            continue
        urls = [d.get("downloadURL") for d in item.get("distribution", []) if d.get("downloadURL")]
        if not urls:
            continue
        found.append(Resource(spec.name, year, urls[0], item.get("modified", "")))
    if not spec.yearly and len(found) > 1:
        raise ValueError(f"{spec.name}: expected one catalog entry, found {len(found)}")
    return sorted(found, key=lambda r: r.year or 0, reverse=True)

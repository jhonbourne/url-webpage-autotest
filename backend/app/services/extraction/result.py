"""Shared helper for packaging extracted records with quality metrics."""

from typing import Any

from app.services.extraction.models import ExtractionPlan


def build_result(
    records: list[dict[str, Any]], plan: ExtractionPlan, strategy: str
) -> dict[str, Any]:
    field_names = [f.name for f in plan.fields]

    # Per-field coverage: fraction of records with a non-empty value for that field.
    coverage: dict[str, float] = {}
    if records:
        for name in field_names:
            filled = sum(1 for r in records if r.get(name) not in (None, "", []))
            coverage[name] = round(filled / len(records), 3)
    else:
        coverage = {name: 0.0 for name in field_names}

    return {
        "records": records,
        "fields": field_names,
        "strategy": strategy,
        "row_count": len(records),
        "field_coverage": coverage,
    }

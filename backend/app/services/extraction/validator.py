"""Rule-based quality check on an extraction result.

Drives the reflection loop: when a result fails these checks the agent retries with
the other strategy, carrying the issues here as feedback.
"""

from typing import Any

from pydantic import BaseModel

# Anti-hallucination sampling: only the 'llm' strategy can invent values (the
# selector executor pulls straight from the DOM). We spot-check a sample of its
# string values against the source page; if most are absent, the result is suspect.
_MIN_VALUE_LEN = 3  # skip trivially-short values that match by chance
_SAMPLE_SIZE = 25
_MIN_SAMPLE = 4  # need enough evidence before flagging
_UNSUPPORTED_RATIO = 0.5  # majority missing -> flag


def _sampled_values(records: list[dict[str, Any]]) -> list[str]:
    values: list[str] = []
    for record in records:
        for value in record.values():
            candidates = value if isinstance(value, list) else [value]
            for item in candidates:
                if isinstance(item, str) and len(item.strip()) >= _MIN_VALUE_LEN:
                    values.append(item.strip().lower())
                    if len(values) >= _SAMPLE_SIZE:
                        return values
    return values


def _unsupported_count(records: list[dict[str, Any]], source_lower: str) -> tuple[int, int]:
    sample = _sampled_values(records)
    missing = sum(1 for v in sample if v not in source_lower)
    return missing, len(sample)


class ValidationReport(BaseModel):
    ok: bool
    issues: list[str]
    # Advisory notes that do NOT fail the result or trigger a retry (e.g. the page
    # was too large for the model budget, so extraction may be incomplete).
    warnings: list[str] = []
    metrics: dict[str, Any]


class ResultValidator:
    def __init__(self, min_field_coverage: float = 0.5):
        self._min_coverage = min_field_coverage

    def validate(
        self,
        result: dict[str, Any],
        *,
        dom_truncated: bool = False,
        source_text: str | None = None,
    ) -> ValidationReport:
        issues: list[str] = []
        row_count: int = result.get("row_count", 0)
        coverage: dict[str, float] = result.get("field_coverage", {})

        if row_count == 0:
            issues.append("no records were extracted")

        if row_count > 0 and coverage:
            empty_fields = [name for name, cov in coverage.items() if cov == 0.0]
            if empty_fields:
                issues.append(f"fields never populated: {', '.join(sorted(empty_fields))}")

            avg_coverage = sum(coverage.values()) / len(coverage)
            if avg_coverage < self._min_coverage:
                issues.append(
                    f"average field coverage {avg_coverage:.2f} below threshold "
                    f"{self._min_coverage:.2f}"
                )

        # Anti-hallucination: verify LLM-extracted values actually appear in the page.
        unsupported_ratio = 0.0
        if source_text is not None and result.get("strategy") == "llm" and row_count > 0:
            missing, checked = _unsupported_count(result.get("records", []), source_text.lower())
            if checked >= _MIN_SAMPLE:
                unsupported_ratio = missing / checked
                if unsupported_ratio > _UNSUPPORTED_RATIO:
                    issues.append(
                        f"{missing} of {checked} sampled values were not found on the page "
                        "(possible hallucination)"
                    )

        # Truncation is advisory, not a failure: retrying the other strategy won't
        # help when the page simply exceeds the prompt budget.
        warnings: list[str] = []
        if dom_truncated and row_count > 0:
            warnings.append(
                "the page was large and the model saw a truncated view of it; "
                "extraction may have missed content"
            )

        avg = sum(coverage.values()) / len(coverage) if coverage else 0.0
        metrics = {
            "row_count": row_count,
            "avg_coverage": round(avg, 3),
            "dom_truncated": dom_truncated,
            "unsupported_ratio": round(unsupported_ratio, 3),
        }
        return ValidationReport(ok=not issues, issues=issues, warnings=warnings, metrics=metrics)

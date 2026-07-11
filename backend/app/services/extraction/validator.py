"""Rule-based quality check on an extraction result.

Drives the reflection loop: when a result fails these checks the agent retries with
the other strategy, carrying the issues here as feedback. (An optional LLM sampling
QA pass is a natural future extension, gated behind config to avoid token cost.)
"""

from typing import Any

from pydantic import BaseModel


class ValidationReport(BaseModel):
    ok: bool
    issues: list[str]
    metrics: dict[str, Any]


class ResultValidator:
    def __init__(self, min_field_coverage: float = 0.5):
        self._min_coverage = min_field_coverage

    def validate(self, result: dict[str, Any]) -> ValidationReport:
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

        avg = sum(coverage.values()) / len(coverage) if coverage else 0.0
        metrics = {"row_count": row_count, "avg_coverage": round(avg, 3)}
        return ValidationReport(ok=not issues, issues=issues, metrics=metrics)

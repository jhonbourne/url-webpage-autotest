from app.services.extraction.validator import ResultValidator


def _result(records, coverage, strategy="selector"):
    return {
        "records": records,
        "fields": list(coverage),
        "strategy": strategy,
        "row_count": len(records),
        "field_coverage": coverage,
    }


def test_passes_on_full_coverage():
    report = ResultValidator().validate(
        _result([{"a": "1"}, {"a": "2"}], {"a": 1.0})
    )
    assert report.ok
    assert report.issues == []


def test_fails_on_zero_records():
    report = ResultValidator().validate(_result([], {"a": 0.0}))
    assert not report.ok
    assert any("no records" in i for i in report.issues)


def test_fails_on_never_populated_field():
    report = ResultValidator().validate(
        _result([{"a": "x", "b": None}], {"a": 1.0, "b": 0.0})
    )
    assert not report.ok
    assert any("never populated" in i for i in report.issues)


def test_fails_on_low_average_coverage():
    # avg = 0.3 < default threshold 0.5
    report = ResultValidator(min_field_coverage=0.5).validate(
        _result([{"a": "x"}], {"a": 0.6, "b": 0.6, "c": 0.0})
    )
    assert not report.ok
    assert any("coverage" in i for i in report.issues)


def test_truncation_is_a_warning_not_a_failure():
    report = ResultValidator().validate(
        _result([{"a": "1"}, {"a": "2"}], {"a": 1.0}), dom_truncated=True
    )
    assert report.ok  # still passes — truncation does not fail the result
    assert report.issues == []
    assert any("truncated" in w for w in report.warnings)
    assert report.metrics["dom_truncated"] is True


def test_no_truncation_warning_when_empty():
    # A truncated page that yielded nothing fails on row_count, not on truncation.
    report = ResultValidator().validate(_result([], {"a": 0.0}), dom_truncated=True)
    assert not report.ok
    assert report.warnings == []


_SOURCE = "<html><body>Wireless Mouse costs 29.90 and Keyboard costs 59.00</body></html>"


def test_hallucination_flagged_for_llm_values_absent_from_page():
    records = [{"name": f"Nonexistent Gadget {i}"} for i in range(5)]
    report = ResultValidator().validate(
        _result(records, {"name": 1.0}, strategy="llm"), source_text=_SOURCE
    )
    assert not report.ok
    assert any("hallucination" in i for i in report.issues)


def test_no_hallucination_flag_when_values_present():
    records = [
        {"name": "Wireless Mouse", "price": "29.90"},
        {"name": "Keyboard", "price": "59.00"},
    ]
    report = ResultValidator().validate(
        _result(records, {"name": 1.0, "price": 1.0}, strategy="llm"), source_text=_SOURCE
    )
    assert report.ok


def test_selector_results_are_not_hallucination_checked():
    # Selector values come straight from the DOM; even if absent from source_text
    # (e.g. a synthetic test), they must not be flagged.
    records = [{"name": "Nonexistent Gadget"}]
    report = ResultValidator().validate(
        _result(records, {"name": 1.0}, strategy="selector"), source_text=_SOURCE
    )
    assert report.ok

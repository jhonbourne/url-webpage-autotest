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

"""The controlled executor is pure (no LLM), so we verify it end-to-end here."""

from app.services.extraction.executor import SelectorExecutor
from app.services.extraction.models import FieldSelector, SelectorPlan


def test_extracts_list_of_records(products_html: str):
    plan = SelectorPlan(
        record_selector="li.product",
        fields={
            "name": FieldSelector(selector="a.name", attr="text"),
            "url": FieldSelector(selector="a.name", attr="href"),
            "price": FieldSelector(selector="span.price", attr="text"),
            "rating": FieldSelector(selector="span.rating", attr="text"),
        },
    )

    records = SelectorExecutor().execute(products_html, plan, is_list=True)

    assert len(records) == 3
    assert records[0] == {
        "name": "Wireless Mouse",
        "url": "/p/1",
        "price": "29.90",
        "rating": "4.5",
    }
    assert records[2]["name"] == "USB-C Hub"


def test_missing_field_becomes_none(products_html: str):
    plan = SelectorPlan(
        record_selector="li.product",
        fields={"missing": FieldSelector(selector="span.nonexistent", attr="text")},
    )
    records = SelectorExecutor().execute(products_html, plan, is_list=True)
    assert all(r["missing"] is None for r in records)


def test_invalid_selector_does_not_crash(products_html: str):
    plan = SelectorPlan(
        record_selector="li.product",
        fields={"bad": FieldSelector(selector="::::", attr="text")},
    )
    records = SelectorExecutor().execute(products_html, plan, is_list=True)
    assert len(records) == 3
    assert all(r["bad"] is None for r in records)


def test_multiple_field_returns_list(products_html: str):
    # Treat the whole list as one record and collect all names into an array field.
    plan = SelectorPlan(
        record_selector="",
        fields={"names": FieldSelector(selector="a.name", attr="text", multiple=True)},
    )
    records = SelectorExecutor().execute(products_html, plan, is_list=False)
    assert records == [
        {"names": ["Wireless Mouse", "Mechanical Keyboard", "USB-C Hub"]}
    ]


def test_multiple_field_empty_when_no_match(products_html: str):
    plan = SelectorPlan(
        record_selector="li.product",
        fields={"tags": FieldSelector(selector="span.tag", attr="text", multiple=True)},
    )
    records = SelectorExecutor().execute(products_html, plan, is_list=True)
    assert all(r["tags"] == [] for r in records)


def test_single_record_mode(products_html: str):
    plan = SelectorPlan(
        record_selector="",
        fields={"heading": FieldSelector(selector="h1", attr="text")},
    )
    records = SelectorExecutor().execute(products_html, plan, is_list=False)
    assert records == [{"heading": "Our Products"}]

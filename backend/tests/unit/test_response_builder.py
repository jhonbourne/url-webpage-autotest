from app.api.v1.scrape import _build_response
from app.models.schemas import ScrapeStatus


def test_build_response_returns_partial_output_on_failure():
    state = {
        "url": "https://x.com/",
        "status": ScrapeStatus.FAILED,
        "error_code": "EXTRACTION_FAILED",
        "error_message": "boom",
        "extraction_plan": {"fields": [{"name": "title"}], "suggested_strategy": "llm"},
        "structured_dom": {"tag": "body"},
        "execution_log": [],
    }
    resp = _build_response(state, task_id="t1")

    assert resp.status == ScrapeStatus.FAILED
    assert resp.error["code"] == "EXTRACTION_FAILED"
    # Partial output: the plan understood + the recovered page structure.
    assert resp.plan["suggested_strategy"] == "llm"
    assert resp.data == {"structured_dom": {"tag": "body"}}

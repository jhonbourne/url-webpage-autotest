from app.services.llm import summarize_usage


def test_summarize_usage_sums_across_models():
    by_model = {
        "qwen3-8b": {"input_tokens": 100, "output_tokens": 20, "total_tokens": 120},
        "qwen3-coder": {"input_tokens": 300, "output_tokens": 50, "total_tokens": 350},
    }
    out = summarize_usage(by_model)
    assert out["input_tokens"] == 400
    assert out["output_tokens"] == 70
    assert out["total_tokens"] == 470
    assert out["by_model"]["qwen3-coder"]["total_tokens"] == 350


def test_summarize_usage_handles_empty():
    out = summarize_usage(None)
    assert out == {
        "input_tokens": 0,
        "output_tokens": 0,
        "total_tokens": 0,
        "by_model": {},
    }


def test_summarize_usage_infers_total_when_missing():
    out = summarize_usage({"m": {"input_tokens": 10, "output_tokens": 5}})
    assert out["total_tokens"] == 15

import pytest

from app import llm


def test_role_extra_body_disables_thinking_for_vision_and_fast(monkeypatch):
    captured = {}

    def fake_call(base_url, model, messages, max_tokens, extra_body=None):
        captured["extra_body"] = extra_body
        return '{"ok": true}', 5, 10, 2

    monkeypatch.setattr(llm, "_call_model", fake_call)

    stages = {"vision": "read", "fast": "triage", "reason": "plan"}
    expected = {
        "vision": llm.DISABLE_THINKING,
        "fast": llm.DISABLE_THINKING,
        "reason": None,
    }

    for role, stage in stages.items():
        data, trace = llm.chat_json(
            role, [{"role": "user", "content": "hi"}], stage=stage
        )
        assert data == {"ok": True}
        assert captured["extra_body"] == expected[role]
        assert trace.stage == stage


def test_vision_failure_falls_back_and_marks_degraded(monkeypatch):
    calls = []

    def fake_call(base_url, model, messages, max_tokens, extra_body=None):
        calls.append((model, extra_body))
        if model == llm.settings.model_vision:
            raise RuntimeError("primary exploded")
        return '{"document_type": "bill"}', 7, 9, 3

    monkeypatch.setattr(llm, "_call_model", fake_call)

    data, trace = llm.chat_json(
        "vision", [{"role": "user", "content": "hi"}], stage="read"
    )

    assert data == {"document_type": "bill"}
    assert trace.degraded is True
    assert trace.model == llm.settings.model_fallback
    assert "RuntimeError" in trace.note
    assert calls[0][0] == llm.settings.model_vision
    assert calls[1][0] == llm.settings.model_fallback
    assert calls[0][1] == llm.DISABLE_THINKING
    assert calls[1][1] == llm.DISABLE_THINKING


def test_invalid_json_is_retried_once(monkeypatch):
    replies = iter(["not json at all", '{"category": "bill"}'])
    calls = []

    def fake_call(base_url, model, messages, max_tokens, extra_body=None):
        calls.append(messages)
        return next(replies), 2, 6, 3

    monkeypatch.setattr(llm, "_call_model", fake_call)

    data, trace = llm.chat_json(
        "fast", [{"role": "user", "content": "hi"}], stage="triage"
    )

    assert data == {"category": "bill"}
    assert len(calls) == 2
    assert trace.prompt_tokens == 12
    assert trace.completion_tokens == 6
    assert any(
        "not valid JSON" in str(message.get("content"))
        for message in calls[1]
    )


def test_invalid_json_twice_raises_pipeline_error(monkeypatch):
    def fake_call(base_url, model, messages, max_tokens, extra_body=None):
        return "still not json", 1, 2, 3

    monkeypatch.setattr(llm, "_call_model", fake_call)

    with pytest.raises(llm.PipelineError) as excinfo:
        llm.chat_json("fast", [{"role": "user", "content": "hi"}], stage="triage")
    assert excinfo.value.stage == "triage"

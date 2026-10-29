import dataclasses

from fastapi.testclient import TestClient

import app.main as main
from app import mock_data
from app.config import settings

client = TestClient(main.app)


def _reset():
    main._rate_day = ""
    main._rate_day_count = 0
    main._rate_ip_events.clear()


def _fake_analyze(data, mime):
    return mock_data.mock_response()


def test_daily_limit_returns_429(monkeypatch):
    monkeypatch.setattr(
        main,
        "settings",
        dataclasses.replace(
            settings,
            demo_max_analyses_per_day=1,
            demo_max_analyses_per_ip_hour=0,
        ),
    )
    monkeypatch.setattr(main.pipeline, "analyze", _fake_analyze)
    _reset()
    try:
        assert client.post("/api/analyze-sample").status_code == 200
        response = client.post("/api/analyze-sample")
        assert response.status_code == 429
        assert "limit" in response.json()["detail"].lower()
    finally:
        _reset()


def test_per_ip_limit_returns_429(monkeypatch):
    monkeypatch.setattr(
        main,
        "settings",
        dataclasses.replace(
            settings,
            demo_max_analyses_per_day=0,
            demo_max_analyses_per_ip_hour=1,
        ),
    )
    monkeypatch.setattr(main.pipeline, "analyze", _fake_analyze)
    _reset()
    try:
        a = {"x-forwarded-for": "203.0.113.5"}
        b = {"x-forwarded-for": "198.51.100.7"}
        assert client.post("/api/analyze-sample", headers=a).status_code == 200
        assert client.post("/api/analyze-sample", headers=a).status_code == 429
        assert client.post("/api/analyze-sample", headers=b).status_code == 200
    finally:
        _reset()


def test_health_is_not_rate_limited(monkeypatch):
    monkeypatch.setattr(
        main,
        "settings",
        dataclasses.replace(
            settings,
            demo_max_analyses_per_day=1,
            demo_max_analyses_per_ip_hour=0,
        ),
    )
    monkeypatch.setattr(main.pipeline, "analyze", _fake_analyze)
    _reset()
    try:
        assert client.post("/api/analyze-sample").status_code == 200
        assert client.post("/api/analyze-sample").status_code == 429
        assert client.get("/api/health").status_code == 200
    finally:
        _reset()

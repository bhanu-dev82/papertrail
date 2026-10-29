import os

os.environ["MOCK_MODE"] = "true"
os.environ["NEBIUS_API_KEY"] = ""
os.environ["TAVILY_API_KEY"] = ""

from fastapi.testclient import TestClient  # noqa: E402

from app.main import app  # noqa: E402

client = TestClient(app)


def test_health_reports_mock():
    response = client.get("/api/health")
    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "ok"
    assert body["mock"] is True
    assert set(body["models"]) == {"vision", "fast", "reason"}


def test_analyze_sample_returns_mock_result():
    response = client.post("/api/analyze-sample")
    assert response.status_code == 200
    body = response.json()
    assert body["mock"] is True
    assert len(body["trace"]) == 4
    assert body["plan"]["steps"]
    assert body["id"]


def test_upload_rejects_non_image_mime():
    response = client.post(
        "/api/analyze",
        files={"file": ("notanimage.txt", b"notanimage", "text/plain")},
    )
    assert response.status_code == 415
    assert response.json()["detail"] == "Upload a JPG, PNG or WEBP image."


def test_upload_mock_png_succeeds():
    response = client.post(
        "/api/analyze",
        files={"file": ("bill.png", b"\x89PNG\r\n\x1a\nfake", "image/png")},
    )
    assert response.status_code == 200
    assert response.json()["mock"] is True


def test_sample_bill_image_is_served():
    response = client.get("/sample-bill.png")
    assert response.status_code == 200
    assert response.headers["content-type"].startswith("image/png")
    assert len(response.content) > 1000


def test_calendar_export_for_known_result():
    result_id = client.post("/api/analyze-sample").json()["id"]
    response = client.get(f"/api/results/{result_id}/calendar.ics")
    assert response.status_code == 200
    assert response.headers["content-type"].startswith("text/calendar")
    assert "attachment" in response.headers["content-disposition"]
    assert "BEGIN:VCALENDAR" in response.text
    assert response.text.count("BEGIN:VEVENT") >= 2


def test_markdown_export_for_known_result():
    result_id = client.post("/api/analyze-sample").json()["id"]
    response = client.get(f"/api/results/{result_id}/plan.md")
    assert response.status_code == 200
    assert response.headers["content-type"].startswith("text/markdown")
    assert "Action plan" in response.text


def test_calendar_unknown_id_is_404():
    response = client.get("/api/results/doesnotexist/calendar.ics")
    assert response.status_code == 404

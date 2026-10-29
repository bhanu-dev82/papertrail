from app.ics import build_ics, build_markdown
from app.mock_data import mock_response


def test_ics_is_crlf_and_has_events():
    text = build_ics(mock_response())

    assert text.startswith("BEGIN:VCALENDAR\r\n")
    assert text.endswith("\r\n")
    assert "\n" not in text.replace("\r\n", "")
    assert text.count("BEGIN:VEVENT") >= 2
    assert "END:VCALENDAR" in text


def test_ics_escapes_commas_and_contains_alarm():
    text = build_ics(mock_response())

    assert "\\," in text
    assert "BEGIN:VALARM" in text
    assert "TRIGGER:-P1D" in text
    assert "DTSTART;VALUE=DATE:" in text


def test_ics_skips_invalid_dates():
    resp = mock_response()
    resp.plan.steps[0].due_date = "not-a-date"
    text = build_ics(resp)
    assert "not-a-date" not in text
    assert text.count("BEGIN:VEVENT") >= 2


def test_markdown_contains_checklist_and_source():
    text = build_markdown(mock_response())

    assert text.startswith("# ")
    assert "- [ ]" in text
    assert "https://bescom.karnataka.gov.in/" in text
    assert "This is not legal or financial advice" in text

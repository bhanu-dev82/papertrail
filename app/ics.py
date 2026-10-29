"""Calendar (.ics) and Markdown export without external libraries."""

from __future__ import annotations

from datetime import date, datetime, timezone

from .schemas import AnalyzeResponse


def _escape(text: str) -> str:
    """Escape text per RFC 5545."""
    return (
        str(text)
        .replace("\\", "\\\\")
        .replace(";", "\\;")
        .replace(",", "\\,")
        .replace("\r\n", "\\n")
        .replace("\n", "\\n")
        .replace("\r", "\\n")
    )


def _parse_date(value: str) -> date | None:
    try:
        return date.fromisoformat(str(value).strip())
    except (ValueError, TypeError):
        return None


def _stamp() -> str:
    return datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")


def _event(uid: str, day: date, summary: str, description: str) -> list[str]:
    return [
        "BEGIN:VEVENT",
        f"UID:{uid}",
        f"DTSTAMP:{_stamp()}",
        f"DTSTART;VALUE=DATE:{day.strftime('%Y%m%d')}",
        f"SUMMARY:{_escape(summary)}",
        f"DESCRIPTION:{_escape(description)}",
        "BEGIN:VALARM",
        "TRIGGER:-P1D",
        "ACTION:DISPLAY",
        "DESCRIPTION:Reminder",
        "END:VALARM",
        "END:VEVENT",
    ]


def build_ics(resp: AnalyzeResponse) -> str:
    """Build an all-day VEVENT for every deadline in the plan and extraction."""
    lines = [
        "BEGIN:VCALENDAR",
        "VERSION:2.0",
        "PRODID:-//PaperTrail//EN",
    ]

    ordinal = 0
    seen: set[tuple[str, str]] = set()

    def add(day_value: str, summary: str, description: str) -> None:
        nonlocal ordinal
        day = _parse_date(day_value)
        if day is None:
            return
        key = (day.isoformat(), summary)
        if key in seen:
            return
        seen.add(key)
        ordinal += 1
        lines.extend(
            _event(f"{resp.id}-{ordinal}@papertrail", day, summary, description)
        )

    for step in resp.plan.steps:
        add(
            step.due_date,
            step.action,
            step.source_url or resp.extraction.issuer,
        )

    for key_date in resp.extraction.key_dates:
        if not key_date.is_deadline:
            continue
        add(
            key_date.date,
            key_date.label or "Document deadline",
            resp.extraction.issuer,
        )

    lines.append("END:VCALENDAR")
    return "\r\n".join(lines) + "\r\n"


def build_markdown(resp: AnalyzeResponse) -> str:
    """Render the plan as a shareable Markdown checklist."""
    extraction = resp.extraction
    triage = resp.triage
    plan = resp.plan

    lines = [
        f"# {plan.headline}",
        "",
        f"**Summary:** {triage.summary}",
        "",
        f"**Urgency:** {triage.urgency}  ",
        f"**Category:** {triage.category}  ",
        f"**Issuer:** {extraction.issuer or 'Unknown'}  ",
        f"**Document:** {extraction.document_type or 'Unknown'}",
        "",
        f"**Risk if ignored:** {plan.risk_if_ignored}",
        "",
        "## Action plan",
        "",
    ]

    for step in plan.steps:
        due = f" (due {step.due_date})" if step.due_date else ""
        source = (
            f" — [source]({step.source_url})"
            if step.source_url
            else " — _unverified, general advice_"
        )
        lines.append(f"- [ ] {step.action}{due}{source}")

    if extraction.key_dates:
        lines.extend(["", "## Key dates", ""])
        for key_date in extraction.key_dates:
            marker = "**deadline**" if key_date.is_deadline else "reference"
            lines.append(
                f"- {key_date.label}: {key_date.date or 'unknown'} ({marker})"
            )

    if plan.draft_message:
        lines.extend(["", "## Draft message", ""])
        for line in plan.draft_message.splitlines():
            lines.append(f"> {line}" if line else ">")

    if resp.sources:
        lines.extend(["", "## Sources", ""])
        for source in resp.sources:
            tag = " _(mock)_" if source.mock else ""
            lines.append(f"- [{source.title}]({source.url}){tag}")

    lines.extend(["", "---", "", plan.disclaimer or ""])
    return "\n".join(lines).strip() + "\n"

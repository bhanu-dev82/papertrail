"""Canned demo data so the app never breaks without API keys."""

from __future__ import annotations

import uuid
from datetime import date, timedelta

from .config import settings
from .schemas import (
    AnalyzeResponse,
    Extraction,
    KeyDate,
    Plan,
    PlanStep,
    Source,
    Triage,
    TraceEntry,
)

DISCLAIMER = "This is not legal or financial advice. Verify details with the issuer."

BESCOM_URL = "https://bescom.karnataka.gov.in/"
DISPUTE_URL = "https://example.org/how-to-dispute-electricity-bill"
LATE_FEE_URL = "https://example.org/late-fee-rules"


def _iso(offset_days: int) -> str:
    return (date.today() + timedelta(days=offset_days)).isoformat()


MOCK_SOURCES: list[Source] = [
    Source(
        title="BESCOM — Bangalore Electricity Supply Company (official)",
        url=BESCOM_URL,
        snippet=(
            "Official BESCOM portal for bill payment, new connections and "
            "consumer services in Bangalore."
        ),
        mock=True,
    ),
    Source(
        title="How to dispute an electricity bill",
        url=DISPUTE_URL,
        snippet=(
            "Step-by-step guide to checking your meter reading and raising a "
            "billing complaint with your electricity provider."
        ),
        mock=True,
    ),
    Source(
        title="Late payment fee rules for utility bills",
        url=LATE_FEE_URL,
        snippet=(
            "Explains how late payment fees and disconnection notices typically "
            "work, and how to request more time."
        ),
        mock=True,
    ),
]


def mock_extraction() -> Extraction:
    return Extraction(
        document_type="electricity bill",
        issuer="BESCOM",
        recipient_name="Asha Rao",
        reference_numbers=["Acct 7712-3381-09", "Bill No. 2026-10-55821"],
        amounts=["₹2,340.00 due", "Late fee ₹150 after due date"],
        key_dates=[
            KeyDate(
                label="Bill date", date=_iso(-5), is_deadline=False
            ),
            KeyDate(
                label="Payment due", date=_iso(4), is_deadline=True
            ),
            KeyDate(
                label="Disconnection notice date", date=_iso(18), is_deadline=True
            ),
        ],
        requested_actions=[
            "Pay the amount due by the due date",
            "Contact customer care to dispute charges",
        ],
        raw_text_excerpt=(
            "BANGALORE ELECTRICITY SUPPLY CO. Account 7712-3381-09. Bill No. "
            "2026-10-55821. Units consumed 312 kWh. Amount payable ₹2,340.00. "
            "Pay by the due date to avoid a late payment fee of ₹150. "
            "Disconnection may occur if the bill remains unpaid."
        ),
        language="en",
    )


def mock_triage() -> Triage:
    return Triage(
        category="bill",
        urgency="high",
        summary=(
            "Your electricity bill of ₹2,340 is due in 4 days; pay on time to "
            "avoid a ₹150 late fee."
        ),
        search_queries=[
            "BESCOM how to pay electricity bill online",
            "BESCOM dispute electricity bill charges process",
        ],
    )


def mock_plan() -> Plan:
    return Plan(
        headline="Pay ₹2,340 in 4 days to avoid a ₹150 late fee",
        risk_if_ignored=(
            "A ₹150 late fee is added after the due date and service may be "
            "disconnected if the bill stays unpaid."
        ),
        steps=[
            PlanStep(
                step=1,
                action="Pay ₹2,340.00 online through the BESCOM portal before the due date.",
                due_date=_iso(4),
                source_url=BESCOM_URL,
                verified=True,
            ),
            PlanStep(
                step=2,
                action="Check the meter reading on your bill against the meter at home.",
                due_date="",
                source_url="",
                verified=False,
            ),
            PlanStep(
                step=3,
                action="Raise a billing complaint with BESCOM if the reading or charges look wrong.",
                due_date="",
                source_url=DISPUTE_URL,
                verified=True,
            ),
            PlanStep(
                step=4,
                action="Set a reminder for the next billing cycle so this does not repeat.",
                due_date="",
                source_url="",
                verified=False,
            ),
        ],
        draft_message=(
            "Subject: Dispute of bill no. 2026-10-55821 (Acct 7712-3381-09)\n\n"
            "Dear BESCOM Customer Care,\n\n"
            "I am writing about the bill dated "
            f"{_iso(-5)} for the amount of ₹2,340.00. I believe the charges may "
            "be incorrect because the meter reading on the bill does not match "
            "my meter reading of [your reading].\n\n"
            "Please review the bill and confirm the correct amount. I am happy "
            "to provide a photo of the meter. I request that any late fee be "
            "waived while this is being reviewed.\n\n"
            "Thank you,\n[Your Name]\n[Your phone number]\n[Your account number]"
        ),
        disclaimer=DISCLAIMER,
    )


def mock_response() -> AnalyzeResponse:
    return AnalyzeResponse(
        id=uuid.uuid4().hex,
        mock=True,
        extraction=mock_extraction(),
        triage=mock_triage(),
        sources=[source.model_copy(deep=True) for source in MOCK_SOURCES],
        plan=mock_plan(),
        trace=[
            TraceEntry(
                stage="read",
                provider="mock",
                model=settings.model_vision,
                latency_ms=0,
                note="mock mode",
            ),
            TraceEntry(
                stage="triage",
                provider="mock",
                model=settings.model_fast,
                latency_ms=0,
                note="mock mode",
            ),
            TraceEntry(
                stage="verify",
                provider="mock",
                model="tavily-search",
                latency_ms=0,
                note="mock mode",
            ),
            TraceEntry(
                stage="plan",
                provider="mock",
                model=settings.model_reason,
                latency_ms=0,
                note="mock mode",
            ),
        ],
    )

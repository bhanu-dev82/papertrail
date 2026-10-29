"""Pydantic models shared by the pipeline, API and exporters."""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field


class KeyDate(BaseModel):
    label: str = ""  # e.g. "Payment due"
    date: str = ""  # ISO YYYY-MM-DD, or "" if unknown
    is_deadline: bool = False


class Extraction(BaseModel):
    document_type: str = ""
    issuer: str = ""
    recipient_name: str = ""
    reference_numbers: list[str] = Field(default_factory=list)
    amounts: list[str] = Field(default_factory=list)  # human-readable e.g. "₹2,340.00 due"
    key_dates: list[KeyDate] = Field(default_factory=list)
    requested_actions: list[str] = Field(default_factory=list)
    raw_text_excerpt: str = ""  # up to 600 chars of transcribed text
    language: str = "en"


class Triage(BaseModel):
    category: Literal[
        "bill",
        "tax",
        "legal",
        "medical",
        "banking",
        "government",
        "insurance",
        "housing",
        "other",
    ] = "other"
    urgency: Literal["low", "medium", "high", "critical"] = "medium"
    summary: str = ""
    search_queries: list[str] = Field(default_factory=list)


class Source(BaseModel):
    title: str = ""
    url: str = ""
    snippet: str = ""
    mock: bool = False


class PlanStep(BaseModel):
    step: int = 0
    action: str = ""
    due_date: str = ""  # ISO or ""
    source_url: str = ""  # must be one of the Source urls, or ""
    verified: bool = False


class Plan(BaseModel):
    headline: str = ""
    risk_if_ignored: str = ""
    steps: list[PlanStep] = Field(default_factory=list)
    draft_message: str = ""  # polite email/letter the user can send, or "" if none needed
    disclaimer: str = ""


class TraceEntry(BaseModel):
    stage: Literal["read", "triage", "verify", "plan"]
    provider: str  # "nebius-token-factory" | "tavily" | "mock"
    model: str  # model id or "tavily-search" or "mock"
    latency_ms: int = 0
    prompt_tokens: int = 0
    completion_tokens: int = 0
    degraded: bool = False
    note: str = ""


class AnalyzeResponse(BaseModel):
    id: str  # uuid4 hex
    mock: bool
    extraction: Extraction
    triage: Triage
    sources: list[Source]
    plan: Plan
    trace: list[TraceEntry]

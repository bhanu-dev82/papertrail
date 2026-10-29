"""Pipeline orchestration: read → triage → verify → plan."""

from __future__ import annotations

import base64
import io
import json
import logging
import uuid
from collections import OrderedDict
from datetime import date

from PIL import Image
from pydantic import ValidationError

from . import llm, mock_data, prompts, search
from .config import settings
from .schemas import (
    AnalyzeResponse,
    Extraction,
    Plan,
    PlanStep,
    Source,
    TraceEntry,
    Triage,
)

logger = logging.getLogger(__name__)

MAX_RESULTS = 20
RESULTS: "OrderedDict[str, AnalyzeResponse]" = OrderedDict()

MAX_SIDE = 1600
JPEG_QUALITY = 85

READ_FAILURE_MESSAGE = (
    "Could not read the document image. Try a clearer photo or enable MOCK_MODE."
)


# --------------------------------------------------------------------------- #
# Result cache (in memory only, last 20)
# --------------------------------------------------------------------------- #
def remember(resp: AnalyzeResponse) -> None:
    RESULTS[resp.id] = resp
    while len(RESULTS) > MAX_RESULTS:
        RESULTS.popitem(last=False)


def get_result(result_id: str) -> AnalyzeResponse | None:
    return RESULTS.get(result_id)


# --------------------------------------------------------------------------- #
# Validation helpers
# --------------------------------------------------------------------------- #
def _validate_extraction(data: dict) -> Extraction:
    defaults = Extraction().model_dump()
    merged = {**defaults, **(data if isinstance(data, dict) else {})}
    try:
        extraction = Extraction.model_validate(merged)
    except ValidationError:
        clean: dict = {}
        for field, value in merged.items():
            try:
                Extraction.model_validate({**defaults, field: value})
            except ValidationError:
                continue
            clean[field] = value
        extraction = Extraction.model_validate(clean)

    extraction.raw_text_excerpt = (extraction.raw_text_excerpt or "")[:600]
    return extraction


def _validate_triage(data: dict) -> Triage:
    data = data if isinstance(data, dict) else {}
    category = str(data.get("category") or "other").strip().lower()
    if category not in Triage.model_fields["category"].annotation.__args__:
        category = "other"
    urgency = str(data.get("urgency") or "medium").strip().lower()
    if urgency not in Triage.model_fields["urgency"].annotation.__args__:
        urgency = "medium"
    queries = data.get("search_queries")
    if not isinstance(queries, list):
        queries = []
    queries = [str(q).strip() for q in queries if str(q).strip()][:3]

    return Triage(
        category=category,  # type: ignore[arg-type]
        urgency=urgency,  # type: ignore[arg-type]
        summary=str(data.get("summary") or "")[:400],
        search_queries=queries,
    )


def _validate_plan(data: dict, sources: list[Source], issuer: str) -> Plan:
    data = data if isinstance(data, dict) else {}
    allowed_urls = {source.url for source in sources if source.url}

    steps: list[PlanStep] = []
    raw_steps = data.get("steps")
    if isinstance(raw_steps, list):
        for raw in raw_steps:
            if not isinstance(raw, dict):
                continue
            action = str(raw.get("action") or "").strip()
            if not action:
                continue
            due_date = str(raw.get("due_date") or "").strip()
            try:
                date.fromisoformat(due_date)
            except (ValueError, TypeError):
                due_date = ""
            source_url = str(raw.get("source_url") or "").strip()
            if source_url not in allowed_urls:
                source_url = ""
            steps.append(
                PlanStep(
                    step=len(steps) + 1,
                    action=action,
                    due_date=due_date,
                    source_url=source_url,
                    verified=bool(source_url),
                )
            )

    if not steps:
        steps = [
            PlanStep(
                step=1,
                action=(
                    f"Review the {data.get('headline') or 'document'} details and "
                    f"contact {issuer} if anything is unclear."
                ),
                verified=False,
            )
        ]

    disclaimer = str(data.get("disclaimer") or "").strip() or mock_data.DISCLAIMER
    return Plan(
        headline=str(data.get("headline") or "").strip()[:200],
        risk_if_ignored=str(data.get("risk_if_ignored") or "").strip()[:500],
        steps=steps,
        draft_message=str(data.get("draft_message") or ""),
        disclaimer=disclaimer,
    )


def _prepare_image(image_bytes: bytes) -> str:
    """Downscale, convert to RGB, re-encode JPEG and return base64."""
    try:
        with Image.open(io.BytesIO(image_bytes)) as image:
            rgb = image.convert("RGB")
            rgb.thumbnail((MAX_SIDE, MAX_SIDE), Image.LANCZOS)
            buffer = io.BytesIO()
            rgb.save(buffer, format="JPEG", quality=JPEG_QUALITY)
    except Exception as exc:
        logger.warning("image preprocessing failed: %s", exc)
        raise llm.PipelineError("read", READ_FAILURE_MESSAGE) from exc
    return base64.b64encode(buffer.getvalue()).decode("ascii")


# --------------------------------------------------------------------------- #
# Stages
# --------------------------------------------------------------------------- #
def _read_stage(b64_image: str) -> tuple[Extraction, TraceEntry]:
    messages = [
        {"role": "system", "content": prompts.READ_SYSTEM},
        {
            "role": "user",
            "content": [
                {
                    "type": "text",
                    "text": prompts.READ_USER.replace(
                        "{today}", date.today().isoformat()
                    ),
                },
                {
                    "type": "image_url",
                    "image_url": {
                        "url": f"data:image/jpeg;base64,{b64_image}",
                    },
                },
            ],
        },
    ]
    try:
        data, trace = llm.chat_json("vision", messages, stage="read", max_tokens=1500)
    except llm.PipelineError as exc:
        raise llm.PipelineError("read", READ_FAILURE_MESSAGE) from exc
    return _validate_extraction(data), trace


def _triage_stage(extraction: Extraction) -> tuple[Triage, TraceEntry]:
    messages = [
        {"role": "system", "content": prompts.TRIAGE_SYSTEM},
        {
            "role": "user",
            "content": prompts.TRIAGE_USER.replace(
                "{today}", date.today().isoformat()
            ).replace(
                "{extraction_json}",
                json.dumps(extraction.model_dump(), ensure_ascii=False),
            ),
        },
    ]
    data, trace = llm.chat_json("fast", messages, stage="triage", max_tokens=400)
    triage = _validate_triage(data)
    if not triage.search_queries:
        fallback_query = (
            f"{extraction.issuer} {extraction.document_type} how to respond"
        ).strip()
        triage.search_queries = [fallback_query or "how to respond to this document"]
    return triage, trace


def _plan_stage(
    extraction: Extraction, triage: Triage, sources: list[Source]
) -> tuple[Plan, TraceEntry]:
    messages = [
        {"role": "system", "content": prompts.PLAN_SYSTEM},
        {
            "role": "user",
            "content": prompts.PLAN_USER.replace(
                "{today}", date.today().isoformat()
            )
            .replace(
                "{extraction_json}",
                json.dumps(extraction.model_dump(), ensure_ascii=False),
            )
            .replace(
                "{triage_json}",
                json.dumps(triage.model_dump(), ensure_ascii=False),
            )
            .replace(
                "{sources_json}",
                json.dumps(
                    [source.model_dump() for source in sources], ensure_ascii=False
                ),
            ),
        },
    ]
    data, trace = llm.chat_json("reason", messages, stage="plan", max_tokens=4000)
    return _validate_plan(data, sources, extraction.issuer), trace


# --------------------------------------------------------------------------- #
# Entry point
# --------------------------------------------------------------------------- #
def analyze(image_bytes: bytes, mime: str) -> AnalyzeResponse:
    """Run the full pipeline. In mock mode returns canned data with a fresh id."""
    if settings.effective_mock:
        resp = mock_data.mock_response()
        remember(resp)
        return resp

    b64_image = _prepare_image(image_bytes)

    extraction, read_trace = _read_stage(b64_image)
    triage, triage_trace = _triage_stage(extraction)
    sources, verify_trace = search.search_sources(
        triage.search_queries, extraction.issuer
    )
    plan, plan_trace = _plan_stage(extraction, triage, sources)

    resp = AnalyzeResponse(
        id=uuid.uuid4().hex,
        mock=False,
        extraction=extraction,
        triage=triage,
        sources=sources,
        plan=plan,
        trace=[read_trace, triage_trace, verify_trace, plan_trace],
    )
    remember(resp)
    return resp

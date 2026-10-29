"""FastAPI app: upload → analyze → plan, plus static frontend and exports."""

from __future__ import annotations

import logging
import threading
import time
from collections import defaultdict, deque
from contextlib import asynccontextmanager
from datetime import datetime, timezone
from pathlib import Path

from fastapi import FastAPI, File, HTTPException, Request, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse, Response
from fastapi.staticfiles import StaticFiles
from starlette.concurrency import run_in_threadpool

from . import pipeline
from .config import settings
from .ics import build_ics, build_markdown
from .llm import PipelineError
from .schemas import AnalyzeResponse

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(name)s: %(message)s",
)
logger = logging.getLogger(__name__)

BASE_DIR = Path(__file__).resolve().parent.parent
STATIC_DIR = BASE_DIR / "static"
SAMPLE_PATH = BASE_DIR / "samples" / "electricity_bill.png"

ALLOWED_MIME = {"image/jpeg", "image/png", "image/webp"}
MAX_UPLOAD_BYTES = 8 * 1024 * 1024


def ensure_sample() -> None:
    """Generate the demo bill image on first use."""
    if SAMPLE_PATH.exists():
        return
    try:
        from samples.make_sample import make

        SAMPLE_PATH.parent.mkdir(parents=True, exist_ok=True)
        make(str(SAMPLE_PATH))
        logger.info("generated sample document at %s", SAMPLE_PATH)
    except Exception as exc:  # pragma: no cover - defensive
        logger.warning("could not generate sample document: %s", exc)


@asynccontextmanager
async def lifespan(_: FastAPI):
    ensure_sample()
    yield


app = FastAPI(
    title="PaperTrail",
    description=(
        "Snap any official document and get a verified action plan, powered by "
        "NVIDIA Nemotron models on Nebius Token Factory."
    ),
    version="1.0.0",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
)

if STATIC_DIR.is_dir():
    app.mount("/static", StaticFiles(directory=str(STATIC_DIR)), name="static")


# --------------------------------------------------------------------------- #
# Helpers
# --------------------------------------------------------------------------- #
def _pipeline_error_response(exc: PipelineError) -> JSONResponse:
    logger.warning("pipeline failed at stage=%s: %s", exc.stage, exc)
    return JSONResponse(
        status_code=502,
        content={"detail": str(exc), "stage": exc.stage},
    )


async def _analyze_bytes(data: bytes, mime: str) -> AnalyzeResponse:
    return await run_in_threadpool(pipeline.analyze, data, mime)


# --------------------------------------------------------------------------- #
# Optional demo spend guard (in-memory; single instance)
# --------------------------------------------------------------------------- #
_rate_lock = threading.Lock()
_rate_day = ""
_rate_day_count = 0
_rate_ip_events: dict[str, deque[float]] = defaultdict(deque)


def _client_ip(request: Request) -> str:
    forwarded = request.headers.get("x-forwarded-for", "")
    if forwarded:
        return forwarded.split(",")[0].strip()
    return request.client.host if request.client else "unknown"


def _rate_limit_ok(request: Request) -> bool:
    global _rate_day, _rate_day_count

    day_limit = settings.demo_max_analyses_per_day
    ip_limit = settings.demo_max_analyses_per_ip_hour
    if not day_limit and not ip_limit:
        return True

    today = datetime.now(timezone.utc).date().isoformat()
    now = time.time()

    with _rate_lock:
        if today != _rate_day:
            _rate_day = today
            _rate_day_count = 0
            _rate_ip_events.clear()

        if day_limit and _rate_day_count >= day_limit:
            return False

        if ip_limit:
            events = _rate_ip_events[_client_ip(request)]
            cutoff = now - 3600
            while events and events[0] < cutoff:
                events.popleft()
            if len(events) >= ip_limit:
                return False
            events.append(now)

        _rate_day_count += 1
        return True


def _enforce_rate_limit(request: Request) -> None:
    if not _rate_limit_ok(request):
        raise HTTPException(
            status_code=429,
            detail="Demo limit reached. Please try again later.",
        )


# --------------------------------------------------------------------------- #
# Routes
# --------------------------------------------------------------------------- #
@app.get("/", include_in_schema=False)
async def index() -> FileResponse:
    return FileResponse(STATIC_DIR / "index.html")


@app.get("/sample-bill.png", include_in_schema=False)
async def sample_bill() -> FileResponse:
    """Serve the generated sample bill for the empty-state preview."""
    ensure_sample()
    return FileResponse(SAMPLE_PATH, media_type="image/png")


@app.get("/api/health")
async def health() -> dict:
    return {
        "status": "ok",
        "mock": settings.effective_mock,
        "models": {
            "vision": settings.model_vision,
            "fast": settings.model_fast,
            "reason": settings.model_reason,
        },
        "tavily": bool(settings.tavily_api_key) and not settings.effective_mock,
    }


@app.post("/api/analyze", response_model=AnalyzeResponse)
async def analyze(request: Request, file: UploadFile = File(...)):
    _enforce_rate_limit(request)
    mime = (file.content_type or "").split(";")[0].strip().lower()
    if mime not in ALLOWED_MIME:
        raise HTTPException(status_code=415, detail="Upload a JPG, PNG or WEBP image.")

    data = await file.read(MAX_UPLOAD_BYTES + 1)
    if len(data) > MAX_UPLOAD_BYTES:
        raise HTTPException(status_code=413, detail="Image is larger than 8 MB.")

    try:
        return await _analyze_bytes(data, mime)
    except PipelineError as exc:
        return _pipeline_error_response(exc)


@app.post("/api/analyze-sample", response_model=AnalyzeResponse)
async def analyze_sample(request: Request):
    _enforce_rate_limit(request)
    ensure_sample()
    if not SAMPLE_PATH.exists():
        raise HTTPException(
            status_code=500,
            detail="Sample document is missing and could not be generated.",
        )
    data = await run_in_threadpool(SAMPLE_PATH.read_bytes)
    try:
        return await _analyze_bytes(data, "image/png")
    except PipelineError as exc:
        return _pipeline_error_response(exc)


def _result_or_404(result_id: str) -> AnalyzeResponse:
    result = pipeline.get_result(result_id)
    if result is None:
        raise HTTPException(status_code=404, detail="Unknown result id.")
    return result


@app.get("/api/results/{result_id}/calendar.ics")
async def result_calendar(result_id: str) -> Response:
    result = _result_or_404(result_id)
    body = build_ics(result)
    return Response(
        content=body,
        media_type="text/calendar",
        headers={
            "Content-Disposition": f"attachment; filename=papertrail-{result.id}.ics"
        },
    )


@app.get("/api/results/{result_id}/plan.md")
async def result_markdown(result_id: str) -> Response:
    result = _result_or_404(result_id)
    body = build_markdown(result)
    return Response(
        content=body,
        media_type="text/markdown",
        headers={
            "Content-Disposition": f"attachment; filename=papertrail-{result.id}.md"
        },
    )

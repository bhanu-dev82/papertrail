"""Nebius Token Factory client wrapper with per-role routing and tracing."""

from __future__ import annotations

import functools
import logging
import time
from typing import Literal

from openai import OpenAI

from .config import settings
from .jsonutil import extract_json
from .schemas import TraceEntry

logger = logging.getLogger(__name__)

Role = Literal["vision", "fast", "reason"]

JSON_RETRY_PROMPT = (
    "Your previous reply was not valid JSON. Reply again with ONLY the JSON "
    "object, no prose."
)

PROVIDER = "nebius-token-factory"

# Nemotron 3 Nano and Super-VL are reasoning-first on Token Factory: without
# this flag they spend the whole stage budget on hidden thinking and return
# empty content (finish_reason="length"). Plan keeps full reasoning on Ultra.
DISABLE_THINKING = {"chat_template_kwargs": {"enable_thinking": False}}
NO_THINKING_ROLES = {"vision", "fast"}


class PipelineError(Exception):
    """Raised when a pipeline stage cannot complete."""

    def __init__(self, stage: str, message: str):
        super().__init__(message)
        self.stage = stage


@functools.lru_cache(maxsize=8)
def _client(base_url: str) -> OpenAI:
    return OpenAI(
        api_key=settings.nebius_api_key,
        base_url=base_url,
        timeout=settings.timeout,
    )


def _role_target(role: str) -> tuple[str, str]:
    if role == "vision":
        return settings.base_url_vision, settings.model_vision
    if role == "fast":
        return settings.base_url_fast, settings.model_fast
    if role == "reason":
        return settings.base_url_reason, settings.model_reason
    raise ValueError(f"Unknown role: {role}")


def _call_model(
    base_url: str,
    model: str,
    messages: list,
    max_tokens: int,
    extra_body: dict | None = None,
) -> tuple[str, int, int, int]:
    """Call one chat completion and return (content, latency_ms, prompt_tokens, completion_tokens)."""
    started = time.perf_counter()
    kwargs = {"extra_body": extra_body} if extra_body else {}
    response = _client(base_url).chat.completions.create(
        model=model,
        messages=messages,
        temperature=0.2,
        max_tokens=max_tokens,
        **kwargs,
    )
    latency_ms = int((time.perf_counter() - started) * 1000)

    content = ""
    if response.choices:
        content = response.choices[0].message.content or ""

    usage = getattr(response, "usage", None)
    prompt_tokens = int(getattr(usage, "prompt_tokens", 0) or 0)
    completion_tokens = int(getattr(usage, "completion_tokens", 0) or 0)
    return content, latency_ms, prompt_tokens, completion_tokens


def _call_with_json_retry(
    base_url: str,
    model: str,
    messages: list,
    max_tokens: int,
    extra_body: dict | None = None,
) -> tuple[dict, int, int, int]:
    """Call the model, retrying once when the reply is not valid JSON."""
    total_latency = 0
    total_prompt = 0
    total_completion = 0
    current_messages = list(messages)

    for attempt in range(2):
        text, latency_ms, prompt_tokens, completion_tokens = _call_model(
            base_url, model, current_messages, max_tokens, extra_body
        )
        total_latency += latency_ms
        total_prompt += prompt_tokens
        total_completion += completion_tokens
        try:
            data = extract_json(text)
        except ValueError:
            if attempt == 0:
                current_messages = list(messages) + [
                    {"role": "user", "content": JSON_RETRY_PROMPT}
                ]
                continue
            raise
        logger.info(
            "llm call model=%s latency_ms=%d prompt_tokens=%d completion_tokens=%d",
            model,
            total_latency,
            total_prompt,
            total_completion,
        )
        return data, total_latency, total_prompt, total_completion

    raise ValueError("No JSON object found")


def _log_api_failure(role: str, base_url: str, model: str, exc: Exception) -> None:
    status = getattr(exc, "status_code", None)
    text = str(exc)
    logger.warning(
        "llm api failure role=%s model=%s base_url=%s status=%s error=%s",
        role,
        model,
        base_url,
        status,
        text,
    )
    if status == 404 or "not found" in text.lower():
        logger.error(
            "Model '%s' was not found at %s. Set the base URL env var for the "
            "'%s' role to the region that hosts this model (see .env.example).",
            model,
            base_url,
            role,
        )


def _text_only_messages(messages: list) -> list:
    """Strip image parts for a text-only fallback after OCR/vision failure."""
    converted = []
    for message in messages:
        content = message.get("content")
        if isinstance(content, list):
            parts = [
                part.get("text", "")
                for part in content
                if isinstance(part, dict) and part.get("type") == "text"
            ]
            text = "\n".join(part for part in parts if part)
            content = "OCR unavailable. The document image could not be read. " + text
        converted.append({**message, "content": content})
    return converted


def chat_json(
    role: Role,
    messages: list,
    stage: str,
    max_tokens: int = 1500,
) -> tuple[dict, TraceEntry]:
    """Run a chat completion that must return a JSON object, with tracing."""
    base_url, model = _role_target(role)
    extra_body = DISABLE_THINKING if role in NO_THINKING_ROLES else None
    degraded = False
    note = ""

    try:
        data, latency_ms, prompt_tokens, completion_tokens = _call_with_json_retry(
            base_url, model, messages, max_tokens, extra_body
        )
    except ValueError as exc:
        raise PipelineError(stage, str(exc)) from exc
    except Exception as exc:
        _log_api_failure(role, base_url, model, exc)
        if role not in ("vision", "reason"):
            raise PipelineError(stage, str(exc)) from exc

        # Retry once on the fallback model (Super) against the reasoning base URL.
        fallback_messages = (
            _text_only_messages(messages) if role == "vision" else messages
        )
        try:
            data, latency_ms, prompt_tokens, completion_tokens = (
                _call_with_json_retry(
                    settings.base_url_reason,
                    settings.model_fallback,
                    fallback_messages,
                    max_tokens,
                    extra_body,
                )
            )
        except Exception as fallback_exc:
            _log_api_failure(
                role, settings.base_url_reason, settings.model_fallback, fallback_exc
            )
            raise PipelineError(stage, str(fallback_exc)) from fallback_exc

        model = settings.model_fallback
        degraded = True
        note = f"fallback: {type(exc).__name__}"

    trace = TraceEntry(
        stage=stage,  # type: ignore[arg-type]
        provider=PROVIDER,
        model=model,
        latency_ms=latency_ms,
        prompt_tokens=prompt_tokens,
        completion_tokens=completion_tokens,
        degraded=degraded,
        note=note,
    )
    return data, trace

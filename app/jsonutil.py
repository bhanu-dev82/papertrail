"""Robust JSON extraction from LLM replies."""

from __future__ import annotations

import json
import re

_THINK_RE = re.compile(r"<think>.*?</think>", re.DOTALL | re.IGNORECASE)
_FENCE_RE = re.compile(r"```(?:json)?\s*(.*?)```", re.DOTALL | re.IGNORECASE)


def extract_json(text: str) -> dict:
    """Return the JSON object contained in an LLM reply.

    Handles reasoning blocks, markdown fences and surrounding prose.
    Raises ValueError when no JSON object can be found.
    """
    if not isinstance(text, str):
        raise ValueError("No JSON object found")

    cleaned = _THINK_RE.sub("", text).strip()
    if not cleaned:
        raise ValueError("No JSON object found")

    fence = _FENCE_RE.search(cleaned)
    if fence:
        cleaned = fence.group(1).strip()

    try:
        parsed = json.loads(cleaned)
        if isinstance(parsed, dict):
            return parsed
    except (json.JSONDecodeError, TypeError):
        pass

    start = cleaned.find("{")
    end = cleaned.rfind("}")
    if start != -1 and end > start:
        candidate = cleaned[start : end + 1]
        try:
            parsed = json.loads(candidate)
            if isinstance(parsed, dict):
                return parsed
        except json.JSONDecodeError:
            pass

    raise ValueError("No JSON object found")

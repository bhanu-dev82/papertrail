"""Settings loaded from environment variables (via .env when present)."""

from __future__ import annotations

import os
from dataclasses import dataclass

from dotenv import load_dotenv

load_dotenv()

_TRUE_VALUES = {"true", "1", "yes"}


def _env_bool(name: str, default: bool = False) -> bool:
    raw = os.getenv(name)
    if raw is None or raw.strip() == "":
        return default
    return raw.strip().lower() in _TRUE_VALUES


def _env_str(name: str, default: str = "") -> str:
    raw = os.getenv(name)
    return default if raw is None else raw.strip()


def _env_int(name: str, default: int = 0) -> int:
    raw = os.getenv(name)
    if raw is None or raw.strip() == "":
        return default
    try:
        return int(raw)
    except ValueError:
        return default


@dataclass(frozen=True)
class Settings:
    mock_mode: bool
    nebius_api_key: str
    tavily_api_key: str
    base_url_vision: str
    base_url_fast: str
    base_url_reason: str
    model_vision: str
    model_fast: str
    model_reason: str
    model_fallback: str
    timeout: float
    demo_max_analyses_per_day: int = 0
    demo_max_analyses_per_ip_hour: int = 0

    @classmethod
    def from_env(cls) -> "Settings":
        try:
            timeout = float(_env_str("REQUEST_TIMEOUT_SECONDS", "90") or 90)
        except ValueError:
            timeout = 90.0
        return cls(
            mock_mode=_env_bool("MOCK_MODE", False),
            nebius_api_key=_env_str("NEBIUS_API_KEY"),
            tavily_api_key=_env_str("TAVILY_API_KEY"),
            base_url_vision=_env_str(
                "NEBIUS_BASE_URL_VISION", "https://api.tokenfactory.nebius.com/v1/"
            ),
            base_url_fast=_env_str(
                "NEBIUS_BASE_URL_FAST", "https://api.tokenfactory.nebius.com/v1/"
            ),
            base_url_reason=_env_str(
                "NEBIUS_BASE_URL_REASON",
                "https://api.tokenfactory.us-central1.nebius.com/v1/",
            ),
            model_vision=_env_str("MODEL_VISION", "nvidia/Nemotron-3.5-Super-VL"),
            model_fast=_env_str(
                "MODEL_FAST", "nvidia/NVIDIA-Nemotron-3-Nano-30B-A3B"
            ),
            model_reason=_env_str("MODEL_REASON", "nvidia/Nemotron-3-Ultra-550b-a55b"),
            model_fallback=_env_str(
                "MODEL_FALLBACK", "nvidia/nemotron-3-super-120b-a12b"
            ),
            timeout=timeout,
            demo_max_analyses_per_day=_env_int("DEMO_MAX_ANALYSES_PER_DAY", 0),
            demo_max_analyses_per_ip_hour=_env_int(
                "DEMO_MAX_ANALYSES_PER_IP_HOUR", 0
            ),
        )

    @property
    def effective_mock(self) -> bool:
        """Mock the whole pipeline when asked to, or when no Nebius key exists."""
        return self.mock_mode or not self.nebius_api_key


settings = Settings.from_env()

"""Tavily web search wrapper returning cited sources."""

from __future__ import annotations

import logging
import re
import time
from urllib.parse import urlparse

from . import mock_data
from .config import settings
from .schemas import Source, TraceEntry

logger = logging.getLogger(__name__)

MAX_QUERIES = 3
MAX_SOURCES = 6
MAX_CANDIDATES = MAX_QUERIES * 3

# Social, directory and aggregator domains are not source material for an
# official procedure. Drop them before the planner can cite them.
BLOCKED_DOMAINS = {
    "facebook.com",
    "instagram.com",
    "linkedin.com",
    "pinterest.com",
    "quora.com",
    "reddit.com",
    "tiktok.com",
    "tracxn.com",
    "twitter.com",
    "x.com",
    "yahoo.com",
    "yelp.com",
    "youtube.com",
}

OFFICIAL_SUFFIXES = (".gov", ".gov.in", ".nic.in", ".mil")
TRUSTED_SUFFIXES = (".org", ".co.in", ".edu", ".ac.in")


def _hostname(url: str) -> str:
    try:
        return (urlparse(url).hostname or "").lower()
    except ValueError:
        return ""


def _is_blocked(host: str) -> bool:
    return any(host == domain or host.endswith("." + domain) for domain in BLOCKED_DOMAINS) or host.startswith("hotfrog.")


def _source_score(source: Source) -> int:
    host = _hostname(source.url)
    if not host:
        return 0
    score = 0
    if host.endswith(OFFICIAL_SUFFIXES):
        score += 4
    elif host.endswith(TRUSTED_SUFFIXES):
        score += 2
    if "official" in source.title.lower():
        score += 1
    return score


def _order_sources(sources: list[Source], issuer: str = "") -> list[Source]:
    """Drop social/aggregator results, prefer official domains, and keep only
    sources that actually mention the issuer when an issuer is available."""
    usable = [source for source in sources if not _is_blocked(_hostname(source.url))]
    if not usable:
        return []

    ranked = sorted(usable, key=_source_score, reverse=True)
    tokens = _issuer_tokens(issuer)

    if tokens:
        relevant = [
            source
            for source in ranked
            if _mentions_issuer(source, tokens)
        ]
        if not relevant:
            return []
        trusted = [source for source in relevant if _source_score(source) >= 2]
        return trusted or relevant

    trusted = [source for source in ranked if _source_score(source) >= 2]
    return trusted or ranked


ISSUER_STOPWORDS = {
    "the", "and", "for", "of", "co", "company", "limited", "ltd", "inc",
    "llc", "corporation", "corp", "services", "service", "department",
    "dept", "government", "govt", "authority", "board", "office", "account",
    "payment", "bill", "notice", "letter", "statement", "document", "number",
    "date", "due", "total", "amount", "unknown",
}


def _issuer_tokens(issuer: str) -> list[str]:
    words = re.findall(r"[a-z0-9]+", str(issuer or "").lower())
    return [word for word in words if len(word) >= 3 and word not in ISSUER_STOPWORDS]


def _mentions_issuer(source: Source, tokens: list[str]) -> bool:
    haystack = " ".join(
        [_hostname(source.url), source.title or "", source.snippet or ""]
    ).lower()
    return any(token in haystack for token in tokens)


def _mock_result(note: str = "", degraded: bool = False) -> tuple[list[Source], TraceEntry]:
    sources = [source.model_copy(deep=True) for source in mock_data.MOCK_SOURCES]
    trace = TraceEntry(
        stage="verify",
        provider="mock",
        model="mock",
        latency_ms=0,
        degraded=degraded,
        note=note or "mock sources",
    )
    return sources, trace


def _issuer_query_name(issuer: str) -> str:
    text = str(issuer or "").strip()
    match = re.search(r"\(([^)]{1,24})\)", text)
    if match and not re.search(r"sample|copy|duplicate", match.group(1), re.IGNORECASE):
        return match.group(1).strip()
    return text.strip(" .,")


def search_sources(
    queries: list[str], issuer: str = ""
) -> tuple[list[Source], TraceEntry]:
    """Search the web for official guidance; fall back to mock sources."""
    if settings.effective_mock or not settings.tavily_api_key:
        return _mock_result()

    started = time.perf_counter()
    try:
        # Imported lazily so MOCK mode never needs the package at runtime.
        from tavily import TavilyClient

        client = TavilyClient(api_key=settings.tavily_api_key)
        seen: set[str] = set()
        sources: list[Source] = []

        search_queries = [query.strip() for query in queries if query.strip()]
        issuer_name = _issuer_query_name(issuer)
        if issuer_name:
            official_query = f"{issuer_name} official website"
            if len(search_queries) >= MAX_QUERIES:
                search_queries = search_queries[: MAX_QUERIES - 1] + [official_query]
            else:
                search_queries.append(official_query)

        for query in search_queries[:MAX_QUERIES]:
            payload = client.search(
                query=query, max_results=3, search_depth="basic"
            )
            results = (payload or {}).get("results", []) or []
            for item in results:
                if not isinstance(item, dict):
                    continue
                url = str(item.get("url") or "").strip()
                if not url or url in seen:
                    continue
                seen.add(url)
                sources.append(
                    Source(
                        title=str(item.get("title") or url).strip(),
                        url=url,
                        snippet=str(item.get("content") or "")[:300],
                        mock=False,
                    )
                )
                if len(sources) >= MAX_CANDIDATES:
                    break
            if len(sources) >= MAX_CANDIDATES:
                break

        if not sources:
            raise RuntimeError("Tavily returned no results")

        ordered = _order_sources(sources, issuer)
        if ordered:
            sources = ordered[:MAX_SOURCES]
        else:
            sources = []

        latency_ms = int((time.perf_counter() - started) * 1000)
        logger.info(
            "tavily search queries=%d sources=%d latency_ms=%d",
            len(queries),
            len(sources),
            latency_ms,
        )
        trace = TraceEntry(
            stage="verify",
            provider="tavily",
            model="tavily-search",
            latency_ms=latency_ms,
        )
        return sources, trace
    except Exception as exc:
        logger.warning("tavily search failed: %s", exc)
        latency_ms = int((time.perf_counter() - started) * 1000)
        sources, _ = _mock_result(
            note=f"tavily failed: {type(exc).__name__}", degraded=True
        )
        trace = TraceEntry(
            stage="verify",
            provider="tavily",
            model="tavily-search",
            latency_ms=latency_ms,
            degraded=True,
            note=f"tavily failed: {type(exc).__name__}",
        )
        return sources, trace

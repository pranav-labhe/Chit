"""Lightweight, zero-dependency autonomous web retrieval engine for Chit."""
from __future__ import annotations

import html
import json
import logging
import re
import urllib.parse
import urllib.request
from typing import Any

log = logging.getLogger(__name__)

USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
    "AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/122.0.0.0 Safari/537.36"
)
DEFAULT_TIMEOUT = 3.5


def budget_snippet(snippet: str, max_chars: int = 100) -> str:
    """Format and word-boundary slice a snippet to fit within a tight context budget."""
    clean = " ".join(snippet.split())
    if not clean or len(clean) <= max_chars:
        return clean
    truncated = clean[:max_chars]
    if " " in truncated:
        truncated = truncated.rsplit(" ", 1)[0]
    return truncated.rstrip(",.;- ") + "."


def _query_duckduckgo_json(query: str, timeout: float = DEFAULT_TIMEOUT) -> list[str]:
    """Query DuckDuckGo Instant Answer JSON API for factual abstracts."""
    encoded = urllib.parse.quote_plus(query.strip())
    url = f"https://api.duckduckgo.com/?q={encoded}&format=json&no_html=1&skip_disambig=1"
    req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        data = json.loads(resp.read().decode("utf-8", errors="ignore"))

    snippets: list[str] = []
    abstract = (data.get("AbstractText") or data.get("Abstract") or "").strip()
    if abstract:
        snippets.append(abstract)

    topics = data.get("RelatedTopics", [])
    for item in topics:
        if isinstance(item, dict) and item.get("Text"):
            text = item["Text"].strip()
            if text and text not in snippets:
                snippets.append(text)
        elif isinstance(item, dict) and "Topics" in item:
            for sub in item.get("Topics", []):
                if isinstance(sub, dict) and sub.get("Text"):
                    text = sub["Text"].strip()
                    if text and text not in snippets:
                        snippets.append(text)

    return snippets


def _query_duckduckgo_html(query: str, timeout: float = DEFAULT_TIMEOUT) -> list[str]:
    """Fallback query to DuckDuckGo HTML search for organic snippets."""
    data = urllib.parse.urlencode({"q": query.strip()}).encode("utf-8")
    req = urllib.request.Request(
        "https://html.duckduckgo.com/html/",
        data=data,
        headers={
            "User-Agent": USER_AGENT,
            "Content-Type": "application/x-www-form-urlencoded",
        },
    )
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        raw_html = resp.read().decode("utf-8", errors="ignore")

    snippets: list[str] = []
    # Match standard DDG HTML result snippet containers
    patterns = [
        r'<a[^>]*class="[^"]*result__snippet[^"]*"[^>]*>(.*?)</a>',
        r'<td[^>]*class="[^"]*result-snippet[^"]*"[^>]*>(.*?)</td>',
        r'<div[^>]*class="[^"]*result__snippet[^"]*"[^>]*>(.*?)</div>',
    ]
    for pattern in patterns:
        matches = re.findall(pattern, raw_html, re.DOTALL | re.IGNORECASE)
        for match in matches:
            clean_text = re.sub(r"<[^>]+>", "", match)
            clean_text = html.unescape(clean_text).strip()
            clean_text = " ".join(clean_text.split())
            if clean_text and clean_text not in snippets:
                snippets.append(clean_text)

    return snippets


def search_web(query: str, max_results: int = 2, max_chars: int = 100, timeout: float = DEFAULT_TIMEOUT) -> list[str]:
    """Execute dual-strategy web retrieval with strict time and length bounds.

    Returns a list of clean, word-boundary budgeted snippet strings.
    Never raises an exception; returns [] on any network or parsing error.
    """
    cleaned_query = query.strip()
    if not cleaned_query:
        return []

    results: list[str] = []

    # 1. Try DuckDuckGo Instant Answer API
    try:
        results = _query_duckduckgo_json(cleaned_query, timeout=timeout)
    except Exception as exc:
        log.debug("DuckDuckGo Instant Answer query failed: %s", exc)

    # 2. If no snippets found, fall back to DuckDuckGo HTML
    if not results:
        try:
            results = _query_duckduckgo_html(cleaned_query, timeout=timeout)
        except Exception as exc:
            log.debug("DuckDuckGo HTML query fallback failed: %s", exc)

    # 3. Budget and slice top results
    budgeted: list[str] = []
    for snippet in results[:max_results]:
        b = budget_snippet(snippet, max_chars=max_chars)
        if b:
            budgeted.append(b)

    return budgeted

"""Lightweight, zero-dependency autonomous web retrieval engine for Chit."""
from __future__ import annotations

import html
from html.parser import HTMLParser
import ipaddress
import json
import logging
import os
import re
import socket
import urllib.parse
import urllib.request
from typing import Any

log = logging.getLogger(__name__)

USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
    "AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/122.0.0.0 Safari/537.36"
)
WIKIPEDIA_USER_AGENT = "ChitAssistant/0.3 (https://chitt.online; contact@chitt.online)"
DEFAULT_TIMEOUT = 3.5
CRAWL_TIMEOUT = 2.5
MAX_CRAWL_BYTES = 131072  # 128 KB stream cap


class SearchResult(str):
    """A budgeted snippet string enriched with crawl and origin metadata.

    Inherits from str so it natively satisfies all string operations,
    equality checks, serialization, and existing test contracts.
    """

    def __new__(cls, snippet: str, url: str = "", title: str = "", domain: str = ""):
        clean = " ".join(str(snippet).split())
        instance = super().__new__(cls, clean)
        instance.snippet = clean
        instance.url = url
        instance.title = title
        instance.domain = domain or (_extract_domain(url) if url else "")
        return instance

    def to_dict(self) -> dict[str, str]:
        return {
            "title": self.title,
            "snippet": self.snippet,
            "url": self.url,
            "domain": self.domain,
        }


def _extract_domain(url: str) -> str:
    try:
        parsed = urllib.parse.urlparse(url)
        netloc = parsed.netloc.split(":")[0].lower()
        if netloc.startswith("www."):
            netloc = netloc[4:]
        return netloc
    except Exception:
        return ""


def is_safe_url(url: str) -> bool:
    """SSRF guard: reject non-http(s) schemes and private/loopback/link-local/reserved IPs."""
    try:
        parsed = urllib.parse.urlparse(url)
        if parsed.scheme not in ("http", "https"):
            return False
        hostname = parsed.hostname
        if not hostname:
            return False

        try:
            ip_obj = ipaddress.ip_address(hostname)
            ips = [ip_obj]
        except ValueError:
            port = parsed.port or (443 if parsed.scheme == "https" else 80)
            addr_info = socket.getaddrinfo(hostname, port, type=socket.SOCK_STREAM)
            ips = [ipaddress.ip_address(item[4][0]) for item in addr_info]

        for ip in ips:
            if (
                ip.is_private
                or ip.is_loopback
                or ip.is_link_local
                or ip.is_reserved
                or ip.is_multicast
                or ip.is_unspecified
            ):
                return False
        return True
    except Exception as exc:
        log.debug("SSRF validation failed for %s: %s", url, exc)
        return False


class _TextExtractParser(HTMLParser):
    def __init__(self):
        super().__init__()
        self.text_parts: list[str] = []
        self._ignore_depth = 0
        self._ignored_tags = {"script", "style", "nav", "header", "footer", "aside", "noscript", "svg"}

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]):
        if tag.lower() in self._ignored_tags:
            self._ignore_depth += 1

    def handle_endtag(self, tag: str):
        if tag.lower() in self._ignored_tags and self._ignore_depth > 0:
            self._ignore_depth -= 1

    def handle_data(self, data: str):
        if self._ignore_depth == 0:
            cleaned = data.strip()
            if cleaned:
                self.text_parts.append(cleaned)


def extract_clean_text_from_html(raw_html: str) -> str:
    parser = _TextExtractParser()
    try:
        parser.feed(raw_html)
        return " ".join(parser.text_parts)
    except Exception:
        clean = re.sub(r"<(script|style|nav|header|footer|aside)[^>]*>.*?</\1>", " ", raw_html, flags=re.DOTALL | re.IGNORECASE)
        clean = re.sub(r"<[^>]+>", " ", clean)
        return " ".join(html.unescape(clean).split())


def extract_relevant_proposition(text: str, query: str, max_chars: int = 80) -> str:
    """Split text into sentences, score against query terms, and return the best 60-80 char proposition."""
    raw_sentences = re.split(r"(?<=[.!?])\s+", text)
    query_tokens = set(re.findall(r"\w+", query.lower()))
    stop_words = {"the", "a", "an", "is", "are", "was", "were", "of", "in", "to", "and", "or", "what", "who", "where", "how", "tell", "about"}
    meaningful_tokens = {w for w in query_tokens if w not in stop_words and len(w) > 2} or query_tokens

    scored: list[tuple[float, str]] = []
    for s in raw_sentences:
        clean_s = " ".join(s.split())
        if len(clean_s) < 15:
            continue
        s_tokens = set(re.findall(r"\w+", clean_s.lower()))
        overlap = len(meaningful_tokens & s_tokens)
        if overlap > 0:
            score = overlap * 10.0 - (len(clean_s) / 250.0)
            scored.append((score, clean_s))

    if scored:
        scored.sort(key=lambda x: x[0], reverse=True)
        best_sentence = scored[0][1]
    elif raw_sentences:
        non_empty = [s.strip() for s in raw_sentences if len(s.strip()) >= 15]
        best_sentence = non_empty[0] if non_empty else text[:max_chars]
    else:
        best_sentence = text[:max_chars]

    return budget_snippet(best_sentence, max_chars=max_chars)


def crawl_page(url: str, query: str, timeout: float = CRAWL_TIMEOUT, max_bytes: int = MAX_CRAWL_BYTES, max_chars: int = 80) -> SearchResult | None:
    """Fetch external web page safely with SSRF protection and byte cap, returning a core proposition."""
    if not is_safe_url(url):
        log.debug("crawl_page rejected unsafe or private URL: %s", url)
        return None

    fetch_url = url
    if "archive.org/details/" in url:
        doc_id = url.split("archive.org/details/")[-1].split("/")[0].split("?")[0]
        if doc_id:
            fetch_url = f"https://archive.org/download/{doc_id}/{doc_id}_djvu.txt"

    try:
        req = urllib.request.Request(fetch_url, headers={"User-Agent": USER_AGENT})
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            content_type = resp.headers.get("Content-Type", "").lower()
            chunks: list[bytes] = []
            total_read = 0
            while total_read < max_bytes:
                chunk = resp.read(min(4096, max_bytes - total_read))
                if not chunk:
                    break
                chunks.append(chunk)
                total_read += len(chunk)
            raw_bytes = b"".join(chunks)

        decoded = raw_bytes.decode("utf-8", errors="ignore")
        if "text/plain" in content_type:
            clean_text = " ".join(decoded.split())
        else:
            clean_text = extract_clean_text_from_html(decoded)

        if not clean_text:
            return None

        prop = extract_relevant_proposition(clean_text, query, max_chars=max_chars)
        if prop:
            return SearchResult(prop, url=url, domain=_extract_domain(url))
    except Exception as exc:
        log.debug("crawl_page failed for %s: %s", url, exc)

    return None



def budget_snippet(snippet: str, max_chars: int = 100) -> str:
    """Format and word-boundary slice a snippet to fit within a tight context budget."""
    clean = " ".join(snippet.split())
    if not clean or len(clean) <= max_chars:
        return clean
    truncated = clean[:max_chars]
    if " " in truncated:
        truncated = truncated.rsplit(" ", 1)[0]
    return truncated.rstrip(",.;- ") + "."


def _query_duckduckgo_json(query: str, timeout: float = DEFAULT_TIMEOUT) -> list[SearchResult]:
    """Query DuckDuckGo Instant Answer JSON API for factual abstracts and entity URLs."""
    encoded = urllib.parse.quote_plus(query.strip())
    url = f"https://api.duckduckgo.com/?q={encoded}&format=json&no_html=1&skip_disambig=1"
    req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        data = json.loads(resp.read().decode("utf-8", errors="ignore"))

    snippets: list[SearchResult] = []
    abstract = (data.get("AbstractText") or data.get("Abstract") or "").strip()
    abstract_url = (data.get("AbstractURL") or "").strip()
    heading = (data.get("Heading") or "").strip()

    if abstract:
        snippets.append(SearchResult(abstract, url=abstract_url, title=heading, domain=_extract_domain(abstract_url) or "duckduckgo.com"))

    topics = data.get("RelatedTopics", [])
    for item in topics:
        if isinstance(item, dict) and item.get("Text"):
            text = item["Text"].strip()
            first_url = (item.get("FirstURL") or "").strip()
            if text and not any(text == s.snippet for s in snippets):
                snippets.append(SearchResult(text, url=first_url, domain=_extract_domain(first_url) or "duckduckgo.com"))
        elif isinstance(item, dict) and "Topics" in item:
            for sub in item.get("Topics", []):
                if isinstance(sub, dict) and sub.get("Text"):
                    text = sub["Text"].strip()
                    first_url = (sub.get("FirstURL") or "").strip()
                    if text and not any(text == s.snippet for s in snippets):
                        snippets.append(SearchResult(text, url=first_url, domain=_extract_domain(first_url) or "duckduckgo.com"))

    return snippets


def _query_wikipedia(query: str, timeout: float = DEFAULT_TIMEOUT) -> list[SearchResult]:
    """Query Wikipedia REST Search & Summary APIs for encyclopedic and classical knowledge."""
    encoded_title = urllib.parse.quote(query.strip().replace(" ", "_"))
    summary_url = f"https://en.wikipedia.org/api/rest_v1/page/summary/{encoded_title}"
    results: list[SearchResult] = []

    # 1. Direct Page Summary API
    try:
        req = urllib.request.Request(summary_url, headers={"User-Agent": WIKIPEDIA_USER_AGENT})
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            data = json.loads(resp.read().decode("utf-8", errors="ignore"))
            extract = (data.get("extract") or "").strip()
            title = (data.get("title") or "").strip()
            page_url = (data.get("content_urls", {}).get("desktop", {}).get("page") or f"https://en.wikipedia.org/wiki/{encoded_title}").strip()
            if extract:
                results.append(SearchResult(extract, url=page_url, title=title, domain="en.wikipedia.org"))
                return results
    except Exception as exc:
        log.debug("Wikipedia summary lookup failed for %s: %s", query, exc)

    # 2. Search API fallback
    try:
        search_query = urllib.parse.quote_plus(query.strip())
        search_url = f"https://en.wikipedia.org/w/api.php?action=query&list=search&srsearch={search_query}&format=json&utf8=1&srlimit=3"
        req = urllib.request.Request(search_url, headers={"User-Agent": WIKIPEDIA_USER_AGENT})
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            data = json.loads(resp.read().decode("utf-8", errors="ignore"))

        search_items = data.get("query", {}).get("search", [])
        for item in search_items:
            title = (item.get("title") or "").strip()
            raw_snippet = item.get("snippet") or ""
            clean_snippet = re.sub(r"<[^>]+>", "", raw_snippet)
            clean_snippet = html.unescape(clean_snippet).strip()
            clean_snippet = " ".join(clean_snippet.split())
            page_url = f"https://en.wikipedia.org/wiki/{urllib.parse.quote(title.replace(' ', '_'))}"
            if clean_snippet:
                results.append(SearchResult(clean_snippet, url=page_url, title=title, domain="en.wikipedia.org"))
    except Exception as exc:
        log.debug("Wikipedia search API failed for %s: %s", query, exc)

    return results


def _query_archive_org(query: str, timeout: float = DEFAULT_TIMEOUT) -> list[SearchResult]:
    """Query Internet Archive Open Search API for historical texts, manuscripts, and translations."""
    encoded_q = urllib.parse.quote_plus(query.strip())
    search_url = (
        f"https://archive.org/advancedsearch.php?q={encoded_q}"
        f"&fl[]=identifier,title,description&sort[]=&rows=3&page=1&output=json"
    )
    results: list[SearchResult] = []
    try:
        req = urllib.request.Request(search_url, headers={"User-Agent": USER_AGENT})
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            data = json.loads(resp.read().decode("utf-8", errors="ignore"))

        docs = data.get("response", {}).get("docs", [])
        for doc in docs:
            identifier = doc.get("identifier") or ""
            title = doc.get("title") or ""
            desc = doc.get("description") or ""
            if isinstance(desc, list):
                desc = " ".join(str(d) for d in desc)
            clean_desc = re.sub(r"<[^>]+>", " ", str(desc))
            clean_desc = html.unescape(clean_desc).strip()
            clean_desc = " ".join(clean_desc.split())
            item_url = f"https://archive.org/details/{identifier}" if identifier else "https://archive.org"
            if clean_desc or title:
                text = clean_desc if clean_desc else title
                results.append(SearchResult(text, url=item_url, title=str(title), domain="archive.org"))
    except Exception as exc:
        log.debug("Archive.org search failed for %s: %s", query, exc)

    return results


def _query_configurable_search(query: str, timeout: float = DEFAULT_TIMEOUT) -> list[SearchResult]:
    """Query optional external metasearch engine (e.g. SearXNG or Brave) if CHIT_SEARCH_URL is configured."""
    endpoint = os.environ.get("CHIT_SEARCH_URL")
    if not endpoint:
        return []

    encoded = urllib.parse.quote_plus(query.strip())
    delim = "&" if "?" in endpoint else "?"
    url = f"{endpoint}{delim}q={encoded}&format=json"
    results: list[SearchResult] = []
    try:
        req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            data = json.loads(resp.read().decode("utf-8", errors="ignore"))

        items = data.get("results") or []
        for item in items:
            title = (item.get("title") or "").strip()
            content = (item.get("content") or item.get("snippet") or "").strip()
            item_url = (item.get("url") or "").strip()
            if content:
                results.append(SearchResult(content, url=item_url, title=title, domain=_extract_domain(item_url)))
    except Exception as exc:
        log.debug("Configurable search failed: %s", exc)

    return results


def _query_duckduckgo_html(query: str, timeout: float = DEFAULT_TIMEOUT) -> list[SearchResult]:
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

    snippets: list[SearchResult] = []
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
            if clean_text and not any(clean_text == s.snippet for s in snippets):
                snippets.append(SearchResult(clean_text, url="https://duckduckgo.com", domain="duckduckgo.com"))

    return snippets


def search_web(query: str, max_results: int = 2, max_chars: int = 100, timeout: float = DEFAULT_TIMEOUT) -> list[SearchResult]:
    """Execute unblocked multi-tier autonomous retrieval with adaptive depth and strict bounds.

    Returns a list of SearchResult strings enriched with title, url, and domain attributes.
    Never raises an exception; returns [] on any network or parsing error.
    """
    cleaned_query = query.strip()
    if not cleaned_query:
        return []

    results: list[SearchResult] = []

    # 1. Tier 1: DuckDuckGo Instant Answer JSON API
    try:
        results = _query_duckduckgo_json(cleaned_query, timeout=timeout)
    except Exception as exc:
        log.debug("DuckDuckGo Instant Answer query failed: %s", exc)

    # Fast-path check: If Tier 1 returned an authoritative extract >= 50 chars, we have ground truth
    has_authoritative = any(len(s.snippet) >= 50 for s in results)

    # 2. Tier 2: Wikipedia REST Search & Summary API (Scholarly/Encyclopedic)
    if not has_authoritative:
        try:
            wiki_results = _query_wikipedia(cleaned_query, timeout=timeout)
            if wiki_results:
                results.extend(wiki_results)
                has_authoritative = any(len(s.snippet) >= 50 for s in results)
        except Exception as exc:
            log.debug("Wikipedia query failed: %s", exc)

    # 3. Tier 3: Internet Archive Open Search API (Archival/Literature)
    if not has_authoritative:
        try:
            archive_results = _query_archive_org(cleaned_query, timeout=timeout)
            if archive_results:
                results.extend(archive_results)
        except Exception as exc:
            log.debug("Archive.org query failed: %s", exc)

    # 4. Tier 4: Configurable metasearch provider (SearXNG / Brave)
    if not results and os.environ.get("CHIT_SEARCH_URL"):
        try:
            config_results = _query_configurable_search(cleaned_query, timeout=timeout)
            if config_results:
                results.extend(config_results)
        except Exception as exc:
            log.debug("Configurable search failed: %s", exc)

    # 5. Deep Crawl Path: If top candidate only has a URL or short snippet (< 50 chars), crawl page
    crawled_results: list[SearchResult] = []
    for cand in results[:max_results]:
        if cand.url and len(cand.snippet) < 50:
            crawled = crawl_page(cand.url, cleaned_query, timeout=CRAWL_TIMEOUT, max_chars=max_chars)
            if crawled:
                crawled_results.append(crawled)
    if crawled_results:
        results = crawled_results + results

    # 6. Fallback to DuckDuckGo HTML if results are still empty (e.g. for offline mock tests)
    if not results:
        try:
            results = _query_duckduckgo_html(cleaned_query, timeout=timeout)
        except Exception as exc:
            log.debug("DuckDuckGo HTML query fallback failed: %s", exc)

    # 7. Budget and slice top results, preserving SearchResult metadata
    budgeted: list[SearchResult] = []
    seen_texts: set[str] = set()
    for item in results:
        snippet_text = item.snippet if isinstance(item, SearchResult) else str(item)
        b = budget_snippet(snippet_text, max_chars=max_chars)
        if b and b not in seen_texts:
            seen_texts.add(b)
            if isinstance(item, SearchResult):
                budgeted.append(SearchResult(b, url=item.url, title=item.title, domain=item.domain))
            else:
                budgeted.append(SearchResult(b))
        if len(budgeted) >= max_results:
            break

    return budgeted


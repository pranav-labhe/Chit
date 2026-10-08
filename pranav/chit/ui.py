"""Single-file browser console for the Chit API.

Run both the API (8000) and this UI (8001) with:
    python -m pranav.chit.ui

The browser only talks to this module. API keys are retained in process memory,
one key per opaque browser session, and attached to server-side API requests.
"""
from __future__ import annotations

import asyncio
import contextlib
import json
import logging
import os
import re
import secrets
import threading
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Literal
from urllib.parse import urlsplit

import httpx
import uvicorn
from fastapi import FastAPI, HTTPException, Request, Response
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from fastapi.responses import HTMLResponse, PlainTextResponse
from pydantic import BaseModel, ConfigDict, Field


from . import api as chit_api

log = logging.getLogger(__name__)

API_BASE = os.environ.get("CHIT_UI_API_URL", "http://127.0.0.1:8000").rstrip("/")
UI_HOST = os.environ.get("CHIT_UI_HOST", "0.0.0.0")
UI_PORT = int(os.environ.get("CHIT_UI_PORT", "8001"))
API_PORT = int(os.environ.get("CHIT_API_PORT", "8000"))
BASE_PATH = os.environ.get("CHIT_UI_BASE_PATH", "").rstrip("/")
COOKIE_NAME = "chit_ui_session"
SESSION_TTL_SECONDS = max(60, int(os.environ.get("CHIT_UI_SESSION_TTL_SECONDS", "43200")))
UPSTREAM_TIMEOUT_SECONDS = float(os.environ.get("CHIT_UI_UPSTREAM_TIMEOUT_SECONDS", "300"))


@dataclass
class KeySession:
    api_key: str
    expires_at: float


_key_sessions: dict[str, KeySession] = {}
_key_sessions_lock = threading.Lock()


# The UI catalog intentionally mirrors every public endpoint in ChitAPIGuide.md.
# `pattern` is the only variable part accepted by the server-side proxy.
ROUTES: list[dict[str, Any]] = [
    {"category": "Health & model", "name": "Server health", "method": "GET", "path": "/health", "pattern": r"^/health$", "query": {}, "body": None},
    {"category": "Health & model", "name": "Service readiness", "method": "GET", "path": "/ready", "pattern": r"^/ready$", "query": {}, "body": None},
    {"category": "Health & model", "name": "Live model details", "method": "GET", "path": "/model", "pattern": r"^/model$", "query": {}, "body": None},
    {"category": "Generate & chat", "name": "Generate a response", "method": "POST", "path": "/generate", "pattern": r"^/generate$", "query": {}, "body": {"prompt": "Explain how memory helps Chit.", "tokens": 100, "temperature": 0}},
    {"category": "Generate & chat", "name": "Continue raw text", "method": "POST", "path": "/generate", "pattern": r"^/generate$", "query": {}, "body": {"prompt": "Chit is the", "mode": "continue", "tokens": 60, "temperature": 0}},
    {"category": "Generate & chat", "name": "Chat message", "method": "POST", "path": "/chat", "pattern": r"^/chat$", "query": {}, "body": {"message": "Hello, Chit.", "temperature": 0}},
    {"category": "Sessions", "name": "Create session", "method": "POST", "path": "/sessions", "pattern": r"^/sessions$", "query": {}, "body": None},
    {"category": "Sessions", "name": "List sessions", "method": "GET", "path": "/sessions", "pattern": r"^/sessions$", "query": {"limit": 50, "offset": 0}, "body": None},
    {"category": "Sessions", "name": "Read session", "method": "GET", "path": "/sessions/{session_id}", "pattern": r"^/sessions/[0-9a-f]{32}$", "query": {"limit": 100}, "body": None},
    {"category": "Sessions", "name": "Read facts", "method": "GET", "path": "/sessions/{session_id}/facts", "pattern": r"^/sessions/[0-9a-f]{32}/facts$", "query": {}, "body": None},
    {"category": "Sessions", "name": "Configure facts", "method": "PATCH", "path": "/sessions/{session_id}/facts", "pattern": r"^/sessions/[0-9a-f]{32}/facts$", "query": {}, "body": {"enabled": True}},
    {"category": "Sessions", "name": "Refresh facts", "method": "POST", "path": "/sessions/{session_id}/facts/refresh", "pattern": r"^/sessions/[0-9a-f]{32}/facts/refresh$", "query": {}, "body": None},
    {"category": "Sessions", "name": "Clear facts", "method": "DELETE", "path": "/sessions/{session_id}/facts", "pattern": r"^/sessions/[0-9a-f]{32}/facts$", "query": {}, "body": None, "confirm": True},
    {"category": "Sessions", "name": "Read summary", "method": "GET", "path": "/sessions/{session_id}/summary", "pattern": r"^/sessions/[0-9a-f]{32}/summary$", "query": {}, "body": None},
    {"category": "Sessions", "name": "Configure summary", "method": "PATCH", "path": "/sessions/{session_id}/summary", "pattern": r"^/sessions/[0-9a-f]{32}/summary$", "query": {}, "body": {"enabled": True}},
    {"category": "Sessions", "name": "Refresh summary", "method": "POST", "path": "/sessions/{session_id}/summary/refresh", "pattern": r"^/sessions/[0-9a-f]{32}/summary/refresh$", "query": {}, "body": None},
    {"category": "Sessions", "name": "Clear summary", "method": "DELETE", "path": "/sessions/{session_id}/summary", "pattern": r"^/sessions/[0-9a-f]{32}/summary$", "query": {}, "body": None, "confirm": True},
    {"category": "Sessions", "name": "Delete session", "method": "DELETE", "path": "/sessions/{session_id}", "pattern": r"^/sessions/[0-9a-f]{32}$", "query": {}, "body": None, "confirm": True},
    {"category": "Memory", "name": "Save a memory", "method": "POST", "path": "/memory", "pattern": r"^/memory$", "query": {}, "body": {"content": "Chit API console example memory.", "memory_type": "experience", "importance": 0.5, "tags": []}},
    {"category": "Memory", "name": "Search memories", "method": "GET", "path": "/memory/search", "pattern": r"^/memory/search$", "query": {"q": "office", "limit": 5}, "body": None},
    {"category": "Memory", "name": "Delete memory", "method": "DELETE", "path": "/memory/{memory_id}", "pattern": r"^/memory/[A-Za-z0-9_-]+$", "query": {}, "body": None, "confirm": True},
    {"category": "Training & jobs", "name": "List training presets", "method": "GET", "path": "/train/configs", "pattern": r"^/train/configs$", "query": {}, "body": None},
    {"category": "Training & jobs", "name": "Start training", "method": "POST", "path": "/train", "pattern": r"^/train$", "query": {}, "body": {"config": "chit_assistant_cpu", "init": "scratch", "promote": False, "force_promote": False}, "confirm": True},
    {"category": "Training & jobs", "name": "List training jobs", "method": "GET", "path": "/train", "pattern": r"^/train$", "query": {}, "body": None},
    {"category": "Training & jobs", "name": "Read training job", "method": "GET", "path": "/train/{job_id}", "pattern": r"^/train/[0-9a-f]{32}$", "query": {}, "body": None},
    {"category": "Training & jobs", "name": "Cancel training job", "method": "POST", "path": "/train/{job_id}/cancel", "pattern": r"^/train/[0-9a-f]{32}/cancel$", "query": {}, "body": None, "confirm": True},
    {"category": "Training & jobs", "name": "List candidates", "method": "GET", "path": "/candidates", "pattern": r"^/candidates$", "query": {}, "body": None},
    {"category": "Training & jobs", "name": "Evaluate candidate", "method": "POST", "path": "/candidates/{job_id}/evaluate", "pattern": r"^/candidates/[0-9a-f]{32}/evaluate$", "query": {}, "body": None, "confirm": True},
    {"category": "Training & jobs", "name": "Promote candidate", "method": "POST", "path": "/candidates/{job_id}/promote", "pattern": r"^/candidates/[0-9a-f]{32}/promote$", "query": {}, "body": None, "confirm": True},
    {"category": "Health & model", "name": "Rollback champion", "method": "POST", "path": "/admin/rollback", "pattern": r"^/admin/rollback$", "query": {"to_sha256": ""}, "body": None, "confirm": True},
    {"category": "Health & model", "name": "Reload champion", "method": "POST", "path": "/admin/reload", "pattern": r"^/admin/reload$", "query": {}, "body": None, "confirm": True},
    {"category": "Knowledge", "name": "Teach knowledge", "method": "POST", "path": "/knowledge", "pattern": r"^/knowledge$", "query": {}, "body": {"items": [{"kind": "qa", "question": "What is Chit?", "answer": "Chit is the neural brain of Atmini."}]}},
    {"category": "Knowledge", "name": "List knowledge", "method": "GET", "path": "/knowledge", "pattern": r"^/knowledge$", "query": {"status": "pending", "limit": 50, "offset": 0}, "body": None},
    {"category": "Knowledge", "name": "Knowledge statistics", "method": "GET", "path": "/knowledge/stats", "pattern": r"^/knowledge/stats$", "query": {}, "body": None},
    {"category": "Knowledge", "name": "Read knowledge entry", "method": "GET", "path": "/knowledge/{entry_id}", "pattern": r"^/knowledge/[A-Za-z0-9_-]+$", "query": {}, "body": None},
    {"category": "Knowledge", "name": "Delete knowledge entry", "method": "DELETE", "path": "/knowledge/{entry_id}", "pattern": r"^/knowledge/[A-Za-z0-9_-]+$", "query": {}, "body": None, "confirm": True},
    {"category": "Knowledge", "name": "Train on knowledge", "method": "POST", "path": "/knowledge/train", "pattern": r"^/knowledge/train$", "query": {}, "body": {"config": "chit_assistant_cpu", "repeat": 3}, "confirm": True},
    {"category": "Training data", "name": "Inspect training data", "method": "GET", "path": "/data", "pattern": r"^/data$", "query": {"config": "chit_assistant_cpu"}, "body": None},
    {"category": "Training data", "name": "Split corpus file", "method": "POST", "path": "/data/split", "pattern": r"^/data/split$", "query": {}, "body": {"source": "corpus.txt", "config": "chit_assistant_cpu", "by": "paragraph", "eval_fraction": 0.1, "dry_run": True}, "confirm": True},
]


def _route_allowed(method: str, path: str) -> bool:
    if not path.startswith("/") or "?" in path or "#" in path or "\\" in path or ".." in path:
        return False
    return any(route["method"] == method and re.fullmatch(route["pattern"], path) for route in ROUTES)


class LoginRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    api_key: str = Field(min_length=1, max_length=4096)


class ProxyRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    method: Literal["GET", "POST", "DELETE"]
    path: str = Field(min_length=1, max_length=256)
    query: dict[str, Any] = Field(default_factory=dict)
    body: Any = None


@contextlib.asynccontextmanager
async def _ui_lifespan(_: FastAPI):
    """Reuse one connection pool for UI-to-API requests."""
    app.state.api_client = httpx.AsyncClient(
        timeout=UPSTREAM_TIMEOUT_SECONDS, follow_redirects=False
    )
    try:
        yield
    finally:
        await app.state.api_client.aclose()


app = FastAPI(title="Chit Browser Console", docs_url=None, redoc_url=None, openapi_url=None, lifespan=_ui_lifespan)

# Asset serving
_UI_DIR = Path(__file__).resolve().parent / "ui"
app.mount("/static", StaticFiles(directory=str(_UI_DIR / "static")), name="static")
templates = Jinja2Templates(directory=str(_UI_DIR / "templates"))



@app.middleware("http")
async def accept_console_prefix(request: Request, call_next):
    """Accept requests whether the reverse proxy strips BASE_PATH or preserves it."""
    prefix = BASE_PATH
    path = request.scope["path"]
    if prefix and (path == prefix or path.startswith(prefix + "/")):
        stripped = path[len(prefix):] or "/"
        request.scope["path"] = stripped
        raw_path = request.scope.get("raw_path")
        raw_prefix = prefix.encode("ascii", errors="ignore")
        if raw_path and raw_path.startswith(raw_prefix):
            request.scope["raw_path"] = raw_path[len(raw_prefix):] or b"/"
    return await call_next(request)


def _page(templates: Jinja2Templates, request: Request) -> HTMLResponse:
    route_data = json.dumps([
        {key: value for key, value in route.items() if key != "pattern"}
        for route in ROUTES
    ], ensure_ascii=False).replace("</", "<\\/")
    return templates.TemplateResponse(
        request=request,
        name="index.html", 
        context={
            "base_path": BASE_PATH,
            "routes": json.loads(route_data)
        }
    )



@app.get("/")
async def index(request: Request):
    return _page(templates, request)


@app.get("/_ui/api-guide", response_class=PlainTextResponse)
async def api_guide():
    """Serve the maintained plain-English API guide inside the console."""
    repository_root = Path(__file__).resolve().parents[2]
    guide_path = repository_root / "ChitAPIGuide.md"
    if not guide_path.is_file():
        guide_path = repository_root / "docs" / "ChitAPIGuide.md"
    if not guide_path.is_file():
        raise HTTPException(status_code=404, detail="The plain-English API guide is not installed.")
    return PlainTextResponse(guide_path.read_text(encoding="utf-8"), headers={"Cache-Control": "no-store"})


async def _get_key_session(request: Request) -> tuple[str, KeySession] | None:
    sid = request.cookies.get(COOKIE_NAME)
    if not sid:
        return None
    now = time.monotonic()
    with _key_sessions_lock:
        for expired_id in [key for key, value in _key_sessions.items() if value.expires_at <= now]:
            _key_sessions.pop(expired_id, None)
        item = _key_sessions.get(sid)
        if item is None:
            return None
        item.expires_at = now + SESSION_TTL_SECONDS
        return sid, item


@app.get("/_ui/session")
async def session_status(request: Request):
    session = await _get_key_session(request)
    return {"authenticated": session is not None}

@app.get("/_ui/session/title")
async def get_session_title(request: Request, session_id: str):
    session = await _get_key_session(request)
    if not session:
        raise HTTPException(status_code=401, detail="Authentication required")
    
    try:
        # Use the proxy logic to call the actual /sessions/{id} endpoint
        async with _new_http_client() as client:
            headers = {"X-API-Key": session[1].api_key}
            response = await client.get(f"{API_BASE}/sessions/{session_id}", headers=headers)
            if response.status_code != 200:
                raise HTTPException(status_code=response.status_code, detail="Session not found")
            
            data = response.json()
            # Use the existing summary if available, otherwise the first message
            title = data.get("summary")
            if not title and data.get("messages"):
                first_msg = data["messages"][0]["content"]
                title = (first_msg[:50] + "...") if len(first_msg) > 50 else first_msg
            
            return {"title": title or "New Conversation"}
    except HTTPException:
        raise
    except httpx.TimeoutException as e:
        log.error("UI helper request timed out: %s", e)
        raise HTTPException(status_code=504, detail="The Chit API did not respond before the UI timeout.")
    except httpx.HTTPError as e:
        log.error(f"Error generating session title: {e}")
        raise HTTPException(status_code=502, detail="The Chit API could not be reached from the UI server.")

@app.get("/_ui/memories")
async def get_ui_memories(request: Request, q: str = ""):
    session = await _get_key_session(request)
    if not session:
        raise HTTPException(status_code=401, detail="Authentication required")
    
    try:
        async with _new_http_client() as client:
            params = {"q": q, "limit": 50}
            response = await client.get(f"{API_BASE}/memory/search", params=params, headers={"X-API-Key": session[1].api_key})
            if response.status_code != 200:
                raise HTTPException(status_code=response.status_code, detail="Memory store unreachable")
            
            return response.json()
    except HTTPException:
        raise
    except httpx.TimeoutException as e:
        log.error("UI helper request timed out: %s", e)
        raise HTTPException(status_code=504, detail="The Chit API did not respond before the UI timeout.")
    except httpx.HTTPError as e:
        log.error(f"Error fetching memories: {e}")
        raise HTTPException(status_code=502, detail="The Chit API could not be reached from the UI server.")

@app.get("/_ui/knowledge/stats")
async def get_ui_knowledge_stats(request: Request):
    session = await _get_key_session(request)
    if not session:
        raise HTTPException(status_code=401, detail="Authentication required")
    
    try:
        async with _new_http_client() as client:
            response = await client.get(f"{API_BASE}/knowledge/stats", headers={"X-API-Key": session[1].api_key})
            if response.status_code != 200:
                raise HTTPException(status_code=response.status_code, detail="Knowledge store unreachable")
            return response.json()
    except HTTPException:
        raise
    except httpx.TimeoutException as e:
        log.error("UI helper request timed out: %s", e)
        raise HTTPException(status_code=504, detail="The Chit API did not respond before the UI timeout.")
    except httpx.HTTPError as e:
        log.error(f"Error fetching knowledge stats: {e}")
        raise HTTPException(status_code=502, detail="The Chit API could not be reached from the UI server.")

@app.get("/_ui/train/status")
async def get_ui_train_status(request: Request):
    session = await _get_key_session(request)
    if not session:
        raise HTTPException(status_code=401, detail="Authentication required")
    
    try:
        async with _new_http_client() as client:
            # Check /health first to see if a job is running
            health = await client.get(f"{API_BASE}/health")
            health_data = health.json()
            job_id = health_data.get("training_job")
            
            if not job_id:
                return {"state": "idle", "progress": 0, "job_id": None}
            
            # Get detailed job status
            job_res = await client.get(f"{API_BASE}/train/{job_id}", headers={"X-API-Key": session[1].api_key})
            if job_res.status_code != 200:
                return {"state": "unknown", "progress": 0, "job_id": job_id}
            
            job_data = job_res.json()
            return {
                "state": job_data.get("state"),
                "progress": job_data.get("progress", 0),
                "job_id": job_id,
                "step": job_data.get("step"),
                "max_steps": job_data.get("max_steps")
            }
    except HTTPException:
        raise
    except httpx.TimeoutException as e:
        log.error("UI helper request timed out: %s", e)
        raise HTTPException(status_code=504, detail="The Chit API did not respond before the UI timeout.")
    except httpx.HTTPError as e:
        log.error(f"Error fetching train status: {e}")
        raise HTTPException(status_code=502, detail="The Chit API could not be reached from the UI server.")

@app.get("/_ui/train/configs")
async def get_ui_train_configs(request: Request):
    session = await _get_key_session(request)
    if not session:
        raise HTTPException(status_code=401, detail="Authentication required")
    
    try:
        async with _new_http_client() as client:
            response = await client.get(f"{API_BASE}/train/configs", headers={"X-API-Key": session[1].api_key})
            if response.status_code != 200:
                raise HTTPException(status_code=response.status_code, detail="Config store unreachable")
            return response.json()
    except HTTPException:
        raise
    except httpx.TimeoutException as e:
        log.error("UI helper request timed out: %s", e)
        raise HTTPException(status_code=504, detail="The Chit API did not respond before the UI timeout.")
    except httpx.HTTPError as e:
        log.error(f"Error fetching configs: {e}")
        raise HTTPException(status_code=502, detail="The Chit API could not be reached from the UI server.")


@app.get("/_ui/train/configs/{config_name}")
async def get_ui_train_config_details(config_name: str, request: Request):
    """Read one allowlisted training preset so the console can explain its settings."""
    session = await _get_key_session(request)
    if not session:
        raise HTTPException(status_code=401, detail="Authentication required")
    if not re.fullmatch(r"[A-Za-z0-9_-]{1,64}", config_name):
        raise HTTPException(status_code=404, detail="Learning plan not found")
    config_root = Path(chit_api.CONFIG_DIR).resolve()
    config_path = (config_root / f"{config_name}.json").resolve()
    if config_path.parent != config_root or not config_path.is_file():
        raise HTTPException(status_code=404, detail="Learning plan not found")
    try:
        with config_path.open("r", encoding="utf-8") as source:
            config = json.load(source)
    except (OSError, json.JSONDecodeError) as error:
        log.warning("Could not read learning plan %s: %s", config_name, error)
        raise HTTPException(status_code=500, detail="Could not read this learning plan")
    return {"name": config_name, "config": config}

@app.post("/_ui/train")
async def post_ui_train(request: Request, payload: dict):
    session = await _get_key_session(request)
    if not session:
        raise HTTPException(status_code=401, detail="Authentication required")
    
    try:
        async with _new_http_client() as client:
            response = await client.post(f"{API_BASE}/train", json=payload, headers={"X-API-Key": session[1].api_key})
            if response.status_code != 202:
                raise HTTPException(status_code=response.status_code, detail=response.text)
            return response.json()
    except HTTPException:
        raise
    except httpx.TimeoutException as e:
        log.error("UI helper request timed out: %s", e)
        raise HTTPException(status_code=504, detail="The Chit API did not respond before the UI timeout.")
    except httpx.HTTPError as e:
        log.error(f"Error starting training: {e}")
        raise HTTPException(status_code=502, detail="The Chit API could not be reached from the UI server.")

@app.get("/_ui/train/jobs")
async def get_ui_train_jobs(request: Request):
    session = await _get_key_session(request)
    if not session:
        raise HTTPException(status_code=401, detail="Authentication required")
    
    try:
        async with _new_http_client() as client:
            response = await client.get(f"{API_BASE}/train", headers={"X-API-Key": session[1].api_key})
            if response.status_code != 200:
                raise HTTPException(status_code=response.status_code, detail="Jobs store unreachable")
            return response.json()
    except HTTPException:
        raise
    except httpx.TimeoutException as e:
        log.error("UI helper request timed out: %s", e)
        raise HTTPException(status_code=504, detail="The Chit API did not respond before the UI timeout.")
    except httpx.HTTPError as e:
        log.error(f"Error fetching jobs: {e}")
        raise HTTPException(status_code=502, detail="The Chit API could not be reached from the UI server.")

@app.post("/_ui/login")
async def login(payload: LoginRequest, request: Request, response: Response):
    _check_origin(request)
    configured_key = chit_api.API_KEY
    if not configured_key:
        raise HTTPException(status_code=503, detail="The UI requires CHIT_API_KEY to be configured on the server.")
    if not secrets.compare_digest(payload.api_key, configured_key):
        raise HTTPException(status_code=401, detail="Invalid API key.")
    session_id = secrets.token_urlsafe(32)
    with _key_sessions_lock:
        _key_sessions[session_id] = KeySession(payload.api_key, time.monotonic() + SESSION_TTL_SECONDS)
    response.set_cookie(
        COOKIE_NAME, session_id, httponly=True, secure=request.url.scheme == "https",
        samesite="strict", max_age=SESSION_TTL_SECONDS,
        path=BASE_PATH or "/",
    )
    return {"authenticated": True}


@app.post("/_ui/logout", status_code=204)
async def logout(request: Request, response: Response):
    _check_origin(request)
    session = await _get_key_session(request)
    if session:
        with _key_sessions_lock:
            _key_sessions.pop(session[0], None)
    response.delete_cookie(COOKIE_NAME, path=BASE_PATH or "/", secure=request.url.scheme == "https",
                           httponly=True, samesite="strict")
    response.status_code = 204
    return response


def _check_origin(request: Request) -> None:
    origin = request.headers.get("origin")
    if not origin:
        return

    parsed_origin = urlsplit(origin)
    forwarded_scheme = request.headers.get("x-forwarded-proto", "").split(",", 1)[0].strip().lower()
    forwarded_host = request.headers.get("x-forwarded-host", "").split(",", 1)[0].strip()
    expected_scheme = forwarded_scheme or request.url.scheme
    expected_authority = forwarded_host or request.headers.get("host", "")

    def authority(value: str, scheme: str) -> tuple[str, int] | None:
        parsed = urlsplit(f"//{value}")
        try:
            port = parsed.port or (443 if scheme == "https" else 80)
        except ValueError:
            return None
        if not parsed.hostname or parsed.username or parsed.password:
            return None
        return parsed.hostname.rstrip(".").casefold(), port

    if (
        parsed_origin.scheme not in {"http", "https"}
        or parsed_origin.path not in {"", "/"}
        or parsed_origin.query
        or parsed_origin.fragment
        or parsed_origin.scheme != expected_scheme
        or authority(parsed_origin.netloc, parsed_origin.scheme) != authority(expected_authority, expected_scheme)
    ):
        raise HTTPException(status_code=403, detail="Cross-origin UI requests are not allowed.")


@app.post("/_ui/proxy")
async def proxy(payload: ProxyRequest, request: Request):
    _check_origin(request)
    session = await _get_key_session(request)
    if not session:
        raise HTTPException(status_code=401, detail="Enter the API key to continue.")
    path = "/" + payload.path.lstrip("/")
    if not _route_allowed(payload.method, path):
        raise HTTPException(status_code=404, detail="This method and path are not in the documented Chit API.")
    try:
        async with _new_http_client() as client:
            kwargs: dict[str, Any] = {
                "params": payload.query,
                "headers": {"X-API-Key": session[1].api_key},
            }
            if payload.method != "GET" and payload.body is not None:
                kwargs["json"] = payload.body
            upstream = await client.request(payload.method, f"{API_BASE}{path}", **kwargs)
    except httpx.TimeoutException:
        raise HTTPException(status_code=504, detail="The Chit API did not respond before the UI timeout.")
    except httpx.HTTPError as error:
        log.warning("Chit UI API proxy failed: %s", error)
        raise HTTPException(status_code=502, detail="The Chit API could not be reached from the UI server.")
    headers = {}
    if content_type := upstream.headers.get("content-type"):
        headers["content-type"] = content_type
    headers["cache-control"] = "no-store"
    return Response(content=upstream.content, status_code=upstream.status_code, headers=headers)


@contextlib.asynccontextmanager
async def _new_http_client():
    """Borrow the app's pooled client without closing it after one request."""
    yield app.state.api_client


class NoSignalServer(uvicorn.Server):
    """The API server owns process signals; the UI exits when it exits."""

    @contextlib.contextmanager
    def capture_signals(self):
        yield


async def serve() -> None:
    api_server = uvicorn.Server(uvicorn.Config(chit_api.app, host="0.0.0.0", port=API_PORT, workers=1))
    ui_server = NoSignalServer(uvicorn.Config(app, host=UI_HOST, port=UI_PORT, workers=1))
    api_task = asyncio.create_task(api_server.serve(), name="chit-api")
    ui_task = asyncio.create_task(ui_server.serve(), name="chit-ui")
    try:
        done, pending = await asyncio.wait({api_task, ui_task}, return_when=asyncio.FIRST_COMPLETED)
        for task in pending:
            if task is api_task:
                api_server.should_exit = True
            else:
                ui_server.should_exit = True
        await asyncio.gather(*pending, return_exceptions=True)
        for task in done:
            error = task.exception()
            if error:
                raise error
            if task.cancelled():
                continue
            if task is api_task:
                log.info("Chit API stopped; stopping UI server")
            else:
                log.error("Chit UI stopped; stopping API server")
    finally:
        api_server.should_exit = True
        ui_server.should_exit = True
        for task in (api_task, ui_task):
            if not task.done():
                task.cancel()
        await asyncio.gather(api_task, ui_task, return_exceptions=True)


if __name__ == "__main__":
    logging.basicConfig(level=os.environ.get("LOG_LEVEL", "INFO"))
    asyncio.run(serve())

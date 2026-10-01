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
from typing import Any, Literal
from urllib.parse import urlsplit

import httpx
import uvicorn
from fastapi import FastAPI, HTTPException, Request, Response
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
    {"category": "Health & model", "name": "Live model details", "method": "GET", "path": "/model", "pattern": r"^/model$", "query": {}, "body": None},
    {"category": "Generate & chat", "name": "Generate a response", "method": "POST", "path": "/generate", "pattern": r"^/generate$", "query": {}, "body": {"prompt": "Explain how memory helps Chit.", "tokens": 100, "temperature": 0}},
    {"category": "Generate & chat", "name": "Continue raw text", "method": "POST", "path": "/generate", "pattern": r"^/generate$", "query": {}, "body": {"prompt": "Chit is the", "mode": "continue", "tokens": 60, "temperature": 0}},
    {"category": "Generate & chat", "name": "Chat message", "method": "POST", "path": "/chat", "pattern": r"^/chat$", "query": {}, "body": {"message": "Hello, Chit.", "temperature": 0}},
    {"category": "Sessions", "name": "Create session", "method": "POST", "path": "/sessions", "pattern": r"^/sessions$", "query": {}, "body": None},
    {"category": "Sessions", "name": "List sessions", "method": "GET", "path": "/sessions", "pattern": r"^/sessions$", "query": {"limit": 50, "offset": 0}, "body": None},
    {"category": "Sessions", "name": "Read session", "method": "GET", "path": "/sessions/{session_id}", "pattern": r"^/sessions/[0-9a-f]{32}$", "query": {"limit": 100}, "body": None},
    {"category": "Sessions", "name": "Delete session", "method": "DELETE", "path": "/sessions/{session_id}", "pattern": r"^/sessions/[0-9a-f]{32}$", "query": {}, "body": None, "confirm": True},
    {"category": "Memory", "name": "Save a memory", "method": "POST", "path": "/memory", "pattern": r"^/memory$", "query": {}, "body": {"content": "Chit API console example memory.", "memory_type": "experience", "importance": 0.5, "tags": []}},
    {"category": "Memory", "name": "Search memories", "method": "GET", "path": "/memory/search", "pattern": r"^/memory/search$", "query": {"q": "office", "limit": 5}, "body": None},
    {"category": "Memory", "name": "Delete memory", "method": "DELETE", "path": "/memory/{memory_id}", "pattern": r"^/memory/[A-Za-z0-9_-]+$", "query": {}, "body": None, "confirm": True},
    {"category": "Training & jobs", "name": "List training presets", "method": "GET", "path": "/train/configs", "pattern": r"^/train/configs$", "query": {}, "body": None},
    {"category": "Training & jobs", "name": "Start training", "method": "POST", "path": "/train", "pattern": r"^/train$", "query": {}, "body": {"config": "chit_assistant_cpu", "init": "scratch"}, "confirm": True},
    {"category": "Training & jobs", "name": "List training jobs", "method": "GET", "path": "/train", "pattern": r"^/train$", "query": {}, "body": None},
    {"category": "Training & jobs", "name": "Read training job", "method": "GET", "path": "/train/{job_id}", "pattern": r"^/train/[0-9a-f]{32}$", "query": {}, "body": None},
    {"category": "Training & jobs", "name": "Cancel training job", "method": "POST", "path": "/train/{job_id}/cancel", "pattern": r"^/train/[0-9a-f]{32}/cancel$", "query": {}, "body": None, "confirm": True},
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


app = FastAPI(title="Chit Browser Console", docs_url=None, redoc_url=None, openapi_url=None)


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


def _page() -> str:
    route_data = json.dumps([
        {key: value for key, value in route.items() if key != "pattern"}
        for route in ROUTES
    ], ensure_ascii=False).replace("</", "<\\/")
    base = json.dumps(BASE_PATH)
    return _HTML.replace("__ROUTES__", route_data).replace("__BASE_PATH__", base)


@app.get("/")
async def index():
    return Response(_page(), media_type="text/html; charset=utf-8", headers={
        "Cache-Control": "no-store",
        "Content-Security-Policy": "default-src 'none'; script-src 'unsafe-inline'; style-src 'unsafe-inline'; "
                                  "connect-src 'self'; base-uri 'none'; form-action 'self'; frame-ancestors 'none'",
        "X-Content-Type-Options": "nosniff",
        "Referrer-Policy": "no-referrer",
    })


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


def _new_http_client() -> httpx.AsyncClient:
    return httpx.AsyncClient(timeout=UPSTREAM_TIMEOUT_SECONDS, follow_redirects=False)


_HTML = r'''<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<meta name="color-scheme" content="dark light"><title>Chit Console</title>
<style>
:root{font-family:Inter,ui-sans-serif,system-ui,-apple-system,"Segoe UI",sans-serif;color:#e9edf5;background:#0c111b;font-synthesis:none;--panel:#131c2a;--line:#283449;--muted:#99a8bd;--accent:#9cddc4;--red:#f6a49c}*{box-sizing:border-box}body{margin:0;min-height:100vh;background:radial-gradient(ellipse at 10% -10%,#233a42 0,transparent 38%),#0c111b}button,input,textarea,select{font:inherit}button{cursor:pointer}.shell{max-width:1420px;margin:auto;padding:28px 24px 60px}.top{display:flex;align-items:center;justify-content:space-between;gap:20px;margin-bottom:22px}.brand{display:flex;align-items:center;gap:13px}.mark{width:44px;height:44px;border-radius:15px;display:grid;place-items:center;background:#a2e0c6;color:#0b1917;font-weight:800;font-size:20px}.brand h1{font-size:19px;margin:0}.brand p{margin:3px 0 0;color:var(--muted);font-size:13px}.badge{border:1px solid var(--line);border-radius:999px;padding:7px 11px;color:var(--muted);font-size:12px}.layout{display:grid;grid-template-columns:230px minmax(0,1fr);gap:18px}.nav,.card{background:color-mix(in srgb,var(--panel) 94%,transparent);border:1px solid var(--line);border-radius:18px}.nav{padding:14px;height:max-content;position:sticky;top:16px}.nav button{display:flex;width:100%;text-align:left;padding:10px 11px;margin:3px 0;border:0;border-radius:10px;background:transparent;color:#b9c5d6}.nav button:hover,.nav button.active{background:#243448;color:#f4f7fb}.nav small{display:block;margin:15px 8px 5px;color:#7f8da2;text-transform:uppercase;letter-spacing:.1em;font-size:10px}.main{min-width:0}.card{padding:21px;margin-bottom:16px}.card h2{font-size:17px;margin:0 0 5px}.sub{font-size:13px;color:var(--muted);margin:0 0 17px}.hidden{display:none!important}.grid{display:grid;grid-template-columns:repeat(2,minmax(0,1fr));gap:13px}.field{display:flex;flex-direction:column;gap:7px;margin:10px 0}.field label{font-size:12px;color:#bec9d8}.field input,.field textarea,.field select{width:100%;border:1px solid #34435a;border-radius:10px;background:#0e1622;color:#e9edf5;padding:10px 11px;outline:none}.field input:focus,.field textarea:focus,.field select:focus{border-color:#8acdb2}.field textarea{min-height:150px;resize:vertical;font:12px/1.5 ui-monospace,SFMono-Regular,Consolas,monospace}.smallarea textarea{min-height:70px}.actions{display:flex;gap:9px;align-items:center;flex-wrap:wrap;margin-top:12px}.primary,.secondary,.danger{border:0;border-radius:10px;padding:10px 15px;font-weight:650}.primary{background:#9cddc4;color:#0d201a}.secondary{background:#26364a;color:#e3eaf4}.danger{background:#4a252a;color:#ffd7d2}.notice{padding:10px 12px;border-radius:10px;background:#1d2c3b;color:#b8c7d8;font-size:13px}.notice.error{background:#43272a;color:#ffc3bc}.chatlog{display:flex;flex-direction:column;gap:11px;max-height:460px;overflow:auto;margin:16px 0}.bubble{max-width:88%;padding:12px 14px;border-radius:14px;white-space:pre-wrap;overflow-wrap:anywhere;line-height:1.55;font-size:14px}.bubble.user{align-self:flex-end;background:#294337}.bubble.chit{align-self:flex-start;background:#1d2a3a}.bubble.system{align-self:center;background:#292b35;color:var(--muted);font-size:12px}.bubble pre{white-space:pre-wrap}.result{max-height:480px;overflow:auto;border-radius:12px;padding:14px;background:#0a1019;border:1px solid #263247;white-space:pre-wrap;overflow-wrap:anywhere;font:12px/1.55 ui-monospace,SFMono-Regular,Consolas,monospace}.status{color:var(--muted);font-size:12px}.endpoint-list{display:grid;grid-template-columns:repeat(auto-fill,minmax(220px,1fr));gap:8px;margin:14px 0}.endpoint{background:#111a27;border:1px solid var(--line);border-radius:10px;padding:10px;color:#e4eaf2;text-align:left}.endpoint:hover{border-color:#8acdb2}.endpoint b{display:block;font-size:12px}.endpoint span{font:11px ui-monospace,monospace;color:#9fadc0}.method{display:inline-block;font-size:10px;font-weight:750;padding:3px 5px;border-radius:5px;background:#253349;color:#b8d9cb;margin-right:5px}.overlay{position:fixed;inset:0;background:#070b12eF;display:grid;place-items:center;padding:20px;z-index:5}.login{max-width:440px;width:100%;padding:26px;background:#151f2d;border:1px solid #34445a;border-radius:18px;box-shadow:0 20px 80px #0008}.login h2{margin:0 0 8px}.login p{color:#aebbd0;font-size:13px;line-height:1.55}.footer{font-size:11px;color:#7f8da2;margin-top:14px}@media(max-width:800px){.shell{padding:18px 12px 40px}.layout{grid-template-columns:1fr}.nav{position:static;display:flex;overflow:auto;gap:4px}.nav small{display:none}.nav button{white-space:nowrap;width:auto}.grid{grid-template-columns:1fr}.top{align-items:flex-start}.badge{display:none}}
</style></head>
<body><div class="shell"><header class="top"><div class="brand"><div class="mark">चित् </div><div><h1>चित्त · Chit Console</h1><p>Browser console for the Chit API</p></div></div><div class="badge" id="connection">Checking server…</div></header>
<div class="layout"><nav class="nav" aria-label="Console sections"><small>Workspace</small><button class="active" data-view="chat">Chat</button><button data-view="generate">Generate</button><small>API tools</small><button data-view="explorer">All API routes</button><button id="logout" class="hidden">Lock console</button></nav>
<main class="main">
<section class="view" id="view-chat"><div class="card"><h2>Talk with Chit</h2><p class="sub">A continuing conversation uses the API’s saved session and memory context.</p><div class="field smallarea"><label for="chatInput">Your message (Markdown is supported)</label><textarea id="chatInput" placeholder="What would you like to work through?"></textarea></div><div class="actions"><button class="primary" id="sendChat">Send message</button><button class="secondary" id="newChat">New conversation</button><span class="status" id="chatSession"></span></div><div class="chatlog" id="chatlog" aria-live="polite"></div></div></section>
<section class="view hidden" id="view-generate"><div class="card"><h2>Generate</h2><p class="sub">Ask Chit for a one-shot response or continue a raw text prefix.</p><div class="field"><label for="genPrompt">Prompt / request</label><textarea id="genPrompt" placeholder="Write an explanation, solve a problem, or create something…"></textarea></div><div class="grid"><div class="field"><label for="genMode">Mode</label><select id="genMode"><option value="assistant">Assistant request (uses memory)</option><option value="continue">Raw text continuation</option></select></div><div class="field"><label for="genTokens">Maximum new tokens (1–500)</label><input type="number" id="genTokens" min="1" max="500" value="160"></div><div class="field"><label for="genTemp">Temperature (0–2)</label><input type="number" id="genTemp" min="0" max="2" step="0.1" value="0.4"></div><div class="field"><label for="genTopK">Top K (1–256)</label><input type="number" id="genTopK" min="1" max="256" value="50"></div></div><div class="field smallarea"><label for="genStop">Optional stop strings (JSON array)</label><textarea id="genStop">[]</textarea></div><div class="actions"><button class="primary" id="runGenerate">Generate</button><span class="status" id="genStatus"></span></div><h3>Response</h3><pre class="result" id="genResult">Your response will appear here.</pre></div></section>
<section class="view hidden" id="view-explorer"><div class="card"><h2>Documented API routes</h2><p class="sub">Choose a route to load its example. Replace path IDs and request values as needed. Changes such as delete, training, cancellation, and file splitting ask for confirmation.</p><div class="endpoint-list" id="endpointList"></div><div class="grid"><div class="field"><label for="apiMethod">Method</label><select id="apiMethod"><option>GET</option><option>POST</option><option>DELETE</option></select></div><div class="field"><label for="apiPath">API path</label><input id="apiPath" spellcheck="false"></div></div><div class="field smallarea"><label for="apiQuery">Query parameters (JSON object)</label><textarea id="apiQuery">{}</textarea></div><div class="field"><label for="apiBody">Request body (JSON; ignored for GET)</label><textarea id="apiBody">null</textarea></div><div class="actions"><button class="primary" id="runApi">Send API request</button><span class="status" id="apiStatus"></span></div><h3>API response</h3><pre class="result" id="apiResult">Choose a route above.</pre></div></section>
</main></div><p class="footer">The API key stays on the server after sign-in. This browser receives only a short-lived HttpOnly session cookie.</p></div>
<div class="overlay" id="loginOverlay"><form class="login" id="loginForm"><div class="mark">चित् </div><h2>Unlock Chit Console</h2><p>Enter the Chit API key. The server will retain it for this browser session and use it for API calls.</p><div class="field"><label for="apiKey">API key</label><input type="password" id="apiKey" autocomplete="current-password" required></div><div class="actions"><button class="primary" type="submit">Continue</button><span class="status" id="loginStatus"></span></div><p class="footer">Use this page over HTTPS when accessing it outside your own computer.</p></form></div>
<script>
const BASE=__BASE_PATH__, ROUTES=__ROUTES__;
const $=s=>document.querySelector(s), esc=s=>String(s??''); let chatId=null;
async function req(path,options={}){const r=await fetch(BASE+path,{credentials:'same-origin',...options});let data=null;const txt=await r.text();try{data=txt?JSON.parse(txt):null}catch{data=txt}if(r.status===401&&path!='/_ui/login'){lock();throw new Error('Console session expired. Enter the API key again.')}return {ok:r.ok,status:r.status,data}}
function pretty(x){return typeof x==='string'?x:JSON.stringify(x,null,2)}
function setLogin(auth){$('#loginOverlay').classList.toggle('hidden',auth);$('#logout').classList.toggle('hidden',!auth)}
function showError(el,e){el.textContent=e.message||String(e);el.classList.add('error')}
async function lock(){setLogin(false);$('#apiKey').value='';chatId=null;$('#chatSession').textContent=''}
async function checkSession(){try{const r=await req('/_ui/session');setLogin(!!r.data?.authenticated);$('#connection').textContent=r.data?.authenticated?'Key held for this browser session':'Sign in required';if(r.data?.authenticated)await refreshHealth()}catch(e){$('#connection').textContent=e.message}}
async function refreshHealth(){try{const r=await callApi('GET','/health',{},null);$('#connection').textContent='API · '+(r.data?.status||r.status)}catch(e){$('#connection').textContent='API unavailable'}}
$('#loginForm').addEventListener('submit',async e=>{e.preventDefault();const status=$('#loginStatus');status.textContent='Checking…';status.classList.remove('error');const key=$('#apiKey').value;try{const r=await req('/_ui/login',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({api_key:key})});$('#apiKey').value='';if(!r.ok)throw new Error(r.data?.detail||'Could not sign in.');setLogin(true);$('#connection').textContent='Key held for this browser session';await refreshHealth()}catch(err){status.textContent=err.message;status.classList.add('error')}});
$('#logout').addEventListener('click',async()=>{try{await req('/_ui/logout',{method:'POST',headers:{'Content-Type':'application/json'},body:'{}'})}finally{await lock();$('#connection').textContent='Signed out'}});
async function callApi(method,path,query,body){const r=await req('/_ui/proxy',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({method,path,query,body})});return r}
document.querySelectorAll('.nav button[data-view]').forEach(b=>b.addEventListener('click',()=>{document.querySelectorAll('.nav button[data-view]').forEach(x=>x.classList.toggle('active',x===b));document.querySelectorAll('.view').forEach(v=>v.classList.toggle('hidden',v.id!=='view-'+b.dataset.view))}));
function addBubble(role,text){const b=document.createElement('div');b.className='bubble '+role;b.textContent=text;$('#chatlog').appendChild(b);$('#chatlog').scrollTop=$('#chatlog').scrollHeight}
$('#sendChat').addEventListener('click',async()=>{const box=$('#chatInput'),message=box.value.trim();if(!message)return;addBubble('user',message);box.value='';$('#sendChat').disabled=true;try{const r=await callApi('POST','/chat',{}, {message,session_id:chatId,temperature:0.4});if(!r.ok)throw new Error(r.data?.detail?pretty(r.data.detail):'Request failed ('+r.status+')');chatId=r.data.session_id;$('#chatSession').textContent=chatId?'Session '+chatId:'No saved session';addBubble('chit',r.data.text||'')}catch(e){addBubble('system',e.message)}finally{$('#sendChat').disabled=false}});
$('#chatInput').addEventListener('keydown',e=>{if(e.key==='Enter'&&!e.shiftKey){e.preventDefault();$('#sendChat').click()}});
$('#newChat').addEventListener('click',()=>{chatId=null;$('#chatlog').replaceChildren();$('#chatSession').textContent='New conversation'});
$('#runGenerate').addEventListener('click',async()=>{const status=$('#genStatus');status.textContent='Generating…';status.classList.remove('error');try{let stop=JSON.parse($('#genStop').value||'[]');if(!Array.isArray(stop))throw new Error('Stop strings must be a JSON array.');const body={prompt:$('#genPrompt').value,mode:$('#genMode').value,tokens:Number($('#genTokens').value),temperature:Number($('#genTemp').value),top_k:Number($('#genTopK').value),stop};const r=await callApi('POST','/generate',{},body);$('#genResult').textContent=pretty(r.data);if(!r.ok)throw new Error('API returned '+r.status);status.textContent='Complete'}catch(e){status.textContent=e.message;status.classList.add('error')}});
const list=$('#endpointList');let selected=null;ROUTES.forEach((route,i)=>{const b=document.createElement('button');b.className='endpoint';b.innerHTML='<b><i class="method">'+route.method+'</i>'+route.name+'</b><span>'+route.path+'</span>';b.title=route.category;b.addEventListener('click',()=>selectRoute(i));list.appendChild(b)});
function selectRoute(i){selected=ROUTES[i];$('#apiMethod').value=selected.method;$('#apiPath').value=selected.path;$('#apiQuery').value=JSON.stringify(selected.query||{},null,2);$('#apiBody').value=selected.body===null?'':JSON.stringify(selected.body,null,2);$('#apiResult').textContent='Ready: '+selected.name+' · '+selected.category;$('#apiStatus').textContent=''}
$('#runApi').addEventListener('click',async()=>{const status=$('#apiStatus'),result=$('#apiResult'),method=$('#apiMethod').value,path=$('#apiPath').value.trim();status.textContent='Sending…';status.classList.remove('error');try{const query=JSON.parse($('#apiQuery').value||'{}');if(!query||Array.isArray(query)||typeof query!=='object')throw new Error('Query parameters must be a JSON object.');let body=null;const raw=$('#apiBody').value.trim();if(raw)body=JSON.parse(raw);if(selected?.confirm&&!confirm('This operation may change Chit data, start work, or stop a job. Continue?')){status.textContent='Cancelled';return}const r=await callApi(method,path,query,body);result.textContent=pretty(r.data);status.textContent='HTTP '+r.status;if(!r.ok)status.classList.add('error')}catch(e){result.textContent=e.message;status.textContent='Could not send request';status.classList.add('error')}});
checkSession();
</script></body></html>'''


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

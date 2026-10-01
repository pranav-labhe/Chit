import json

import httpx
import pytest
from fastapi.testclient import TestClient

from pranav.chit import api
from pranav.chit import ui


KEY = "test-ui-key"


@pytest.fixture(autouse=True)
def configured_ui(monkeypatch):
    monkeypatch.setattr(api, "API_KEY", KEY)
    with ui._key_sessions_lock:
        ui._key_sessions.clear()
    yield
    with ui._key_sessions_lock:
        ui._key_sessions.clear()


def test_ui_is_single_page_and_lists_every_documented_api_route():
    with TestClient(ui.app) as client:
        response = client.get("/")
    assert response.status_code == 200
    assert "Unlock Chit Console" in response.text
    assert "__ROUTES__" not in response.text
    assert len(ui.ROUTES) == 25  # two examples for the single /generate route
    expected = {
        ("GET", "/health"), ("GET", "/model"),
        ("POST", "/generate"), ("POST", "/chat"),
        ("POST", "/sessions"), ("GET", "/sessions"),
        ("GET", "/sessions/{session_id}"), ("DELETE", "/sessions/{session_id}"),
        ("POST", "/memory"), ("GET", "/memory/search"), ("DELETE", "/memory/{memory_id}"),
        ("GET", "/train/configs"), ("POST", "/train"), ("GET", "/train"),
        ("GET", "/train/{job_id}"), ("POST", "/train/{job_id}/cancel"),
        ("POST", "/knowledge"), ("GET", "/knowledge"), ("GET", "/knowledge/stats"),
        ("GET", "/knowledge/{entry_id}"), ("DELETE", "/knowledge/{entry_id}"),
        ("POST", "/knowledge/train"), ("GET", "/data"), ("POST", "/data/split"),
    }
    assert {(r["method"], r["path"]) for r in ui.ROUTES} == expected
    assert len(expected) == 24


def test_login_is_required_key_is_server_side_and_sessions_are_isolated():
    with TestClient(ui.app) as first, TestClient(ui.app) as second:
        assert first.get("/_ui/session").json() == {"authenticated": False}
        assert first.post("/_ui/proxy", json={"method": "GET", "path": "/health"}).status_code == 401
        assert first.post("/_ui/login", json={"api_key": "wrong"}).status_code == 401

        login = first.post("/_ui/login", json={"api_key": KEY})
        assert login.status_code == 200
        assert login.json() == {"authenticated": True}
        assert KEY not in login.text
        cookie = login.cookies.get(ui.COOKIE_NAME)
        assert cookie and cookie != KEY
        assert "httponly" in login.headers["set-cookie"].lower()
        assert "samesite=strict" in login.headers["set-cookie"].lower()
        assert second.get("/_ui/session").json() == {"authenticated": False}

        logout = first.post("/_ui/logout", json={})
        assert logout.status_code == 204
        assert first.get("/_ui/session").json() == {"authenticated": False}


def test_proxy_forwards_key_request_and_response_without_exposing_key(monkeypatch):
    observed = {}

    def upstream(request):
        observed["method"] = request.method
        observed["url"] = str(request.url)
        observed["key"] = request.headers.get("x-api-key")
        observed["body"] = request.content.decode()
        return httpx.Response(202, json={"id": "job-1", "state": "queued"})

    monkeypatch.setattr(ui, "_new_http_client", lambda: httpx.AsyncClient(
        transport=httpx.MockTransport(upstream), follow_redirects=False))

    with TestClient(ui.app) as client:
        client.post("/_ui/login", json={"api_key": KEY})
        response = client.post("/_ui/proxy", json={
            "method": "POST", "path": "/train", "query": {"example": "yes"},
            "body": {"config": "tiny", "init": "scratch"},
        })

    assert response.status_code == 202
    assert response.json() == {"id": "job-1", "state": "queued"}
    assert observed == {
        "method": "POST", "url": "http://127.0.0.1:8000/train?example=yes",
        "key": KEY, "body": json.dumps({"config": "tiny", "init": "scratch"}, separators=(",", ":")),
    }
    assert KEY not in response.text


def test_proxy_omits_body_for_documented_bodyless_post(monkeypatch):
    observed = {}

    def upstream(request):
        observed["body"] = request.content
        return httpx.Response(201, json={"id": "session-id"})

    monkeypatch.setattr(ui, "_new_http_client", lambda: httpx.AsyncClient(
        transport=httpx.MockTransport(upstream), follow_redirects=False))
    with TestClient(ui.app) as client:
        client.post("/_ui/login", json={"api_key": KEY})
        response = client.post("/_ui/proxy", json={"method": "POST", "path": "/sessions"})
    assert response.status_code == 201
    assert response.json() == {"id": "session-id"}
    assert observed["body"] == b""


@pytest.mark.parametrize("method,path", [
    ("GET", "http://example.com/health"), ("GET", "/docs"),
    ("POST", "/health"), ("DELETE", "/generate"), ("GET", "/../health"),
])
def test_proxy_rejects_routes_outside_documented_api(method, path):
    with TestClient(ui.app) as client:
        client.post("/_ui/login", json={"api_key": KEY})
        response = client.post("/_ui/proxy", json={"method": method, "path": path})
    assert response.status_code == 404


def test_login_and_mutating_proxy_reject_cross_origin_requests():
    with TestClient(ui.app) as client:
        response = client.post("/_ui/login", json={"api_key": KEY}, headers={"Origin": "https://attacker.test"})
        assert response.status_code == 403
        client.post("/_ui/login", json={"api_key": KEY})
        response = client.post("/_ui/proxy", json={"method": "GET", "path": "/health"},
                               headers={"Origin": "https://attacker.test"})
    assert response.status_code == 403


def test_expired_or_restarted_server_session_requires_login_again():
    with TestClient(ui.app) as client:
        client.post("/_ui/login", json={"api_key": KEY})
        cookie = client.cookies.get(ui.COOKIE_NAME)
        with ui._key_sessions_lock:
            ui._key_sessions[cookie].expires_at = 0
        assert client.get("/_ui/session").json() == {"authenticated": False}
        client.post("/_ui/login", json={"api_key": KEY})
        # A process restart clears this in-memory map. Simulate that here.
        with ui._key_sessions_lock:
            ui._key_sessions.clear()
        assert client.get("/_ui/session").json() == {"authenticated": False}


def test_console_prefix_login_works_when_reverse_proxy_preserves_prefix(monkeypatch):
    monkeypatch.setattr(ui, "BASE_PATH", "/console")
    with TestClient(ui.app, base_url="https://app.chitt.online") as client:
        page = client.get("/console/")
        assert page.status_code == 200
        assert 'const BASE="/console"' in page.text
        login = client.post("/console/_ui/login", json={"api_key": KEY},
                            headers={"Origin": "https://app.chitt.online"})
        assert login.status_code == 200
        assert login.json() == {"authenticated": True}
        assert "path=/console" in login.headers["set-cookie"].lower()


def test_login_accepts_public_origin_behind_https_reverse_proxy():
    proxy_headers = {
        "Origin": "https://app.chitt.online",
        "Host": "127.0.0.1:8001",
        "X-Forwarded-Host": "app.chitt.online",
        "X-Forwarded-Proto": "https",
    }
    with TestClient(ui.app) as client:
        response = client.post("/_ui/login", json={"api_key": KEY}, headers=proxy_headers)
    assert response.status_code == 200
    assert response.json() == {"authenticated": True}

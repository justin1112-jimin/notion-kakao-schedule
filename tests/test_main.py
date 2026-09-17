"""main.py의 정적 파일 서빙 + 로그인 에러 플래시 회귀 테스트.

- /static/*는 로그인 없이도 접근 가능해야 함 (로그인 페이지 자체가 이 CSS/JS를 씀).
- 로그인 에러는 예전엔 /login?error=... 쿼리 파라미터로 노출돼서 새로고침해도
  반복 노출됐음 — 세션 기반 1회성 플래시로 바꿔서 한 번 보여준 뒤 사라져야 함.
"""

import os
from unittest.mock import MagicMock, patch
from urllib.parse import parse_qs, urlparse

import pytest

os.environ.setdefault("REDIS_URL", "redis://localhost:6379")
os.environ.setdefault("SESSION_SECRET_KEY", "test-secret")
os.environ.setdefault("GOOGLE_CLIENT_ID", "x")
os.environ.setdefault("GOOGLE_CLIENT_SECRET", "x")
os.environ.setdefault("CRON_SECRET", "x")
os.environ.setdefault("KAKAO_REST_API_KEY", "x")
os.environ.setdefault("NOTION_CLIENT_ID", "x")
os.environ.setdefault("NOTION_CLIENT_SECRET", "x")


@pytest.fixture
def client():
    from starlette.testclient import TestClient

    with patch("app.scheduler.create_scheduler", return_value=MagicMock()):
        from app import main

        with TestClient(main.app) as c:
            yield c


def test_static_files_accessible_without_login(client):
    resp = client.get("/static/theme.css")
    assert resp.status_code == 200
    resp = client.get("/static/theme.js")
    assert resp.status_code == 200


def test_settings_redirects_without_login(client):
    resp = client.get("/settings", follow_redirects=False)
    assert resp.status_code == 307
    assert resp.headers["location"] == "/login"


def test_login_page_links_shared_theme_css(client):
    resp = client.get("/login")
    assert "/static/theme.css" in resp.text


def test_login_error_flash_shows_once_then_clears(client):
    resp = client.get(
        "/auth/kakao/callback", params={"code": "x", "state": "wrong-state"}, follow_redirects=False
    )
    assert resp.status_code == 307
    assert resp.headers["location"] == "/login"

    first = client.get("/login")
    assert "잘못된 요청입니다" in first.text

    second = client.get("/login")
    assert "잘못된 요청입니다" not in second.text


def _settings_dict(**overrides):
    """db.get_settings()가 반환하는 것과 같은 모양의 dict (DEFAULTS 기반)."""
    from app import db

    settings = {**db.DEFAULTS}
    settings["notify_hour"] = int(settings["notify_hour"])
    settings["notify_minute"] = int(settings["notify_minute"])
    settings["last_sent_at"] = None
    settings["last_sent_status"] = None
    settings.update(overrides)
    return settings


@pytest.fixture
def logged_in_client(client):
    """카카오 로그인 콜백을 거쳐 세션에 user_id="user1"이 저장된 클라이언트."""
    with patch(
        "app.kakao_client.exchange_code_for_tokens",
        return_value={"access_token": "a", "refresh_token": "r"},
    ), patch(
        "app.kakao_client.fetch_user_info",
        return_value={"user_id": "user1", "nickname": "테스트"},
    ), patch("app.db.update_kakao_refresh_token"):
        redirect = client.get("/login/kakao", follow_redirects=False)
        state = parse_qs(urlparse(redirect.headers["location"]).query)["state"][0]
        client.get("/auth/kakao/callback", params={"code": "x", "state": state}, follow_redirects=False)
    return client


def test_ical_connect_saves_valid_url(logged_in_client):
    with patch("app.db.get_settings", return_value=_settings_dict(calendar_sources="notion")), \
         patch("app.ical_client.get_today_events", return_value=[]), \
         patch("app.db.update_ical_url") as mock_update_url, \
         patch("app.db.update_calendar_sources") as mock_update_sources:
        resp = logged_in_client.post(
            "/ical/connect", data={"ical_url": "https://example.com/cal.ics"}, follow_redirects=False
        )

    assert resp.status_code == 303
    assert resp.headers["location"] == "/settings?flash=ical_connected"
    mock_update_url.assert_called_once_with("user1", "https://example.com/cal.ics")
    mock_update_sources.assert_called_once_with("user1", "notion,ical")


def test_ical_connect_validation_failure_does_not_save(logged_in_client):
    with patch("app.db.get_settings", return_value=_settings_dict(calendar_sources="notion")), \
         patch("app.ical_client.get_today_events", side_effect=Exception("bad url")), \
         patch("app.db.update_ical_url") as mock_update_url:
        resp = logged_in_client.post("/ical/connect", data={"ical_url": "https://bad.example.com/x"})

    assert "캘린더 URL을 확인할 수 없습니다" in resp.text
    mock_update_url.assert_not_called()


def test_ical_connect_empty_url_disconnects(logged_in_client):
    with patch("app.db.get_settings", return_value=_settings_dict(calendar_sources="notion,ical")), \
         patch("app.db.update_ical_url") as mock_update_url, \
         patch("app.db.update_calendar_sources") as mock_update_sources:
        resp = logged_in_client.post("/ical/connect", data={"ical_url": ""}, follow_redirects=False)

    assert resp.status_code == 303
    assert resp.headers["location"] == "/settings?flash=ical_disconnected"
    mock_update_url.assert_called_once_with("user1", "")
    mock_update_sources.assert_called_once_with("user1", "notion")

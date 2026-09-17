"""main.py의 정적 파일 서빙 + 로그인 에러 플래시 회귀 테스트.

- /static/*는 로그인 없이도 접근 가능해야 함 (로그인 페이지 자체가 이 CSS/JS를 씀).
- 로그인 에러는 예전엔 /login?error=... 쿼리 파라미터로 노출돼서 새로고침해도
  반복 노출됐음 — 세션 기반 1회성 플래시로 바꿔서 한 번 보여준 뒤 사라져야 함.
"""

import os
from unittest.mock import MagicMock, patch

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

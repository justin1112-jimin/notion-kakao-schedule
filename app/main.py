import logging
import os
import secrets
import time
from contextlib import asynccontextmanager
from typing import Optional

import sentry_sdk
from fastapi import FastAPI, Form, Request
from fastapi.responses import JSONResponse, PlainTextResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from starlette.middleware.sessions import SessionMiddleware

from app import db, google_calendar_client, ical_client, kakao_client, notion_client, scheduler

logging.basicConfig(
    level=os.environ.get("LOG_LEVEL", "INFO"),
    format="%(asctime)s %(levelname)s %(name)s: %(message)s",
)
logger = logging.getLogger(__name__)

# 둘 다 선택 사항 — 안 넣으면 그냥 조용히 비활성화됨 (다른 OAuth 연동과 동일한 패턴)
if os.environ.get("SENTRY_DSN"):
    sentry_sdk.init(dsn=os.environ["SENTRY_DSN"], traces_sample_rate=0.0)
    logger.info("Sentry error tracking enabled")

templates = Jinja2Templates(directory="app/templates")

# "/internal/run-daily" skips the login session check but enforces its own
# secret-header check inside the handler (called by GitHub Actions, not a browser).
PUBLIC_PATHS = {"/login", "/login/kakao", "/auth/kakao/callback", "/internal/run-daily"}
# 로그인 페이지 자체가 이 정적 파일(테마 CSS/JS)을 쓰므로 로그인 없이도 접근 가능해야 함.
PUBLIC_PATH_PREFIXES = ("/static/",)


@asynccontextmanager
async def lifespan(app: FastAPI):
    app.state.scheduler = scheduler.create_scheduler()
    yield
    app.state.scheduler.shutdown()


app = FastAPI(lifespan=lifespan)
app.mount("/static", StaticFiles(directory="app/static"), name="static")


@app.middleware("http")
async def require_login(request: Request, call_next):
    path = request.url.path
    if path in PUBLIC_PATHS or path.startswith(PUBLIC_PATH_PREFIXES) or request.session.get("logged_in"):
        return await call_next(request)
    return RedirectResponse("/login")


# Must be added after `require_login` above so it ends up as the outer
# middleware and populates request.session before require_login reads it.
app.add_middleware(SessionMiddleware, secret_key=os.environ["SESSION_SECRET_KEY"])


def _get_user_id(request: Request) -> str:
    """세션에서 user_id 추출"""
    return request.session.get("user_id")


def _render_settings(request: Request, **extra):
    user_id = _get_user_id(request)
    settings = db.get_settings(user_id)
    # 방문 시점에 스케줄을 DB 설정과 동기화 — 신규 사용자 최초 등록 및
    # (드물게) 스케줄러가 놓친 사용자를 다음 방문 때 자동으로 복구함.
    scheduler.add_or_update_user_job(
        request.app.state.scheduler, user_id, settings["notify_hour"], settings["notify_minute"]
    )
    notion_databases = []
    if settings["notion_token"]:
        try:
            notion_databases = notion_client.list_shared_databases(settings["notion_token"])
        except Exception:
            notion_databases = []
    context = {
        "request": request,
        "settings": settings,
        "nickname": request.session.get("nickname"),
        "notion_connected": bool(settings["notion_token"]),
        "notion_databases": notion_databases,
        "kakao_connected": bool(settings["kakao_refresh_token"]),
        "google_calendar_connected": bool(settings["google_calendar_refresh_token"]),
        "ical_connected": bool(settings["ical_url"]),
        **extra,
    }
    return templates.TemplateResponse(request=request, name="settings.html", context=context)


@app.get("/")
async def root():
    return RedirectResponse("/settings")


@app.get("/login")
async def login(request: Request):
    # 세션 기반 1회성 플래시: 쿼리 파라미터로 넘기면 URL에 에러 문구가 남아서
    # 새로고침/뒤로가기 때마다 반복 노출되고 공유 URL에도 그대로 찍힘.
    error = request.session.pop("login_error", None)
    return templates.TemplateResponse(
        request=request, name="login.html", context={"request": request, "error": error}
    )


@app.get("/login/kakao")
async def login_kakao(request: Request):
    state = secrets.token_urlsafe(16)
    request.session["oauth_state"] = state
    redirect_uri = str(request.url_for("kakao_login_callback"))
    return RedirectResponse(kakao_client.build_authorize_url(redirect_uri, state))


@app.get("/auth/kakao/callback", name="kakao_login_callback")
async def kakao_login_callback(request: Request, code: str, state: str):
    if state != request.session.get("oauth_state"):
        logger.warning("kakao login state mismatch")
        request.session["login_error"] = "잘못된 요청입니다. 다시 로그인해주세요."
        return RedirectResponse("/login")

    redirect_uri = str(request.url_for("kakao_login_callback"))
    tokens = kakao_client.exchange_code_for_tokens(redirect_uri, code)
    user_info = kakao_client.fetch_user_info(tokens["access_token"])
    logger.info("kakao login success user=%s", user_info["user_id"])

    request.session["logged_in"] = True
    request.session["user_id"] = user_info["user_id"]
    request.session["nickname"] = user_info["nickname"]
    # 카카오 로그인 자체가 talk_message 동의를 포함하므로, 로그인 = 카카오 연결.
    db.update_kakao_refresh_token(user_info["user_id"], tokens["refresh_token"])
    return RedirectResponse("/settings")


@app.get("/logout")
async def logout(request: Request):
    request.session.clear()
    return RedirectResponse("/login")


@app.get("/settings")
async def settings_page(request: Request, flash: Optional[str] = None):
    return _render_settings(request, flash=flash)


@app.post("/settings")
async def save_settings(
    request: Request,
    notify_hour: int = Form(...),
    notify_minute: int = Form(...),
):
    user_id = _get_user_id(request)
    db.update_general_settings(user_id=user_id, notify_hour=notify_hour, notify_minute=notify_minute)
    scheduler.add_or_update_user_job(request.app.state.scheduler, user_id, notify_hour, notify_minute)
    return RedirectResponse("/settings?flash=saved", status_code=303)


@app.get("/notion/connect")
async def notion_connect(request: Request):
    state = secrets.token_urlsafe(16)
    request.session["oauth_state_notion"] = state
    redirect_uri = str(request.url_for("notion_callback"))
    url = notion_client.build_authorize_url(redirect_uri, state)
    return RedirectResponse(url)


@app.get("/notion/callback", name="notion_callback")
async def notion_callback(request: Request, code: str, state: str):
    if state != request.session.get("oauth_state_notion"):
        return PlainTextResponse("잘못된 요청입니다.", status_code=400)

    user_id = _get_user_id(request)
    redirect_uri = str(request.url_for("notion_callback"))
    token_data = notion_client.exchange_code_for_token(redirect_uri, code)
    db.update_notion_token(user_id, token_data["access_token"])

    # 공유된 데이터베이스가 정확히 하나면 속성까지 자동으로 마저 선택
    databases = notion_client.list_shared_databases(token_data["access_token"])
    if len(databases) == 1:
        date_property, title_property = notion_client.detect_properties(
            token_data["access_token"], databases[0]["id"]
        )
        db.update_notion_database(user_id, databases[0]["id"], date_property, title_property)
        return RedirectResponse("/settings?flash=notion_connected", status_code=303)
    if not databases:
        return RedirectResponse("/settings?flash=notion_no_database", status_code=303)
    return RedirectResponse("/settings?flash=notion_select_database", status_code=303)


@app.post("/notion/select-database")
async def notion_select_database(request: Request, database_id: str = Form(...)):
    user_id = _get_user_id(request)
    settings = db.get_settings(user_id)
    date_property, title_property = notion_client.detect_properties(
        settings["notion_token"], database_id
    )
    db.update_notion_database(user_id, database_id, date_property, title_property)
    return RedirectResponse("/settings?flash=notion_database_selected", status_code=303)


@app.get("/google-calendar/connect")
async def google_calendar_connect(request: Request):
    state = secrets.token_urlsafe(16)
    request.session["oauth_state_calendar"] = state
    redirect_uri = str(request.url_for("google_calendar_callback"))
    url = google_calendar_client.build_calendar_authorize_url(redirect_uri, state)
    return RedirectResponse(url)


@app.get("/google-calendar/callback", name="google_calendar_callback")
async def google_calendar_callback(request: Request, code: str, state: str):
    if state != request.session.get("oauth_state_calendar"):
        return PlainTextResponse("잘못된 요청입니다.", status_code=400)

    user_id = _get_user_id(request)
    redirect_uri = str(request.url_for("google_calendar_callback"))
    tokens = google_calendar_client.exchange_code_for_tokens(redirect_uri, code)
    db.update_google_calendar_refresh_token(user_id, tokens["refresh_token"])
    # Google Calendar를 기본으로 활성화
    current_sources = db.get_settings(user_id).get("calendar_sources", "notion")
    if "google" not in current_sources:
        new_sources = f"{current_sources},google" if current_sources else "google"
        db.update_calendar_sources(user_id, new_sources)
    return RedirectResponse("/settings?flash=google_calendar_connected", status_code=303)


@app.post("/ical/connect")
async def ical_connect(request: Request, ical_url: str = Form("")):
    user_id = _get_user_id(request)
    ical_url = ical_url.strip()
    current_sources = [s for s in db.get_settings(user_id)["calendar_sources"].split(",") if s]

    if not ical_url:
        db.update_ical_url(user_id, "")
        db.update_calendar_sources(user_id, ",".join(s for s in current_sources if s != "ical") or "notion")
        return RedirectResponse("/settings?flash=ical_disconnected", status_code=303)

    if ical_url.startswith("webcal://"):
        ical_url = ical_url.replace("webcal://", "https://", 1)

    try:
        ical_client.get_today_events(ical_url)  # 저장 전에 실제로 파싱되는지 검증
    except Exception as e:
        logger.warning("ical url validation failed user=%s: %s", user_id, e)
        return _render_settings(
            request, ical_error="캘린더 URL을 확인할 수 없습니다. 공개 공유 URL이 맞는지 확인해주세요."
        )

    db.update_ical_url(user_id, ical_url)
    if "ical" not in current_sources:
        current_sources.append("ical")
    db.update_calendar_sources(user_id, ",".join(current_sources))
    return RedirectResponse("/settings?flash=ical_connected", status_code=303)


@app.post("/preview")
async def preview(request: Request):
    user_id = _get_user_id(request)
    settings = db.get_settings(user_id)
    items = notion_client.get_today_schedule(
        settings["notion_token"],
        settings["notion_database_id"],
        settings["notion_date_property"],
        settings["notion_title_property"],
    )
    message = notion_client.format_message(items)
    return _render_settings(request, preview_message=message)


@app.post("/test-send")
async def test_send(request: Request):
    user_id = _get_user_id(request)
    try:
        message = scheduler.run_daily_job(user_id=user_id, source="manual")
        return _render_settings(request, test_result=f"성공\n{message}")
    except scheduler.NoCalendarConnectedError as e:
        return _render_settings(request, test_result=f"실패: {e}", show_no_calendar_alert=True)
    except Exception as e:
        return _render_settings(request, test_result=f"실패: {e}")


@app.get("/api/send-history")
async def api_send_history(request: Request):
    """발송 이력 및 통계 JSON 반환"""
    if not request.session.get("logged_in"):
        return JSONResponse({"error": "unauthorized"}, status_code=401)

    user_id = _get_user_id(request)
    history = db.get_send_history(user_id, limit=30)
    stats = db.get_send_statistics(user_id)
    return JSONResponse({
        "history": history,
        "statistics": stats,
    })


@app.get("/status")
async def status_page(request: Request):
    """지금 저장된 알림 시각과, 스케줄러에 실제로 예약된 다음 발송 시각을 보여줌.

    두 값이 다르게 보인다면(예: 방금 시각을 바꿨는데 아직 반영 전) /settings를
    한 번 방문하면 즉시 동기화됨(`_render_settings`가 매번 재등록하므로).
    """
    user_id = _get_user_id(request)
    settings = db.get_settings(user_id)
    scheduler.add_or_update_user_job(
        request.app.state.scheduler, user_id, settings["notify_hour"], settings["notify_minute"]
    )
    next_run_at = scheduler.get_next_run_time(request.app.state.scheduler, user_id)
    context = {
        "request": request,
        "settings": settings,
        "nickname": request.session.get("nickname"),
        "notion_connected": bool(settings["notion_token"]),
        "kakao_connected": bool(settings["kakao_refresh_token"]),
        "google_calendar_connected": bool(settings["google_calendar_refresh_token"]),
        "ical_connected": bool(settings["ical_url"]),
        "already_sent_today": scheduler.already_sent_today(user_id),
        "next_run_at": next_run_at,
    }
    return templates.TemplateResponse(request=request, name="status.html", context=context)


@app.get("/dashboard")
async def dashboard(request: Request):
    """발송 이력 대시보드 (로그인 필수)"""
    user_id = _get_user_id(request)
    history = db.get_send_history(user_id, limit=30)
    stats = db.get_send_statistics(user_id)
    context = {
        "request": request,
        "history": history,
        "statistics": stats,
    }
    return templates.TemplateResponse(request=request, name="dashboard.html", context=context)


@app.get("/internal/run-daily")
async def internal_run_daily(request: Request):
    """앱 내부 스케줄러가 놓친 사용자를 재시도하는 백업 트리거 (GitHub Actions가 호출).

    등록된 전체 사용자를 순회해서, 오늘 아직 성공 발송을 못 한 사용자만 재시도한다.
    한 명이라도 실패하면 500을 반환해 GitHub Actions가 저장소 소유자에게 이메일로 알리게 한다.
    """
    if request.headers.get("X-Cron-Secret") != os.environ["CRON_SECRET"]:
        logger.warning("run-daily called with invalid cron secret")
        return PlainTextResponse("unauthorized", status_code=401)

    logger.info("backup trigger started")
    results = []
    any_failed = False
    for user_id in db.get_all_user_ids():
        if scheduler.already_sent_today(user_id):
            results.append(f"{user_id}: already sent today")
            continue
        try:
            scheduler.run_daily_job(user_id=user_id, source="backup")
            results.append(f"{user_id}: sent")
        except Exception as e:
            any_failed = True
            results.append(f"{user_id}: failed - {e}")
        time.sleep(0.3)  # 카카오 API 초당 요청 한도 방지용 (사용자 순차 발송 사이 간격)

    body = "\n".join(results) if results else "no registered users"
    return PlainTextResponse(body, status_code=500 if any_failed else 200)

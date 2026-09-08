import os
import secrets
from contextlib import asynccontextmanager
from typing import Optional

from fastapi import FastAPI, Form, Request
from fastapi.responses import JSONResponse, PlainTextResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
from starlette.middleware.sessions import SessionMiddleware

from app import auth, db, google_calendar_client, kakao_client, notion_client, scheduler

templates = Jinja2Templates(directory="app/templates")

# "/internal/run-daily" skips the login session check but enforces its own
# secret-header check inside the handler (called by GitHub Actions, not a browser).
PUBLIC_PATHS = {"/login", "/login/google", "/auth/callback", "/internal/run-daily"}

# 현재 개인용(1인) 운영 — 앱 내부 스케줄러(APScheduler)는 이 사용자 기준으로만 동작.
# 다중 사용자가 실제로 늘어나면 사용자별 스케줄 등록 방식으로 교체 필요.
ADMIN_USER_ID = os.environ.get("ADMIN_USER_ID", "default_user")


@asynccontextmanager
async def lifespan(app: FastAPI):
    settings = db.get_settings(ADMIN_USER_ID)
    app.state.scheduler = scheduler.create_scheduler(ADMIN_USER_ID, settings)
    yield
    app.state.scheduler.shutdown()


app = FastAPI(lifespan=lifespan)


@app.middleware("http")
async def require_login(request: Request, call_next):
    if request.url.path in PUBLIC_PATHS or request.session.get("logged_in"):
        return await call_next(request)
    return RedirectResponse("/login")


# Must be added after `require_login` above so it ends up as the outer
# middleware and populates request.session before require_login reads it.
app.add_middleware(SessionMiddleware, secret_key=os.environ["SESSION_SECRET_KEY"])


def _get_user_id(request: Request) -> str:
    """세션에서 user_id 추출"""
    return request.session.get("user_id")


def _mask(value: str) -> str:
    if not value:
        return ""
    return f"****{value[-4:]}" if len(value) > 4 else "****"


def _render_settings(request: Request, **extra):
    user_id = _get_user_id(request)
    settings = db.get_settings(user_id)
    context = {
        "request": request,
        "settings": settings,
        "user_email": request.session.get("email"),
        "notion_token_display": _mask(settings["notion_token"]),
        "kakao_rest_api_key_display": _mask(settings["kakao_rest_api_key"]),
        "kakao_client_secret_display": _mask(settings["kakao_client_secret"]),
        "kakao_connected": bool(settings["kakao_refresh_token"]),
        "google_calendar_connected": bool(settings["google_calendar_refresh_token"]),
        **extra,
    }
    return templates.TemplateResponse(request=request, name="settings.html", context=context)


@app.get("/")
async def root():
    return RedirectResponse("/settings")


@app.get("/login")
async def login(request: Request, error: Optional[str] = None):
    return templates.TemplateResponse(
        request=request, name="login.html", context={"request": request, "error": error}
    )


@app.get("/login/google")
async def login_google(request: Request):
    state = secrets.token_urlsafe(16)
    request.session["oauth_state"] = state
    redirect_uri = str(request.url_for("auth_callback"))
    return RedirectResponse(auth.build_authorize_url(redirect_uri, state))


@app.get("/auth/callback", name="auth_callback")
async def auth_callback(request: Request, code: str, state: str):
    if state != request.session.get("oauth_state"):
        return RedirectResponse("/login?error=잘못된 요청입니다. 다시 로그인해주세요.")

    redirect_uri = str(request.url_for("auth_callback"))
    user_info = auth.fetch_user_info(redirect_uri, code)

    request.session["logged_in"] = True
    request.session["user_id"] = user_info["user_id"]
    request.session["email"] = user_info["email"]
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
    notion_token: str = Form(""),
    notion_database_id: str = Form(...),
    notion_date_property: str = Form(...),
    notion_title_property: str = Form(...),
    kakao_rest_api_key: str = Form(""),
    kakao_client_secret: str = Form(""),
    notify_hour: int = Form(...),
    notify_minute: int = Form(...),
):
    user_id = _get_user_id(request)
    current = db.get_settings(user_id)
    db.update_general_settings(
        user_id=user_id,
        notion_token=notion_token or current["notion_token"],
        notion_database_id=notion_database_id,
        notion_date_property=notion_date_property,
        notion_title_property=notion_title_property,
        kakao_rest_api_key=kakao_rest_api_key or current["kakao_rest_api_key"],
        kakao_client_secret=kakao_client_secret or current["kakao_client_secret"],
        notify_hour=notify_hour,
        notify_minute=notify_minute,
    )
    scheduler.reschedule(request.app.state.scheduler, notify_hour, notify_minute)
    return RedirectResponse("/settings?flash=saved", status_code=303)


@app.get("/kakao/connect")
async def kakao_connect(request: Request):
    user_id = _get_user_id(request)
    settings = db.get_settings(user_id)
    redirect_uri = str(request.url_for("kakao_callback"))
    url = kakao_client.build_authorize_url(settings["kakao_rest_api_key"], redirect_uri)
    return RedirectResponse(url)


@app.get("/kakao/callback", name="kakao_callback")
async def kakao_callback(request: Request, code: str):
    user_id = _get_user_id(request)
    settings = db.get_settings(user_id)
    redirect_uri = str(request.url_for("kakao_callback"))
    tokens = kakao_client.exchange_code_for_tokens(
        settings["kakao_rest_api_key"],
        settings["kakao_client_secret"],
        redirect_uri,
        code,
    )
    db.update_kakao_refresh_token(user_id, tokens["refresh_token"])
    return RedirectResponse("/settings?flash=kakao_connected", status_code=303)


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
    if request.headers.get("X-Cron-Secret") != os.environ["CRON_SECRET"]:
        return PlainTextResponse("unauthorized", status_code=401)

    if scheduler.already_sent_today(ADMIN_USER_ID):
        return PlainTextResponse("already sent today", status_code=200)

    try:
        scheduler.run_daily_job(user_id=ADMIN_USER_ID, source="backup")
        return PlainTextResponse("sent", status_code=200)
    except Exception as e:
        return PlainTextResponse(f"failed: {e}", status_code=500)

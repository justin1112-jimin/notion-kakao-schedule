from contextlib import asynccontextmanager
from typing import Optional

from fastapi import FastAPI, Form, Request
from fastapi.responses import RedirectResponse
from fastapi.templating import Jinja2Templates

from app import db, kakao_client, notion_client, scheduler

templates = Jinja2Templates(directory="app/templates")


@asynccontextmanager
async def lifespan(app: FastAPI):
    db.init_db()
    app.state.scheduler = scheduler.create_scheduler(db.get_settings())
    yield
    app.state.scheduler.shutdown()


app = FastAPI(lifespan=lifespan)


def _mask(value: str) -> str:
    if not value:
        return ""
    return f"****{value[-4:]}" if len(value) > 4 else "****"


def _render_settings(request: Request, **extra):
    settings = db.get_settings()
    context = {
        "request": request,
        "settings": settings,
        "notion_token_display": _mask(settings["notion_token"]),
        "kakao_rest_api_key_display": _mask(settings["kakao_rest_api_key"]),
        "kakao_client_secret_display": _mask(settings["kakao_client_secret"]),
        "kakao_connected": bool(settings["kakao_refresh_token"]),
        **extra,
    }
    return templates.TemplateResponse("settings.html", context)


@app.get("/")
async def root():
    return RedirectResponse("/settings")


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
    current = db.get_settings()
    db.update_general_settings(
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
    settings = db.get_settings()
    redirect_uri = str(request.url_for("kakao_callback"))
    url = kakao_client.build_authorize_url(settings["kakao_rest_api_key"], redirect_uri)
    return RedirectResponse(url)


@app.get("/kakao/callback", name="kakao_callback")
async def kakao_callback(request: Request, code: str):
    settings = db.get_settings()
    redirect_uri = str(request.url_for("kakao_callback"))
    tokens = kakao_client.exchange_code_for_tokens(
        settings["kakao_rest_api_key"],
        settings["kakao_client_secret"],
        redirect_uri,
        code,
    )
    db.update_kakao_refresh_token(tokens["refresh_token"])
    return RedirectResponse("/settings?flash=kakao_connected", status_code=303)


@app.post("/preview")
async def preview(request: Request):
    settings = db.get_settings()
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
    try:
        message = scheduler.run_daily_job()
        return _render_settings(request, test_result=f"성공\n{message}")
    except Exception as e:
        return _render_settings(request, test_result=f"실패: {e}")

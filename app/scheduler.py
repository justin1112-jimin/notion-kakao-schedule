import os
from datetime import datetime
from zoneinfo import ZoneInfo

from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.triggers.cron import CronTrigger

from app import db, google_calendar_client, kakao_client, notion_client

KST = ZoneInfo("Asia/Seoul")
JOB_ID = "daily_notify"


def _app_base_url() -> str:
    """카카오 메시지의 '자세히 보기' 링크에 쓸 앱 자신의 공개 URL.

    Render는 배포된 서비스에 RENDER_EXTERNAL_URL을 자동으로 주입하므로 별도
    설정 없이 프로덕션 도메인을 얻을 수 있음. 로컬 개발 환경에서는 이 값이
    없으므로 localhost로 대체(로컬 테스트 발송이 localhost로 가는 것은 정상).
    """
    return (
        os.environ.get("PUBLIC_BASE_URL")
        or os.environ.get("RENDER_EXTERNAL_URL")
        or "http://localhost:8000"
    )


class NoCalendarConnectedError(Exception):
    pass


def run_daily_job(user_id: str, source: str = "scheduler") -> str:
    """
    user_id: 사용자 ID
    source: "scheduler" | "backup" | "manual"
    """
    settings = db.get_settings(user_id)
    now = datetime.now(KST).isoformat()
    try:
        if not settings.get("notion_token") and not settings.get("google_calendar_refresh_token"):
            raise NoCalendarConnectedError(
                "연결된 일정 서비스가 없습니다. Notion 또는 Google Calendar를 먼저 연결해주세요."
            )

        message_parts = []
        calendar_sources = settings.get("calendar_sources", "notion").split(",")

        if "notion" in calendar_sources:
            items = notion_client.get_today_schedule(
                settings["notion_token"],
                settings["notion_database_id"],
                settings["notion_date_property"],
                settings["notion_title_property"],
            )
            notion_msg = notion_client.format_message(items)
            if notion_msg:
                message_parts.append(f"[Notion]\n{notion_msg}")

        if "google" in calendar_sources and settings.get("google_calendar_refresh_token"):
            tokens = google_calendar_client.refresh_access_token(
                settings["google_calendar_refresh_token"]
            )
            events = google_calendar_client.get_today_events(tokens["access_token"])
            google_msg = google_calendar_client.format_google_events(events)
            if google_msg:
                message_parts.append(f"[Google Calendar]\n{google_msg}")

        message = "\n\n".join(message_parts)
        if not message:
            message = "오늘 일정이 없습니다."

        tokens = kakao_client.refresh_kakao_access_token(settings["kakao_refresh_token"])
        new_refresh_token = tokens.get("refresh_token")
        if new_refresh_token:
            db.update_kakao_refresh_token(user_id, new_refresh_token)

        link_url = f"{_app_base_url()}/dashboard"
        kakao_client.send_kakao_memo(tokens["access_token"], message, link_url)
        db.record_send_result(user_id, "success", now)
        db.add_send_history(user_id, now, "success", source)
        return message
    except Exception as e:
        error_msg = str(e)
        db.record_send_result(user_id, f"error: {error_msg}", now)
        db.add_send_history(user_id, now, "failed", source, _sanitize_error(error_msg))
        raise


def _sanitize_error(error_msg: str) -> str:
    """에러 메시지에서 민감한 정보 제거 (API/대시보드에서 노출될 예정)"""
    if not error_msg:
        return "Unknown error"
    msg = error_msg.lower()
    if "connection" in msg or "timeout" in msg or "network" in msg:
        return "Connection error"
    if "token" in msg or "unauthorized" in msg or "401" in msg:
        return "Authentication failed"
    if "403" in msg or "forbidden" in msg:
        return "Permission denied"
    if "404" in msg or "not found" in msg:
        return "Resource not found"
    if "invalid" in msg or "bad" in msg:
        return "Invalid request"
    return "Request failed"


def create_scheduler(user_id: str, settings: dict) -> BackgroundScheduler:
    sched = BackgroundScheduler(timezone=KST)
    sched.add_job(
        run_daily_job,
        CronTrigger(hour=settings["notify_hour"], minute=settings["notify_minute"], timezone=KST),
        id=JOB_ID,
        kwargs={"user_id": user_id, "source": "scheduler"},
    )
    sched.start()
    return sched


def reschedule(sched: BackgroundScheduler, hour: int, minute: int):
    sched.reschedule_job(JOB_ID, trigger=CronTrigger(hour=hour, minute=minute, timezone=KST))


def already_sent_today(user_id: str) -> bool:
    """오늘 이미 성공 발송했는지 확인"""
    settings = db.get_settings(user_id)
    if settings["last_sent_status"] != "success" or not settings["last_sent_at"]:
        return False
    last_sent = datetime.fromisoformat(settings["last_sent_at"])
    return last_sent.astimezone(KST).date() == datetime.now(KST).date()

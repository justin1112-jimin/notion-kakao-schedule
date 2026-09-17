import logging
import os
from datetime import datetime
from zoneinfo import ZoneInfo

import sentry_sdk
from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.triggers.cron import CronTrigger

from app import db, google_calendar_client, kakao_client, notion_client

logger = logging.getLogger(__name__)

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
    logger.info("daily job start user=%s source=%s", user_id, source)
    try:
        if not settings.get("notion_token") and not settings.get("google_calendar_refresh_token"):
            raise NoCalendarConnectedError(
                "연결된 일정 서비스가 없습니다. Notion 또는 Google Calendar를 먼저 연결해주세요."
            )

        message_parts = []
        failed_sources = []
        calendar_sources = settings.get("calendar_sources", "notion").split(",")
        active_sources = [s for s in calendar_sources if s != "google" or settings.get("google_calendar_refresh_token")]

        if "notion" in calendar_sources:
            try:
                items = notion_client.get_today_schedule(
                    settings["notion_token"],
                    settings["notion_database_id"],
                    settings["notion_date_property"],
                    settings["notion_title_property"],
                )
                notion_msg = notion_client.format_message(items)
                if notion_msg:
                    message_parts.append(f"[Notion]\n{notion_msg}")
                db.record_source_success(user_id, "notion", now)
            except Exception as e:
                logger.warning("notion fetch failed user=%s: %s", user_id, e)
                failed_sources.append("Notion")

        if "google" in calendar_sources and settings.get("google_calendar_refresh_token"):
            try:
                tokens = google_calendar_client.refresh_access_token(
                    settings["google_calendar_refresh_token"]
                )
                events = google_calendar_client.get_today_events(tokens["access_token"])
                google_msg = google_calendar_client.format_google_events(events)
                if google_msg:
                    message_parts.append(f"[Google Calendar]\n{google_msg}")
                db.record_source_success(user_id, "google_calendar", now)
            except Exception as e:
                logger.warning("google calendar fetch failed user=%s: %s", user_id, e)
                failed_sources.append("Google Calendar")

        # 활성화된 캘린더가 전부 조회 실패면 "오늘 일정이 없습니다"로 조용히
        # 보내는 대신 명확하게 실패 처리 (겪었던 문제: 한쪽 캘린더 실패가 나머지
        # 캘린더에서 이미 가져온 내용까지 같이 막아버리던 비대칭 동작을 방지).
        if failed_sources and len(failed_sources) == len(active_sources):
            raise Exception(f"캘린더 조회 실패: {', '.join(failed_sources)}")

        if failed_sources:
            message_parts.append(f"⚠️ {', '.join(failed_sources)} 조회 실패 — 재연결이 필요할 수 있어요")

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
        logger.info("daily job success user=%s source=%s", user_id, source)
        return message
    except Exception as e:
        error_msg = str(e)
        logger.error("daily job failed user=%s source=%s: %s", user_id, source, error_msg)
        sentry_sdk.capture_exception(e)
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


def _job_id(user_id: str) -> str:
    return f"{JOB_ID}:{user_id}"


def add_or_update_user_job(sched: BackgroundScheduler, user_id: str, hour: int, minute: int):
    """사용자의 알림 시각으로 작업을 등록/갱신 (신규 사용자면 새로 추가됨)"""
    sched.add_job(
        run_daily_job,
        CronTrigger(hour=hour, minute=minute, timezone=KST),
        id=_job_id(user_id),
        kwargs={"user_id": user_id, "source": "scheduler"},
        replace_existing=True,
    )


def create_scheduler() -> BackgroundScheduler:
    """지금까지 등록된 모든 사용자 각각의 알림 시각으로 작업을 등록한 스케줄러 생성"""
    sched = BackgroundScheduler(timezone=KST)
    sched.start()
    for user_id in db.get_all_user_ids():
        settings = db.get_settings(user_id)
        add_or_update_user_job(sched, user_id, settings["notify_hour"], settings["notify_minute"])
    return sched


def get_next_run_time(sched: BackgroundScheduler, user_id: str):
    """이 사용자의 다음 자동 발송 예정 시각 (스케줄러에 등록 안 돼있으면 None)"""
    job = sched.get_job(_job_id(user_id))
    return job.next_run_time if job else None


def already_sent_today(user_id: str) -> bool:
    """오늘 이미 성공 발송했는지 확인"""
    settings = db.get_settings(user_id)
    if settings["last_sent_status"] != "success" or not settings["last_sent_at"]:
        return False
    last_sent = datetime.fromisoformat(settings["last_sent_at"])
    return last_sent.astimezone(KST).date() == datetime.now(KST).date()

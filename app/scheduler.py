from datetime import datetime
from zoneinfo import ZoneInfo

from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.triggers.cron import CronTrigger

from app import db, kakao_client, notion_client

KST = ZoneInfo("Asia/Seoul")
JOB_ID = "daily_notify"


def run_daily_job() -> str:
    settings = db.get_settings()
    try:
        items = notion_client.get_today_schedule(
            settings["notion_token"],
            settings["notion_database_id"],
            settings["notion_date_property"],
            settings["notion_title_property"],
        )
        message = notion_client.format_message(items)

        tokens = kakao_client.refresh_kakao_access_token(
            settings["kakao_rest_api_key"],
            settings["kakao_refresh_token"],
            settings["kakao_client_secret"],
        )
        new_refresh_token = tokens.get("refresh_token")
        if new_refresh_token:
            db.update_kakao_refresh_token(new_refresh_token)

        kakao_client.send_kakao_memo(tokens["access_token"], message)
        db.record_send_result("success", datetime.now(KST).isoformat())
        return message
    except Exception as e:
        db.record_send_result(f"error: {e}", datetime.now(KST).isoformat())
        raise


def create_scheduler(settings: dict) -> BackgroundScheduler:
    sched = BackgroundScheduler(timezone=KST)
    sched.add_job(
        run_daily_job,
        CronTrigger(hour=settings["notify_hour"], minute=settings["notify_minute"], timezone=KST),
        id=JOB_ID,
    )
    sched.start()
    return sched


def reschedule(sched: BackgroundScheduler, hour: int, minute: int):
    sched.reschedule_job(JOB_ID, trigger=CronTrigger(hour=hour, minute=minute, timezone=KST))

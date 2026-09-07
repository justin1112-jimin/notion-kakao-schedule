from datetime import datetime
from zoneinfo import ZoneInfo

from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.triggers.cron import CronTrigger

from app import db, kakao_client, notion_client

KST = ZoneInfo("Asia/Seoul")
JOB_ID = "daily_notify"


def run_daily_job(source: str = "scheduler") -> str:
    """
    source: "scheduler" | "backup" | "manual"
    """
    settings = db.get_settings()
    now = datetime.now(KST).isoformat()
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
        db.record_send_result("success", now)
        db.add_send_history(now, "success", source)
        return message
    except Exception as e:
        error_msg = str(e)
        db.record_send_result(f"error: {error_msg}", now)
        db.add_send_history(now, "failed", source, error_msg)
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


def already_sent_today(settings: dict) -> bool:
    if settings["last_sent_status"] != "success" or not settings["last_sent_at"]:
        return False
    last_sent = datetime.fromisoformat(settings["last_sent_at"])
    return last_sent.astimezone(KST).date() == datetime.now(KST).date()

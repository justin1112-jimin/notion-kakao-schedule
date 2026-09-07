import os

import redis

KEY = "settings"

DEFAULTS = {
    "notion_token": "",
    "notion_database_id": "",
    "notion_date_property": "날짜",
    "notion_title_property": "이름",
    "kakao_rest_api_key": "",
    "kakao_client_secret": "",
    "kakao_refresh_token": "",
    "notify_hour": "8",
    "notify_minute": "0",
    "last_sent_at": "",
    "last_sent_status": "",
}


def get_client() -> redis.Redis:
    redis_url = os.environ["REDIS_URL"]
    return redis.from_url(redis_url, decode_responses=True)


def init_db():
    client = get_client()
    if not client.exists(KEY):
        client.hset(KEY, mapping=DEFAULTS)


def get_settings() -> dict:
    client = get_client()
    raw = client.hgetall(KEY)
    settings = {**DEFAULTS, **raw}
    settings["notify_hour"] = int(settings["notify_hour"])
    settings["notify_minute"] = int(settings["notify_minute"])
    settings["last_sent_at"] = settings["last_sent_at"] or None
    settings["last_sent_status"] = settings["last_sent_status"] or None
    return settings


def update_general_settings(
    notion_token: str,
    notion_database_id: str,
    notion_date_property: str,
    notion_title_property: str,
    kakao_rest_api_key: str,
    kakao_client_secret: str,
    notify_hour: int,
    notify_minute: int,
):
    client = get_client()
    client.hset(
        KEY,
        mapping={
            "notion_token": notion_token,
            "notion_database_id": notion_database_id,
            "notion_date_property": notion_date_property,
            "notion_title_property": notion_title_property,
            "kakao_rest_api_key": kakao_rest_api_key,
            "kakao_client_secret": kakao_client_secret,
            "notify_hour": str(notify_hour),
            "notify_minute": str(notify_minute),
        },
    )


def update_kakao_refresh_token(token: str):
    client = get_client()
    client.hset(KEY, "kakao_refresh_token", token)


def record_send_result(status: str, when: str):
    client = get_client()
    client.hset(KEY, mapping={"last_sent_status": status, "last_sent_at": when})


def add_send_history(timestamp: str, status: str, source: str, message: str = ""):
    """
    Redis 리스트에 발송 기록 추가 (최근 100개만 유지)
    status: "success" or "failed"
    source: "scheduler" | "backup" | "manual"
    """
    import json
    client = get_client()
    history_key = "send_history"
    record = json.dumps({
        "timestamp": timestamp,
        "status": status,
        "source": source,
        "message": message,
    })
    client.lpush(history_key, record)
    client.ltrim(history_key, 0, 99)


def get_send_history(limit: int = 30) -> list:
    """최근 발송 이력 조회"""
    import json
    client = get_client()
    history_key = "send_history"
    raw_records = client.lrange(history_key, 0, limit - 1)
    return [json.loads(r) for r in raw_records]


def get_send_statistics() -> dict:
    """발송 통계 조회"""
    from datetime import datetime, timedelta
    from zoneinfo import ZoneInfo

    history = get_send_history(limit=100)
    KST = ZoneInfo("Asia/Seoul")
    today = datetime.now(KST).date()
    week_ago = today - timedelta(days=7)

    total = len(history)
    success_count = sum(1 for r in history if r["status"] == "success")
    week_success = 0
    week_total = 0

    for record in history:
        try:
            record_date = datetime.fromisoformat(record["timestamp"]).astimezone(KST).date()
            if record_date >= week_ago:
                week_total += 1
                if record["status"] == "success":
                    week_success += 1
        except:
            pass

    source_count = {}
    for record in history:
        source = record.get("source", "unknown")
        source_count[source] = source_count.get(source, 0) + 1

    return {
        "total": total,
        "success_count": success_count,
        "success_rate": f"{(success_count / total * 100) if total > 0 else 0:.1f}%",
        "week_success": week_success,
        "week_total": week_total,
        "week_success_rate": f"{(week_success / week_total * 100) if week_total > 0 else 0:.1f}%",
        "source_count": source_count,
    }

import os

import redis

def _get_settings_key(user_id: str) -> str:
    """사용자별 설정 키 생성"""
    return f"user:{user_id}:settings"


def _get_history_key(user_id: str) -> str:
    """사용자별 발송 이력 키 생성"""
    return f"user:{user_id}:send_history"


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
    "google_calendar_refresh_token": "",
    "calendar_sources": "notion",  # "notion" | "google" | "notion,google"
}


def get_client() -> redis.Redis:
    redis_url = os.environ["REDIS_URL"]
    return redis.from_url(redis_url, decode_responses=True)


def init_db():
    """호환성 유지 (사용 안 함)"""
    pass


def get_settings(user_id: str) -> dict:
    """사용자별 설정 조회"""
    client = get_client()
    key = _get_settings_key(user_id)
    if not client.exists(key):
        client.hset(key, mapping=DEFAULTS)
    raw = client.hgetall(key)
    settings = {**DEFAULTS, **raw}
    settings["notify_hour"] = int(settings["notify_hour"])
    settings["notify_minute"] = int(settings["notify_minute"])
    settings["last_sent_at"] = settings["last_sent_at"] or None
    settings["last_sent_status"] = settings["last_sent_status"] or None
    return settings


def update_general_settings(
    user_id: str,
    notion_token: str,
    notion_database_id: str,
    notion_date_property: str,
    notion_title_property: str,
    kakao_rest_api_key: str,
    kakao_client_secret: str,
    notify_hour: int,
    notify_minute: int,
):
    """사용자별 일반 설정 저장"""
    client = get_client()
    key = _get_settings_key(user_id)
    client.hset(
        key,
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


def update_kakao_refresh_token(user_id: str, token: str):
    """사용자별 카카오 토큰 저장"""
    client = get_client()
    key = _get_settings_key(user_id)
    client.hset(key, "kakao_refresh_token", token)


def update_google_calendar_refresh_token(user_id: str, token: str):
    """사용자별 Google Calendar 토큰 저장"""
    client = get_client()
    key = _get_settings_key(user_id)
    client.hset(key, "google_calendar_refresh_token", token)


def update_calendar_sources(user_id: str, sources: str):
    """활성화된 캘린더 소스 저장"""
    client = get_client()
    key = _get_settings_key(user_id)
    client.hset(key, "calendar_sources", sources)


def record_send_result(user_id: str, status: str, when: str):
    """발송 결과 기록"""
    client = get_client()
    key = _get_settings_key(user_id)
    client.hset(key, mapping={"last_sent_status": status, "last_sent_at": when})


def add_send_history(user_id: str, timestamp: str, status: str, source: str, message: str = ""):
    """
    사용자별 발송 기록 추가 (최근 100개만 유지)
    """
    import json
    client = get_client()
    history_key = _get_history_key(user_id)
    record = json.dumps({
        "timestamp": timestamp,
        "status": status,
        "source": source,
        "message": message,
    })
    client.lpush(history_key, record)
    client.ltrim(history_key, 0, 99)


def get_send_history(user_id: str, limit: int = 30) -> list:
    """사용자별 발송 이력 조회"""
    import json
    client = get_client()
    history_key = _get_history_key(user_id)
    raw_records = client.lrange(history_key, 0, limit - 1)
    return [json.loads(r) for r in raw_records]


def get_send_statistics(user_id: str) -> dict:
    """사용자별 발송 통계 조회"""
    from datetime import datetime, timedelta
    from zoneinfo import ZoneInfo

    history = get_send_history(user_id, limit=100)
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

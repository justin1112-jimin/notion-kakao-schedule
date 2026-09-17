import os
from typing import Optional

import redis

def _get_settings_key(user_id: str) -> str:
    """사용자별 설정 키 생성"""
    return f"user:{user_id}:settings"


def _get_history_key(user_id: str) -> str:
    """사용자별 발송 이력 키 생성"""
    return f"user:{user_id}:send_history"


ALL_USERS_KEY = "all_user_ids"


DEFAULTS = {
    "notion_token": "",
    "notion_database_id": "",
    "notion_date_property": "날짜",
    "notion_title_property": "이름",
    "kakao_refresh_token": "",
    "notify_hour": "8",
    "notify_minute": "0",
    "last_sent_at": "",
    "last_sent_status": "",
    "google_calendar_refresh_token": "",
    "calendar_sources": "notion",  # "notion" | "google" | "notion,google"
    "notion_last_success_at": "",
    "google_calendar_last_success_at": "",
}


_client: Optional[redis.Redis] = None


def get_client() -> redis.Redis:
    """Redis 클라이언트 싱글턴 (최초 호출 시점에만 REDIS_URL을 읽고 연결을 재사용).

    이전엔 호출할 때마다 새 연결을 만들어서 커넥션 낭비 + 타임아웃 미설정으로
    Redis 응답이 느려지면 요청이 무한정 대기할 수 있었음.
    """
    global _client
    if _client is None:
        redis_url = os.environ["REDIS_URL"]
        _client = redis.from_url(
            redis_url,
            decode_responses=True,
            socket_timeout=5,
            socket_connect_timeout=5,
        )
    return _client


def init_db():
    """호환성 유지 (사용 안 함)"""
    pass


def get_settings(user_id: str) -> dict:
    """사용자별 설정 조회 (조회 시점에 전체 사용자 목록에도 등록)"""
    client = get_client()
    client.sadd(ALL_USERS_KEY, user_id)
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


def get_all_user_ids() -> list:
    """지금까지 설정을 조회한 적 있는 모든 사용자 ID 목록 (스케줄러/백업 트리거가 순회할 대상)"""
    client = get_client()
    return list(client.smembers(ALL_USERS_KEY))


def update_general_settings(user_id: str, notify_hour: int, notify_minute: int):
    """사용자별 일반 설정 저장"""
    client = get_client()
    key = _get_settings_key(user_id)
    client.hset(
        key,
        mapping={
            "notify_hour": str(notify_hour),
            "notify_minute": str(notify_minute),
        },
    )


def update_notion_token(user_id: str, token: str):
    """OAuth 인증 후 Notion 액세스 토큰 저장"""
    client = get_client()
    key = _get_settings_key(user_id)
    client.hset(key, "notion_token", token)


def update_notion_database(user_id: str, database_id: str, date_property: str, title_property: str):
    """선택한 데이터베이스 및 자동 감지된 속성명 저장"""
    client = get_client()
    key = _get_settings_key(user_id)
    client.hset(
        key,
        mapping={
            "notion_database_id": database_id,
            "notion_date_property": date_property,
            "notion_title_property": title_property,
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


def record_source_success(user_id: str, source_key: str, when: str):
    """캘린더 소스별 마지막 조회 성공 시각 기록 (연결은 돼있지만 실제로는
    죽어있는 토큰을 "✅ 연결됨" 배지만 보고는 구분할 수 없던 문제 대응)"""
    client = get_client()
    key = _get_settings_key(user_id)
    client.hset(key, f"{source_key}_last_success_at", when)


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

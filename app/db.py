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

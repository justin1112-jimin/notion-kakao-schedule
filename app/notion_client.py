from __future__ import annotations

import base64
import os
from datetime import datetime
from urllib.parse import urlencode
from zoneinfo import ZoneInfo

import requests

KST = ZoneInfo("Asia/Seoul")
NOTION_API_VERSION = "2022-06-28"
NOTION_OAUTH_AUTHORIZE_URL = "https://api.notion.com/v1/oauth/authorize"
NOTION_OAUTH_TOKEN_URL = "https://api.notion.com/v1/oauth/token"


def build_authorize_url(redirect_uri: str, state: str) -> str:
    params = {
        "client_id": os.environ["NOTION_CLIENT_ID"],
        "response_type": "code",
        "owner": "user",
        "redirect_uri": redirect_uri,
        "state": state,
    }
    return NOTION_OAUTH_AUTHORIZE_URL + "?" + urlencode(params)


def exchange_code_for_token(redirect_uri: str, code: str) -> dict:
    """authorization code를 (만료 없는) access token으로 교환"""
    credentials = base64.b64encode(
        f"{os.environ['NOTION_CLIENT_ID']}:{os.environ['NOTION_CLIENT_SECRET']}".encode()
    ).decode()
    resp = requests.post(
        NOTION_OAUTH_TOKEN_URL,
        headers={"Authorization": f"Basic {credentials}"},
        json={
            "grant_type": "authorization_code",
            "code": code,
            "redirect_uri": redirect_uri,
        },
        timeout=10,
    )
    resp.raise_for_status()
    return resp.json()


def list_shared_databases(notion_token: str) -> list[dict]:
    """OAuth 동의 시 사용자가 공유한 데이터베이스 목록 (id, title) 조회"""
    resp = requests.post(
        "https://api.notion.com/v1/search",
        headers={
            "Authorization": f"Bearer {notion_token}",
            "Notion-Version": NOTION_API_VERSION,
            "Content-Type": "application/json",
        },
        json={"filter": {"property": "object", "value": "database"}},
        timeout=10,
    )
    resp.raise_for_status()
    databases = []
    for db in resp.json()["results"]:
        title = "".join(p.get("plain_text", "") for p in db.get("title", []))
        databases.append({"id": db["id"], "title": title or "(제목 없음)"})
    return databases


def detect_properties(notion_token: str, database_id: str) -> tuple[str, str]:
    """데이터베이스 스키마에서 title/date 속성명을 타입 기준으로 자동 감지"""
    resp = requests.get(
        f"https://api.notion.com/v1/databases/{database_id}",
        headers={
            "Authorization": f"Bearer {notion_token}",
            "Notion-Version": NOTION_API_VERSION,
        },
        timeout=10,
    )
    resp.raise_for_status()
    properties = resp.json()["properties"]

    title_property = next(name for name, prop in properties.items() if prop["type"] == "title")
    date_property = next(
        (name for name, prop in properties.items() if prop["type"] == "date"), None
    )
    if not date_property:
        raise ValueError("이 데이터베이스에는 날짜(date) 속성이 없습니다.")
    return date_property, title_property


def get_today_schedule(
    notion_token: str,
    database_id: str,
    date_property: str,
    title_property: str,
) -> list[dict]:
    today = datetime.now(KST).strftime("%Y-%m-%d")

    url = f"https://api.notion.com/v1/databases/{database_id}/query"
    headers = {
        "Authorization": f"Bearer {notion_token}",
        "Notion-Version": NOTION_API_VERSION,
        "Content-Type": "application/json",
    }
    payload = {
        "filter": {
            "property": date_property,
            "date": {"equals": today},
        },
        "sorts": [{"property": date_property, "direction": "ascending"}],
    }

    resp = requests.post(url, headers=headers, json=payload, timeout=10)
    resp.raise_for_status()
    results = resp.json()["results"]

    items = []
    for page in results:
        props = page["properties"]
        title = _extract_title(props.get(title_property, {}))
        time_str = _extract_time(props.get(date_property, {}))
        items.append({"title": title, "time": time_str})
    return items


def _extract_title(prop: dict) -> str:
    if prop.get("type") == "title":
        parts = prop.get("title", [])
        return "".join(p.get("plain_text", "") for p in parts) or "(제목 없음)"
    return "(제목 없음)"


def _extract_time(prop: dict) -> str | None:
    if prop.get("type") != "date":
        return None
    date_obj = prop.get("date")
    if not date_obj or not date_obj.get("start"):
        return None
    start = date_obj["start"]
    if "T" in start:
        dt = datetime.fromisoformat(start)
        return dt.strftime("%H:%M")
    return None


def format_message(items: list[dict]) -> str:
    today = datetime.now(KST)
    weekday_kr = ["월", "화", "수", "목", "금", "토", "일"][today.weekday()]
    header = f"📅 {today.strftime('%Y년 %m월 %d일')} ({weekday_kr}) 오늘의 일정"

    if not items:
        return f"{header}\n\n오늘은 등록된 일정이 없어요. 편안한 하루 보내세요 🙂"

    timed = sorted([i for i in items if i["time"]], key=lambda x: x["time"])
    all_day = [i for i in items if not i["time"]]

    lines = [header, ""]
    for i in timed:
        lines.append(f"⏰ {i['time']}  {i['title']}")
    for i in all_day:
        lines.append(f"• {i['title']}")

    return "\n".join(lines)

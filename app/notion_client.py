from __future__ import annotations

from datetime import datetime
from zoneinfo import ZoneInfo

import requests

KST = ZoneInfo("Asia/Seoul")
NOTION_API_VERSION = "2022-06-28"


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

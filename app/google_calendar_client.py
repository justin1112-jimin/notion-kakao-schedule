import os
import requests
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

KST = ZoneInfo("Asia/Seoul")


def build_calendar_authorize_url(redirect_uri: str, state: str) -> str:
    """Google Calendar OAuth 인가 URL 생성"""
    client_id = os.environ["GOOGLE_CLIENT_ID"]
    scopes = [
        "openid",
        "email",
        "profile",
        "https://www.googleapis.com/auth/calendar.readonly",
    ]
    scope_str = " ".join(scopes)
    return (
        f"https://accounts.google.com/o/oauth2/v2/auth?"
        f"client_id={client_id}&"
        f"redirect_uri={redirect_uri}&"
        f"response_type=code&"
        f"scope={scope_str}&"
        f"state={state}&"
        f"access_type=offline&"
        f"prompt=consent"
    )


def exchange_code_for_tokens(redirect_uri: str, code: str) -> dict:
    """Authorization code를 access/refresh token으로 교환"""
    response = requests.post(
        "https://oauth2.googleapis.com/token",
        data={
            "client_id": os.environ["GOOGLE_CLIENT_ID"],
            "client_secret": os.environ["GOOGLE_CLIENT_SECRET"],
            "code": code,
            "grant_type": "authorization_code",
            "redirect_uri": redirect_uri,
        },
    )
    response.raise_for_status()
    return response.json()


def refresh_access_token(refresh_token: str) -> dict:
    """Refresh token으로 새 access token 획득"""
    response = requests.post(
        "https://oauth2.googleapis.com/token",
        data={
            "client_id": os.environ["GOOGLE_CLIENT_ID"],
            "client_secret": os.environ["GOOGLE_CLIENT_SECRET"],
            "refresh_token": refresh_token,
            "grant_type": "refresh_token",
        },
    )
    response.raise_for_status()
    return response.json()


def get_today_events(access_token: str) -> list:
    """오늘 일정 조회"""
    today = datetime.now(KST).date()
    start = datetime.combine(today, datetime.min.time()).replace(tzinfo=KST).isoformat()
    end = datetime.combine(today + timedelta(days=1), datetime.min.time()).replace(tzinfo=KST).isoformat()

    response = requests.get(
        "https://www.googleapis.com/calendar/v3/calendars/primary/events",
        headers={"Authorization": f"Bearer {access_token}"},
        params={
            "timeMin": start,
            "timeMax": end,
            "singleEvents": True,
            "orderBy": "startTime",
        },
    )
    response.raise_for_status()
    return response.json().get("items", [])


def format_google_events(events: list) -> str:
    """Google Calendar 이벤트를 메시지 포맷으로 변환"""
    if not events:
        return ""

    lines = []
    for event in events:
        title = event.get("summary", "(제목 없음)")
        start = event.get("start", {})
        start_time = start.get("dateTime") or start.get("date")

        try:
            if "T" in start_time:
                dt = datetime.fromisoformat(start_time).astimezone(KST)
                time_str = dt.strftime("%H:%M")
                lines.append(f"• {title} ({time_str})")
            else:
                lines.append(f"• {title} (종일)")
        except:
            lines.append(f"• {title}")

    return "\n".join(lines)

import ipaddress
import socket
from datetime import datetime, timedelta
from urllib.parse import urljoin, urlparse
from zoneinfo import ZoneInfo

import icalendar
import recurring_ical_events
import requests

KST = ZoneInfo("Asia/Seoul")

ALLOWED_SCHEMES = {"http", "https"}
MAX_REDIRECTS = 5


class UnsafeUrlError(Exception):
    """사용자가 등록한 ICS URL이 내부망/사설 IP를 가리켜 SSRF 위험이 있을 때"""


def _assert_public_host(url: str):
    """URL의 스킴/호스트를 검증 — 사용자가 등록한 URL을 서버가 대신 fetch하는
    구조라, 내부망(Redis, 클라우드 메타데이터 서버 등)을 가리키는 URL을 그냥
    통과시키면 SSRF로 이어짐. 리다이렉트도 매 홉마다 재검증해야 이 체크를
    "일단 공개 URL로 리다이렉트 → 실제로는 내부로 재리다이렉트"로 우회할 수 없음."""
    parsed = urlparse(url)
    if parsed.scheme not in ALLOWED_SCHEMES:
        raise UnsafeUrlError(f"허용되지 않는 URL 스킴입니다: {parsed.scheme}")
    if not parsed.hostname:
        raise UnsafeUrlError("URL에 호스트가 없습니다")

    try:
        addrinfo = socket.getaddrinfo(parsed.hostname, parsed.port or (443 if parsed.scheme == "https" else 80))
    except socket.gaierror as e:
        raise UnsafeUrlError(f"호스트를 확인할 수 없습니다: {parsed.hostname}") from e

    for *_, sockaddr in addrinfo:
        ip = ipaddress.ip_address(sockaddr[0])
        if ip.is_private or ip.is_loopback or ip.is_link_local or ip.is_reserved or ip.is_multicast or ip.is_unspecified:
            raise UnsafeUrlError(f"내부/사설 네트워크를 가리키는 URL은 사용할 수 없습니다: {parsed.hostname}")


def _fetch(url: str, redirects_left: int = MAX_REDIRECTS) -> requests.Response:
    _assert_public_host(url)
    response = requests.get(url, timeout=10, allow_redirects=False)
    if response.is_redirect:
        if redirects_left <= 0:
            raise UnsafeUrlError("리다이렉트가 너무 많습니다")
        location = response.headers.get("Location")
        if not location:
            response.raise_for_status()
            return response
        return _fetch(urljoin(url, location), redirects_left - 1)
    response.raise_for_status()
    return response


def get_today_events(ical_url: str) -> list:
    """구독 중인 ICS 캘린더에서 오늘(KST) 발생하는 일정 조회.

    원본 ICS의 반복 일정(RRULE)은 규칙만 담고 있어서, 오늘 실제로 발생하는
    occurrence는 recurring_ical_events로 따로 전개해야 함 — 이걸 생략하고
    최초 DTSTART만 보면 매주 반복되는 일정 같은 게 최초 발생일 이후로는
    다시는 안 뜨는 조용한 버그가 생김.
    """
    if ical_url.startswith("webcal://"):
        ical_url = ical_url.replace("webcal://", "https://", 1)

    response = _fetch(ical_url)
    calendar = icalendar.Calendar.from_ical(response.content)

    today = datetime.now(KST).date()
    start = datetime.combine(today, datetime.min.time()).replace(tzinfo=KST)
    end = start + timedelta(days=1)

    occurrences = recurring_ical_events.of(calendar).between(start, end)
    events = []
    for component in occurrences:
        title = str(component.get("summary", "(제목 없음)"))
        dtstart = component.get("dtstart").dt
        all_day = not isinstance(dtstart, datetime)
        if not all_day and dtstart.tzinfo is None:
            dtstart = dtstart.replace(tzinfo=KST)
        events.append({"title": title, "start": dtstart, "all_day": all_day})

    events.sort(key=lambda e: (not e["all_day"], "" if e["all_day"] else e["start"].astimezone(KST).isoformat()))
    return events


def format_ical_events(events: list) -> str:
    """ICS 이벤트를 메시지 포맷으로 변환"""
    if not events:
        return ""

    lines = []
    for event in events:
        if event["all_day"]:
            lines.append(f"• {event['title']} (종일)")
        else:
            time_str = event["start"].astimezone(KST).strftime("%H:%M")
            lines.append(f"• {event['title']} ({time_str})")

    return "\n".join(lines)

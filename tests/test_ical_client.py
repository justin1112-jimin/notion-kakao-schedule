"""app/ical_client.py 회귀 테스트.

- 반복 일정(RRULE) 전개: recurring_ical_events 연동이 깨지면 매주 반복되는
  일정 같은 게 최초 발생일 이후로는 조용히 다시 안 뜨게 됨.
- SSRF 방지: 사용자가 등록한 ICS URL을 서버가 대신 fetch하는 구조라, 내부망
  (Redis, 클라우드 메타데이터 서버 등)을 가리키는 URL은 반드시 거부돼야 함.
  실제 DNS를 타지 않도록 모든 테스트에서 socket.getaddrinfo를 모킹한다.
"""

import socket
from datetime import datetime, timedelta
from unittest.mock import Mock, patch
from zoneinfo import ZoneInfo

import pytest

from app import ical_client

KST = ZoneInfo("Asia/Seoul")


def _addrinfo(ip="93.184.216.34", port=443):
    return [(socket.AF_INET, socket.SOCK_STREAM, 6, "", (ip, port))]


def _build_ics(today) -> bytes:
    today_str = today.strftime("%Y%m%d")
    tomorrow_str = (today + timedelta(days=1)).strftime("%Y%m%d")
    recur_start_str = (today - timedelta(weeks=10)).strftime("%Y%m%d")
    ics = f"""BEGIN:VCALENDAR
VERSION:2.0
PRODID:-//test//test//KO
BEGIN:VEVENT
UID:single-event-1
DTSTART:{today_str}T090000Z
DTEND:{today_str}T100000Z
SUMMARY:일회성 회의
END:VEVENT
BEGIN:VEVENT
UID:recurring-1
DTSTART:{recur_start_str}T020000Z
DTEND:{recur_start_str}T030000Z
RRULE:FREQ=WEEKLY;COUNT=1000
SUMMARY:주간 반복 일정
END:VEVENT
BEGIN:VEVENT
UID:allday-1
DTSTART;VALUE=DATE:{today_str}
DTEND;VALUE=DATE:{tomorrow_str}
SUMMARY:종일 이벤트
END:VEVENT
END:VCALENDAR
"""
    return ics.encode()


def _mock_response(content: bytes):
    response = Mock()
    response.content = content
    response.is_redirect = False
    response.raise_for_status = Mock()
    return response


def test_get_today_events_includes_single_and_recurring_and_allday():
    today = datetime.now(KST).date()
    with patch("app.ical_client.socket.getaddrinfo", return_value=_addrinfo()), \
         patch("app.ical_client.requests.get", return_value=_mock_response(_build_ics(today))):
        events = ical_client.get_today_events("https://example.com/calendar.ics")

    titles = {e["title"] for e in events}
    assert titles == {"일회성 회의", "주간 반복 일정", "종일 이벤트"}


def test_get_today_events_normalizes_webcal_scheme():
    today = datetime.now(KST).date()
    with patch("app.ical_client.socket.getaddrinfo", return_value=_addrinfo()), \
         patch("app.ical_client.requests.get", return_value=_mock_response(_build_ics(today))) as mock_get:
        ical_client.get_today_events("webcal://example.com/calendar.ics")

    assert mock_get.call_args[0][0] == "https://example.com/calendar.ics"


def test_format_ical_events_marks_allday_and_timed():
    today = datetime.now(KST).date()
    with patch("app.ical_client.socket.getaddrinfo", return_value=_addrinfo()), \
         patch("app.ical_client.requests.get", return_value=_mock_response(_build_ics(today))):
        events = ical_client.get_today_events("https://example.com/calendar.ics")

    message = ical_client.format_ical_events(events)
    assert "종일 이벤트 (종일)" in message
    assert "일회성 회의 (18:00)" in message  # 09:00 UTC == 18:00 KST


def test_format_ical_events_empty_list_returns_empty_string():
    assert ical_client.format_ical_events([]) == ""


@pytest.mark.parametrize(
    "private_ip",
    [
        "127.0.0.1",  # loopback
        "10.0.0.5",  # RFC1918 사설망
        "169.254.169.254",  # 클라우드 메타데이터 서버(AWS/GCP/Azure 공통)
        "::1",  # loopback (IPv6)
    ],
)
def test_get_today_events_rejects_private_or_internal_ip(private_ip):
    with patch("app.ical_client.socket.getaddrinfo", return_value=_addrinfo(private_ip)), \
         patch("app.ical_client.requests.get") as mock_get:
        with pytest.raises(ical_client.UnsafeUrlError):
            ical_client.get_today_events("https://internal.example.com/calendar.ics")

    mock_get.assert_not_called()


def test_get_today_events_rejects_non_http_scheme():
    with patch("app.ical_client.requests.get") as mock_get:
        with pytest.raises(ical_client.UnsafeUrlError):
            ical_client.get_today_events("file:///etc/passwd")

    mock_get.assert_not_called()


def test_get_today_events_rejects_redirect_to_private_ip():
    """공개 URL로 시작해도, 리다이렉트가 내부망으로 향하면 거부해야 한다
    (검증을 최초 URL에서만 하고 리다이렉트를 그대로 따라가면 우회당함)."""
    redirect_response = Mock()
    redirect_response.is_redirect = True
    redirect_response.headers = {"Location": "https://internal.example.com/secret.ics"}

    def fake_getaddrinfo(host, port):
        if host == "public.example.com":
            return _addrinfo("93.184.216.34")
        if host == "internal.example.com":
            return _addrinfo("10.0.0.9")
        raise AssertionError(f"unexpected host: {host}")

    with patch("app.ical_client.socket.getaddrinfo", side_effect=fake_getaddrinfo), \
         patch("app.ical_client.requests.get", side_effect=[redirect_response]) as mock_get:
        with pytest.raises(ical_client.UnsafeUrlError):
            ical_client.get_today_events("https://public.example.com/calendar.ics")

    mock_get.assert_called_once()

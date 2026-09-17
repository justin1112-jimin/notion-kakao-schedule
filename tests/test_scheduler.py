"""run_daily_job()의 캘린더 소스별 부분 실패 처리 회귀 테스트.

2026-09-17에 실제로 겪은 버그: Google Calendar 리프레시 토큰이 무효화됐을 때
그 예외가 잡히지 않고 그대로 전파되면서, 이미 조회에 성공한 Notion 일정까지
통째로 발송이 취소됐음. 이 파일은 그 버그가 재발하지 않는지 확인한다.
"""

from unittest.mock import patch

import pytest

from app import scheduler

BASE_SETTINGS = {
    "notion_token": "notion-token",
    "notion_database_id": "db-id",
    "notion_date_property": "날짜",
    "notion_title_property": "이름",
    "google_calendar_refresh_token": "google-refresh-token",
    "calendar_sources": "notion,google",
    "kakao_refresh_token": "kakao-refresh-token",
}


def test_partial_calendar_failure_still_sends_other_source():
    """Google Calendar 조회가 실패해도 Notion 일정은 정상 발송돼야 한다."""
    sent = {}
    with patch("app.scheduler.db.get_settings", return_value=BASE_SETTINGS), \
         patch("app.scheduler.db.update_kakao_refresh_token"), \
         patch("app.scheduler.db.record_send_result"), \
         patch("app.scheduler.db.add_send_history"), \
         patch("app.scheduler.db.record_source_success") as mock_record_success, \
         patch("app.scheduler.notion_client.get_today_schedule", return_value=["item"]), \
         patch("app.scheduler.notion_client.format_message", return_value="노션 일정 있음"), \
         patch(
             "app.scheduler.google_calendar_client.refresh_access_token",
             side_effect=Exception("400 Client Error: Bad Request"),
         ), \
         patch(
             "app.scheduler.kakao_client.refresh_kakao_access_token",
             return_value={"access_token": "a"},
         ), \
         patch(
             "app.scheduler.kakao_client.send_kakao_memo",
             side_effect=lambda at, msg, link: sent.update(message=msg),
         ):
        result = scheduler.run_daily_job("user1", source="manual")

    assert "노션 일정 있음" in result
    assert "Google Calendar 조회 실패" in result
    assert sent["message"] == result
    # 성공한 Notion만 last_success_at이 기록되고, 실패한 Google Calendar는 기록 안 됨
    mock_record_success.assert_called_once()
    assert mock_record_success.call_args[0][:2] == ("user1", "notion")


def test_all_calendar_sources_fail_raises():
    """활성화된 캘린더가 전부 실패하면 명확하게 예외를 던지고 발송하지 않는다."""
    with patch("app.scheduler.db.get_settings", return_value=BASE_SETTINGS), \
         patch("app.scheduler.db.record_send_result"), \
         patch("app.scheduler.db.add_send_history"), \
         patch("app.scheduler.db.record_source_success"), \
         patch(
             "app.scheduler.notion_client.get_today_schedule",
             side_effect=Exception("notion down"),
         ), \
         patch(
             "app.scheduler.google_calendar_client.refresh_access_token",
             side_effect=Exception("400 Client Error: Bad Request"),
         ), \
         patch("app.scheduler.kakao_client.send_kakao_memo") as mock_send:
        with pytest.raises(Exception, match="캘린더 조회 실패"):
            scheduler.run_daily_job("user1", source="manual")

    mock_send.assert_not_called()


def test_both_calendar_sources_succeed():
    """정상 케이스: 두 캘린더 모두 성공하면 경고 문구 없이 둘 다 메시지에 포함된다."""
    with patch("app.scheduler.db.get_settings", return_value=BASE_SETTINGS), \
         patch("app.scheduler.db.update_kakao_refresh_token"), \
         patch("app.scheduler.db.record_send_result"), \
         patch("app.scheduler.db.add_send_history"), \
         patch("app.scheduler.db.record_source_success"), \
         patch("app.scheduler.notion_client.get_today_schedule", return_value=["item"]), \
         patch("app.scheduler.notion_client.format_message", return_value="노션 일정"), \
         patch(
             "app.scheduler.google_calendar_client.refresh_access_token",
             return_value={"access_token": "g"},
         ), \
         patch("app.scheduler.google_calendar_client.get_today_events", return_value=["event"]), \
         patch(
             "app.scheduler.google_calendar_client.format_google_events",
             return_value="구글 일정",
         ), \
         patch(
             "app.scheduler.kakao_client.refresh_kakao_access_token",
             return_value={"access_token": "a"},
         ), \
         patch("app.scheduler.kakao_client.send_kakao_memo"):
        result = scheduler.run_daily_job("user1", source="manual")

    assert "노션 일정" in result
    assert "구글 일정" in result
    assert "조회 실패" not in result


def test_no_calendar_connected_raises():
    """Notion/Google Calendar 둘 다 미연결이면 NoCalendarConnectedError."""
    settings = {**BASE_SETTINGS, "notion_token": "", "google_calendar_refresh_token": ""}
    with patch("app.scheduler.db.get_settings", return_value=settings), \
         patch("app.scheduler.db.record_send_result"), \
         patch("app.scheduler.db.add_send_history"):
        with pytest.raises(scheduler.NoCalendarConnectedError):
            scheduler.run_daily_job("user1", source="manual")

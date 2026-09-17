"""db.get_client()가 싱글턴으로 동작하는지 확인.

이전엔 호출할 때마다 redis.from_url()로 새 연결을 만들었음 — 매 요청마다
불필요한 커넥션을 만드는 비용과, 재사용 없이 매번 새로 붙는 구조적 낭비가 있었음.
"""

from unittest.mock import patch

from app import db


def test_get_client_reuses_same_instance():
    db._client = None  # 다른 테스트에서 캐시된 싱글턴 초기화
    with patch.dict("os.environ", {"REDIS_URL": "redis://localhost:6379"}), \
         patch("app.db.redis.from_url") as mock_from_url:
        mock_from_url.return_value = "fake-client"

        first = db.get_client()
        second = db.get_client()

        assert first is second
        mock_from_url.assert_called_once()
    db._client = None

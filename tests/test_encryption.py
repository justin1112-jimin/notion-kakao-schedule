"""OAuth 토큰(notion_token/kakao_refresh_token/google_calendar_refresh_token)
Redis 저장 시 암호화(TOKEN_ENCRYPTION_KEY)가 선택적으로 동작하는지 확인.

TOKEN_ENCRYPTION_KEY가 없어도 기존처럼 평문으로 동작해야 하고(하위 호환),
있으면 저장 시 암호화되고 조회 시 자동으로 복호화돼야 한다. 이 키를 이번에
처음 켰을 때 이전에 평문으로 저장돼 있던 값을 읽어도 에러 없이 그대로
반환돼야 한다(migration 시나리오).
"""

from unittest.mock import patch

from cryptography.fernet import Fernet

from app import db

TEST_KEY = Fernet.generate_key().decode()


def _reset_fernet_singleton():
    db._fernet = None
    db._fernet_checked = False


def test_encrypt_decrypt_round_trip_when_key_set():
    _reset_fernet_singleton()
    with patch.dict("os.environ", {"TOKEN_ENCRYPTION_KEY": TEST_KEY}):
        encrypted = db._encrypt("secret-token")
        assert encrypted != "secret-token"
        assert db._decrypt(encrypted) == "secret-token"
    _reset_fernet_singleton()


def test_encrypt_is_noop_without_key():
    _reset_fernet_singleton()
    with patch.dict("os.environ", {}, clear=True):
        assert db._encrypt("secret-token") == "secret-token"
        assert db._decrypt("secret-token") == "secret-token"
    _reset_fernet_singleton()


def test_decrypt_falls_back_to_raw_value_for_legacy_plaintext():
    """TOKEN_ENCRYPTION_KEY를 이번에 처음 켰을 때, 이전에 평문으로 저장된
    값(Fernet 토큰이 아닌 값)을 읽어도 에러 없이 그대로 돌려줘야 한다."""
    _reset_fernet_singleton()
    with patch.dict("os.environ", {"TOKEN_ENCRYPTION_KEY": TEST_KEY}):
        assert db._decrypt("legacy-plaintext-token") == "legacy-plaintext-token"
    _reset_fernet_singleton()


def test_empty_value_passes_through_regardless_of_key():
    _reset_fernet_singleton()
    with patch.dict("os.environ", {"TOKEN_ENCRYPTION_KEY": TEST_KEY}):
        assert db._encrypt("") == ""
        assert db._decrypt("") == ""
    _reset_fernet_singleton()


def test_get_settings_decrypts_secret_fields():
    _reset_fernet_singleton()
    with patch.dict("os.environ", {"TOKEN_ENCRYPTION_KEY": TEST_KEY}):
        encrypted_notion = db._encrypt("notion-secret")
        stored = {**db.DEFAULTS, "notion_token": encrypted_notion}
        fake_client = type("FakeClient", (), {
            "sadd": lambda self, *a, **k: None,
            "exists": lambda self, *a, **k: True,
            "hgetall": lambda self, *a, **k: stored,
        })()
        with patch("app.db.get_client", return_value=fake_client):
            settings = db.get_settings("user1")
        assert settings["notion_token"] == "notion-secret"
    _reset_fernet_singleton()

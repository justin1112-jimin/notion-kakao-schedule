import os
import sqlite3

DB_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "data")
DB_PATH = os.path.join(DB_DIR, "app.db")


def get_conn() -> sqlite3.Connection:
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def init_db():
    os.makedirs(DB_DIR, exist_ok=True)
    conn = get_conn()
    try:
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS settings (
                id INTEGER PRIMARY KEY CHECK (id = 1),
                notion_token TEXT NOT NULL DEFAULT '',
                notion_database_id TEXT NOT NULL DEFAULT '',
                notion_date_property TEXT NOT NULL DEFAULT '날짜',
                notion_title_property TEXT NOT NULL DEFAULT '이름',
                kakao_rest_api_key TEXT NOT NULL DEFAULT '',
                kakao_client_secret TEXT NOT NULL DEFAULT '',
                kakao_refresh_token TEXT NOT NULL DEFAULT '',
                notify_hour INTEGER NOT NULL DEFAULT 8,
                notify_minute INTEGER NOT NULL DEFAULT 0,
                last_sent_at TEXT,
                last_sent_status TEXT
            )
            """
        )
        conn.execute("INSERT OR IGNORE INTO settings (id) VALUES (1)")
        conn.commit()
    finally:
        conn.close()


def get_settings() -> dict:
    conn = get_conn()
    try:
        row = conn.execute("SELECT * FROM settings WHERE id = 1").fetchone()
        return dict(row)
    finally:
        conn.close()


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
    conn = get_conn()
    try:
        conn.execute(
            """
            UPDATE settings SET
                notion_token = ?,
                notion_database_id = ?,
                notion_date_property = ?,
                notion_title_property = ?,
                kakao_rest_api_key = ?,
                kakao_client_secret = ?,
                notify_hour = ?,
                notify_minute = ?
            WHERE id = 1
            """,
            (
                notion_token,
                notion_database_id,
                notion_date_property,
                notion_title_property,
                kakao_rest_api_key,
                kakao_client_secret,
                notify_hour,
                notify_minute,
            ),
        )
        conn.commit()
    finally:
        conn.close()


def update_kakao_refresh_token(token: str):
    conn = get_conn()
    try:
        conn.execute("UPDATE settings SET kakao_refresh_token = ? WHERE id = 1", (token,))
        conn.commit()
    finally:
        conn.close()


def record_send_result(status: str, when: str):
    conn = get_conn()
    try:
        conn.execute(
            "UPDATE settings SET last_sent_status = ?, last_sent_at = ? WHERE id = 1",
            (status, when),
        )
        conn.commit()
    finally:
        conn.close()

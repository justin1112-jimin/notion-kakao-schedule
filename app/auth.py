import os
from urllib.parse import urlencode

import requests

GOOGLE_AUTH_URL = "https://accounts.google.com/o/oauth2/v2/auth"
GOOGLE_TOKEN_URL = "https://oauth2.googleapis.com/token"
GOOGLE_USERINFO_URL = "https://www.googleapis.com/oauth2/v3/userinfo"


def build_authorize_url(redirect_uri: str, state: str) -> str:
    params = {
        "client_id": os.environ["GOOGLE_CLIENT_ID"],
        "redirect_uri": redirect_uri,
        "response_type": "code",
        "scope": "openid email",
        "state": state,
        "prompt": "select_account",
    }
    return GOOGLE_AUTH_URL + "?" + urlencode(params)


def fetch_user_info(redirect_uri: str, code: str) -> dict:
    """Google OAuth 인증 후 사용자 정보 반환 (email, sub)"""
    data = {
        "client_id": os.environ["GOOGLE_CLIENT_ID"],
        "client_secret": os.environ["GOOGLE_CLIENT_SECRET"],
        "redirect_uri": redirect_uri,
        "code": code,
        "grant_type": "authorization_code",
    }
    token_resp = requests.post(GOOGLE_TOKEN_URL, data=data, timeout=10)
    token_resp.raise_for_status()
    access_token = token_resp.json()["access_token"]

    userinfo_resp = requests.get(
        GOOGLE_USERINFO_URL,
        headers={"Authorization": f"Bearer {access_token}"},
        timeout=10,
    )
    userinfo_resp.raise_for_status()
    info = userinfo_resp.json()
    return {
        "email": info.get("email"),
        "user_id": info.get("sub"),  # Google unique user ID
    }


def fetch_email(redirect_uri: str, code: str) -> str:
    """호환성 유지: fetch_user_info의 이메일만 반환"""
    return fetch_user_info(redirect_uri, code)["email"]

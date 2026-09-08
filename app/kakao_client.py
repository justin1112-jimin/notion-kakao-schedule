import json
import os
from urllib.parse import urlencode

import requests


def build_authorize_url(redirect_uri: str, state: str) -> str:
    params = {
        "client_id": os.environ["KAKAO_REST_API_KEY"],
        "redirect_uri": redirect_uri,
        "response_type": "code",
        "scope": "talk_message profile_nickname",
        "state": state,
    }
    return "https://kauth.kakao.com/oauth/authorize?" + urlencode(params)


def exchange_code_for_tokens(redirect_uri: str, code: str) -> dict:
    data = {
        "grant_type": "authorization_code",
        "client_id": os.environ["KAKAO_REST_API_KEY"],
        "redirect_uri": redirect_uri,
        "code": code,
    }
    client_secret = os.environ.get("KAKAO_CLIENT_SECRET", "")
    if client_secret:
        data["client_secret"] = client_secret

    resp = requests.post("https://kauth.kakao.com/oauth/token", data=data, timeout=10)
    resp.raise_for_status()
    return resp.json()


def refresh_kakao_access_token(refresh_token: str) -> dict:
    data = {
        "grant_type": "refresh_token",
        "client_id": os.environ["KAKAO_REST_API_KEY"],
        "refresh_token": refresh_token,
    }
    client_secret = os.environ.get("KAKAO_CLIENT_SECRET", "")
    if client_secret:
        data["client_secret"] = client_secret

    resp = requests.post("https://kauth.kakao.com/oauth/token", data=data, timeout=10)
    resp.raise_for_status()
    return resp.json()


def fetch_user_info(access_token: str) -> dict:
    """카카오 로그인 후 사용자 식별 정보 반환 (id, nickname)"""
    resp = requests.get(
        "https://kapi.kakao.com/v2/user/me",
        headers={"Authorization": f"Bearer {access_token}"},
        timeout=10,
    )
    resp.raise_for_status()
    data = resp.json()
    nickname = data.get("kakao_account", {}).get("profile", {}).get("nickname")
    return {"user_id": str(data["id"]), "nickname": nickname}


def send_kakao_memo(access_token: str, message: str):
    url = "https://kapi.kakao.com/v2/api/talk/memo/default/send"
    headers = {"Authorization": f"Bearer {access_token}"}
    template_object = {
        "object_type": "text",
        "text": message,
        "link": {"web_url": "https://notion.so", "mobile_web_url": "https://notion.so"},
    }
    resp = requests.post(
        url,
        headers=headers,
        data={"template_object": json.dumps(template_object)},
        timeout=10,
    )
    resp.raise_for_status()
    return resp.json()

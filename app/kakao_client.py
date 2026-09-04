import json
from urllib.parse import urlencode

import requests


def build_authorize_url(rest_api_key: str, redirect_uri: str) -> str:
    params = {
        "client_id": rest_api_key,
        "redirect_uri": redirect_uri,
        "response_type": "code",
        "scope": "talk_message",
    }
    return "https://kauth.kakao.com/oauth/authorize?" + urlencode(params)


def exchange_code_for_tokens(rest_api_key: str, client_secret: str, redirect_uri: str, code: str) -> dict:
    data = {
        "grant_type": "authorization_code",
        "client_id": rest_api_key,
        "redirect_uri": redirect_uri,
        "code": code,
    }
    if client_secret:
        data["client_secret"] = client_secret

    resp = requests.post("https://kauth.kakao.com/oauth/token", data=data, timeout=10)
    resp.raise_for_status()
    return resp.json()


def refresh_kakao_access_token(rest_api_key: str, refresh_token: str, client_secret: str) -> dict:
    data = {
        "grant_type": "refresh_token",
        "client_id": rest_api_key,
        "refresh_token": refresh_token,
    }
    if client_secret:
        data["client_secret"] = client_secret

    resp = requests.post("https://kauth.kakao.com/oauth/token", data=data, timeout=10)
    resp.raise_for_status()
    return resp.json()


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

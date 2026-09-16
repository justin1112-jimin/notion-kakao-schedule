import json
import os
import time
from urllib.parse import urlencode

import requests


def _post_with_retry(url: str, max_retries: int = 3, **kwargs) -> requests.Response:
    """카카오 API가 429(rate limit)를 반환하면 지수 백오프로 재시도.

    여러 사용자의 발송이 같은 순간(예: 다들 08:00으로 설정)에 몰려서
    앱 단위 초당 요청 한도에 걸리는 경우를 대비한 안전장치.
    """
    delay = 1.0
    for attempt in range(max_retries + 1):
        resp = requests.post(url, timeout=10, **kwargs)
        if resp.status_code == 429 and attempt < max_retries:
            time.sleep(delay)
            delay *= 2
            continue
        resp.raise_for_status()
        return resp


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

    resp = _post_with_retry("https://kauth.kakao.com/oauth/token", data=data)
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


def send_kakao_memo(access_token: str, message: str, link_url: str):
    url = "https://kapi.kakao.com/v2/api/talk/memo/default/send"
    headers = {"Authorization": f"Bearer {access_token}"}
    template_object = {
        "object_type": "text",
        "text": message,
        "link": {"web_url": link_url, "mobile_web_url": link_url},
        "button_title": "대시보드 보기",
    }
    resp = _post_with_retry(
        url,
        headers=headers,
        data={"template_object": json.dumps(template_object)},
    )
    return resp.json()

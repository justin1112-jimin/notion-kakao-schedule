---
name: setup-dev
description: 로컬 개발 환경을 자동으로 설정합니다. 처음 시작할 때 "개발 환경 설정", "로컬 실행 준비", "setup-dev" 등으로 한 번 실행하면 venv, pip, 패키지 설치가 모두 완료됩니다.
---

# setup-dev 스킬

로컬 개발 환경을 한 번에 준비합니다.

## 설정 항목

1. **Python 환경**
   - Python 버전 확인
   - venv (가상 환경) 생성

2. **패키지 설치**
   - pip 업그레이드
   - requirements.txt 패키지 설치

3. **환경 변수**
   - .env 파일 존재 여부 확인
   - 필수 변수 목록 표시

4. **Redis (선택사항)**
   - 로컬 Redis 서버 상태 확인

5. **프로젝트 구조**
   - 필수 파일 존재 여부 확인

## 실행

```bash
setup-dev
```

## 결과 예시

```
🛠️  개발 환경 설정 시작

📌 Python 버전 확인...
Python 3.11.0

📦 venv 생성 중...
✅ venv 생성 완료

🔌 venv 활성화...
✅ venv 활성화 완료

📥 pip 업그레이드...
✅ pip 업그레이드 완료

📚 requirements.txt 설치 중...
✅ 패키지 설치 완료

🔐 환경 변수 확인...
✅ .env 파일 존재

📂 프로젝트 구조 확인...
  ✅ app/main.py
  ✅ app/db.py
  ✅ app/scheduler.py
  ✅ requirements.txt

✨ 개발 환경 설정 완료!

🚀 다음 단계:
  1. .env 파일 확인/수정
  2. uvicorn app.main:app --reload
  3. http://localhost:8000 접속 → /login에서 카카오로 로그인
```

## 필수 환경변수

.env 파일에 다음 변수들이 필요합니다 (로그인=카카오 로그인, Notion/Google Calendar는 OAuth):

```
REDIS_URL=redis://localhost:6379
SESSION_SECRET_KEY=
KAKAO_REST_API_KEY=
KAKAO_CLIENT_SECRET=
NOTION_CLIENT_ID=
NOTION_CLIENT_SECRET=
GOOGLE_CLIENT_ID=
GOOGLE_CLIENT_SECRET=
```

로컬 개발에서는 `REDIS_URL`을 생략하고 싶으시면, 그 부분만 Render의 값을 복사해서 넣으면 됩니다. `GOOGLE_CLIENT_ID`/`GOOGLE_CLIENT_SECRET`은 로그인용이 아니라 선택 기능인 Google Calendar 연동에만 쓰입니다.

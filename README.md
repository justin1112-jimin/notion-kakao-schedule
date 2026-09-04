# Notion → 카카오톡 오늘 일정 알림

Notion 데이터베이스에서 오늘 날짜의 일정을 가져와, 매일 아침 카카오톡 "나에게 보내기"로 요약해서 보내주는 개인용 자동화 도구입니다.

FastAPI 웹앱으로 만들어져 있어 브라우저에서 Notion/카카오 연동과 알림 시각을 설정합니다. 나중에 Capacitor로 감싸서 하이브리드 앱(iOS/Android)으로 배포하는 걸 목표로 설계되어 있습니다.

## 폴더 구성
```
notion-kakao-schedule/
├── app/
│   ├── main.py            # FastAPI 앱, 라우트
│   ├── db.py               # Redis(Upstash) 설정 저장소
│   ├── notion_client.py     # Notion 조회 + 메시지 포맷팅
│   ├── kakao_client.py      # 카카오 OAuth + 메시지 전송
│   ├── scheduler.py         # APScheduler 기반 매일 알림 스케줄러
│   └── templates/settings.html
├── requirements.txt
└── _v1_backup/               # (gitignore) v1 로컬 스크립트 백업, 배포엔 미포함
```

## 아키텍처

```
브라우저 (설정 UI)
      ↓
FastAPI 웹서비스 (Render) ── 매일 지정 시각에 내부 스케줄러(APScheduler)가 실행
      ↓                                      ↓
Upstash Redis (설정/토큰 저장)      Notion 조회 → 메시지 포맷 → 카카오 전송
```

- 설정(Notion 토큰, 카카오 토큰, 알림 시각)은 `.env`가 아니라 **Redis**에 저장됩니다. Render 무료 웹서비스는 디스크가 임시(재배포 시 초기화)라서 별도 저장소가 필요합니다.
- 매일 알림 발송은 macOS launchd가 아니라 **앱 프로세스 내부 스케줄러**가 담당합니다. 즉 서버가 켜져 있어야 작동합니다.
- Render 무료 플랜은 일정 시간 요청이 없으면 서버가 잠드는데(spin down), 이러면 스케줄러도 같이 멈춥니다. **UptimeRobot 같은 무료 핑 서비스로 5분마다 `/settings`를 호출**해서 항상 깨어있게 해줘야 합니다.

## 로컬 개발

```bash
cd notion-kakao-schedule
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt
```

Upstash 등에서 발급받은 Redis 연결 URL을 환경변수로 넣고 실행합니다.
```bash
REDIS_URL="rediss://default:비밀번호@호스트:포트" uvicorn app.main:app --reload --port 8000
```

브라우저에서 http://localhost:8000/settings 접속 → Notion/카카오 값 입력 → 저장.

## Notion 연동 설정

1. https://www.notion.so/my-integrations 에서 **New integration** 생성 → Internal Integration Token 복사
2. 일정이 있는 Notion 데이터베이스 페이지 우측 상단 `•••` → **연결(Connections)** → 방금 만든 통합 추가 (빼먹으면 API가 데이터베이스를 못 읽습니다)
3. 데이터베이스 URL에서 32자리 ID 복사
4. 본인 데이터베이스의 실제 속성 이름(날짜 속성, 제목 속성)을 확인
5. 이 값들을 `/settings` 페이지 폼에 입력 후 저장

## 카카오 개발자 앱 설정

1. https://developers.kakao.com → 애플리케이션 추가 → **앱 키 > REST API 키** 확인
2. **제품 설정 > 카카오 로그인** 활성화
3. **Redirect URI**에 앱이 실제로 떠 있는 주소 + `/kakao/callback` 추가
   - 로컬: `http://localhost:8000/kakao/callback`
   - 배포: `https://<render-서비스명>.onrender.com/kakao/callback`
4. **동의항목**에서 "카카오톡 메시지 전송(talk_message)"을 선택 동의로 활성화
   - 참고: 개인 개발자 계정은 별도 심사 없이 본인 카카오 계정으로 "나에게 보내기"를 바로 사용할 수 있습니다.
5. `/settings` 페이지에 REST API 키 입력 후 저장 → **"카카오 연결"** 버튼으로 로그인/동의

## Render 배포

1. GitHub에 이 저장소 push (private 권장 — 토큰은 코드에 없지만 개인용 도구라 공개할 이유 없음)
2. Render → New → **Web Service** → 이 저장소 연결
3. Build Command: `pip install -r requirements.txt`
4. Start Command: `uvicorn app.main:app --host 0.0.0.0 --port $PORT`
5. Instance Type: Free
6. Environment Variables에 `REDIS_URL` 추가 (Upstash Redis의 TCP 연결 URL, `rediss://...`)
7. Deploy

### Upstash Redis (무료, 만료 없음)

Render 무료 Postgres는 30일 후 만료되지만, Upstash Redis 무료 티어는 계속 무료로 유지되고 저장할 데이터도 설정 한 덩어리뿐이라 이쪽이 이 프로젝트엔 더 맞습니다.

1. https://upstash.com 가입 → Create Database (Redis, Free)
2. Region은 Render 웹서비스와 같은 리전으로 맞추기
3. "Connect" 화면의 **TCP 탭**에서 연결 URL(`rediss://default:...`) 복사 → Render 환경변수 `REDIS_URL`에 붙여넣기

### 항상 깨어있게 유지하기 (UptimeRobot)

1. https://uptimerobot.com 가입 (무료)
2. Add New Monitor → HTTP(s) → URL: `https://<render-서비스명>.onrender.com/settings`
3. Interval: 5분

## 사용법

배포/로컬 실행 후 `/settings` 페이지에서:
- **저장**: Notion/카카오 설정, 알림 시각 저장
- **카카오 연결**: 카카오 OAuth 로그인/동의
- **오늘 일정 미리보기**: 전송 없이 오늘 일정만 확인
- **지금 테스트 전송**: 실제로 카카오톡 메시지 즉시 발송

## 참고 사항

- 카카오 액세스 토큰은 6시간마다 만료되지만, 발송 시마다 refresh token으로 자동 갱신합니다.
- 리프레시 토큰이 회전(rotate)되면 새 값이 자동으로 Redis에 저장됩니다.
- v1(로컬 스크립트 + macOS launchd 버전)은 `_v1_backup/`에 보관되어 있으며 더 이상 사용하지 않습니다.

## 다음 단계 (v2 로드맵)

- Capacitor로 이 웹 UI를 감싸서 iOS/Android 하이브리드 앱으로 배포
- Google Calendar / Apple Calendar 등 추가 캘린더 어댑터

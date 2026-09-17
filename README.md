# Notion → 카카오톡 오늘 일정 알림

**버전**: v2.3 · [소개 페이지](https://justin1112-jimin.github.io/notion-kakao-schedule/)

Notion(과 선택적으로 Google Calendar)에서 오늘 날짜의 일정을 가져와, 매일 아침 카카오톡 "나에게 보내기"로 요약해서 보내주는 개인용 자동화 도구입니다.

FastAPI 웹앱으로 만들어져 있고, 카카오 로그인 하나로 신원 확인과 메시지 발송 동의를 동시에 처리합니다(로그인 = 카카오 연결). Notion/Google Calendar도 전부 OAuth 연결이라 API 키를 직접 복사-붙여넣기할 필요가 없습니다. 나중에 Capacitor로 감싸서 하이브리드 앱(iOS/Android)으로 배포하는 걸 목표로 설계되어 있습니다.

## 폴더 구성
```
notion-kakao-schedule/
├── app/
│   ├── main.py                    # FastAPI 앱, 전체 라우트 + 로깅/Sentry 초기화
│   ├── db.py                      # Redis(Upstash) 저장소 (싱글턴 클라이언트, 토큰 암호화, 사용자별 설정/발송 이력)
│   ├── notion_client.py           # Notion OAuth + 일정 조회 (date/title 속성 자동 감지)
│   ├── kakao_client.py            # 카카오 로그인 + 메시지 전송 (429 재시도/백오프 포함)
│   ├── google_calendar_client.py  # Google Calendar OAuth + 일정 조회 (선택 기능)
│   ├── scheduler.py               # APScheduler 기반 매일 알림 스케줄러, 캘린더 소스별 부분 실패 처리
│   ├── static/                    # 템플릿 공용 theme.css/theme.js (라이트·다크 토큰, 다크모드 토글)
│   └── templates/
│       ├── login.html             # 로그인 페이지 (카카오)
│       ├── settings.html          # 설정 페이지 (Notion/카카오/Google Calendar 연결)
│       ├── dashboard.html         # 발송 이력 대시보드
│       └── status.html            # 저장된 설정 vs 스케줄러 실제 예약 시각 비교
├── docs/                          # GitHub Pages 소개 페이지 (index.html/guide.html/style.css)
├── tests/                         # pytest 회귀 테스트 — push/PR마다 CI로 자동 실행
├── requirements.txt
├── requirements-dev.txt           # requirements.txt + pytest
└── _v1_backup/               # (gitignore) v1 로컬 스크립트 백업, 배포엔 미포함
```

## 아키텍처

```
브라우저
      ↓
   /login (카카오 로그인 = 카카오 연결)
      ↓
FastAPI 웹서비스 (Render) ── 매일 지정 시각에 내부 스케줄러(APScheduler)가 실행
      ↓                                      ↓
Upstash Redis (사용자별 설정/토큰 저장)   Notion + Google Calendar 조회 → 메시지 포맷 → 카카오 전송
```

- 설정(Notion/카카오/Google Calendar 토큰, 알림 시각)은 `.env`가 아니라 **Redis**에 저장됩니다. Render 무료 웹서비스는 디스크가 임시(재배포 시 초기화)라서 별도 저장소가 필요합니다.
- 매일 알림 발송은 macOS launchd가 아니라 **앱 프로세스 내부 스케줄러**가 담당합니다. 즉 서버가 켜져 있어야 작동합니다.
- Render 무료 플랜은 일정 시간 요청이 없으면 서버가 잠드는데(spin down), 이러면 스케줄러도 같이 멈춥니다. **UptimeRobot 같은 무료 핑 서비스로 5분마다 `/settings`를 호출**해서 항상 깨어있게 해줘야 합니다.

## 로컬 개발

```bash
cd notion-kakao-schedule
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt
```

아래 환경변수를 넣고 실행합니다 (전부 아래 "환경변수" 절 참고):
```bash
REDIS_URL="rediss://default:비밀번호@호스트:포트" \
SESSION_SECRET_KEY="아무-랜덤-문자열" \
KAKAO_REST_API_KEY="..." KAKAO_CLIENT_SECRET="..." \
NOTION_CLIENT_ID="..." NOTION_CLIENT_SECRET="..." \
GOOGLE_CLIENT_ID="..." GOOGLE_CLIENT_SECRET="..." \
  uvicorn app.main:app --reload --port 8000
```

브라우저에서 http://localhost:8000 접속 → `/login`으로 자동 리다이렉트 → **카카오로 로그인** (로그인 자체가 카카오 메시지 발송 동의까지 포함) → `/settings`에서 Notion 연결.

## 테스트

```bash
pip install -r requirements-dev.txt
pytest tests/ -v
```

실제 Redis/외부 API 없이 전부 mock으로 도는 회귀 테스트입니다(`scheduler.py`의 캘린더 소스별 부분 실패 처리, `db.py`의 Redis 클라이언트 싱글턴 동작 등). `main` 브랜치에 push하거나 PR을 열면 GitHub Actions(`.github/workflows/test.yml`)가 자동으로 실행합니다.

## 환경변수

| 변수 | 용도 |
|---|---|
| `REDIS_URL` | Upstash Redis 연결 문자열 |
| `SESSION_SECRET_KEY` | 세션 쿠키 서명용 랜덤 문자열 (한 번 생성 후 고정) |
| `KAKAO_REST_API_KEY` | 카카오 로그인 + 메시지 전송용 앱 키 (앱 소유자가 한 번만 발급, 모든 사용자가 공유) |
| `KAKAO_CLIENT_SECRET` | (선택) 같은 카카오 앱의 Client Secret |
| `NOTION_CLIENT_ID` / `NOTION_CLIENT_SECRET` | Notion OAuth 공개 통합 |
| `GOOGLE_CLIENT_ID` / `GOOGLE_CLIENT_SECRET` | Google Calendar 연동용 (로그인용 아님) |
| `CRON_SECRET` | GitHub Actions 백업 트리거 인증 (배포 시에만 필요) |
| `SENTRY_DSN` | (선택) [Sentry](https://sentry.io) 에러 트래킹 — 비워두면 비활성화 |
| `LOG_LEVEL` | (선택) 로그 레벨, 기본값 `INFO` |
| `TOKEN_ENCRYPTION_KEY` | (선택, 강력 권장) OAuth 토큰 Redis 저장 시 암호화 키 — 비워두면 평문 저장(하위 호환) |

## 카카오 개발자 앱 설정 (필수, 앱 소유자가 한 번만)

1. https://developers.kakao.com → 애플리케이션 추가 → **앱 키 > REST API 키** 확인
2. **제품 설정 > 카카오 로그인** 활성화
3. **Redirect URI**에 `/auth/kakao/callback` 등록
   - 로컬: `http://localhost:8000/auth/kakao/callback`
   - 배포: `https://<render-서비스명>.onrender.com/auth/kakao/callback`
4. **동의항목**에서 "카카오톡 메시지 전송(talk_message)"을 **필수 동의**로 설정 (선택 동의로 두면 로그인은 되는데 메시지 발송 권한이 빠질 수 있음)
5. REST API 키(및 필요 시 Client Secret)를 `KAKAO_REST_API_KEY`/`KAKAO_CLIENT_SECRET` 환경변수에 설정

앱 하나만 만들면 됩니다 — 사용자는 그냥 `/login`에서 **"카카오로 로그인"** 버튼만 누르면 자동으로 메시지 발송 동의까지 끝납니다.

## Notion 연동 설정 (필수, 앱 소유자가 한 번만)

1. https://www.notion.so/my-integrations → 새 통합 생성
2. 유형을 **Public (OAuth)**으로 설정 (Internal이면 안 됨)
3. Capabilities에서 "Read content" 활성화
4. Redirect URI에 `/notion/callback` 등록 (배포: `https://<render-서비스명>.onrender.com/notion/callback`)
5. Client ID/Secret을 `NOTION_CLIENT_ID`/`NOTION_CLIENT_SECRET` 환경변수에 설정

사용자는 `/settings`에서 **"Notion 연결"** 버튼을 누르고 Notion 자체 페이지 선택 화면에서 데이터베이스를 고르면 끝입니다. 날짜/제목 속성명은 스키마에서 타입 기준으로 자동 감지되므로 직접 입력할 필요가 없습니다.

## Google Calendar 연동 설정 (선택)

1. https://console.cloud.google.com/ → 프로젝트 생성 → OAuth 동의 화면 설정(User Type: 외부, 테스트 상태 유지)
2. OAuth 클라이언트 ID(웹 애플리케이션) 생성, Redirect URI에 `/google-calendar/callback` 등록
3. Google Calendar API 활성화
4. Client ID/Secret을 `GOOGLE_CLIENT_ID`/`GOOGLE_CLIENT_SECRET` 환경변수에 설정

사용자는 `/settings`에서 "Google Calendar 연결" 버튼으로 선택적으로 추가할 수 있습니다.

## Render 배포

1. GitHub에 이 저장소 push (fork한 저장소도 가능)
2. Render → New → **Web Service** → 이 저장소 연결
3. Build Command: `pip install -r requirements.txt`
4. Start Command: `uvicorn app.main:app --host 0.0.0.0 --port $PORT`
5. Instance Type: Free
6. Environment Variables에 위 "환경변수" 절의 항목 **전부** 추가
7. Deploy

**순서 주의**: 환경변수를 먼저 추가(자동 재배포 1회 발생)한 뒤 코드를 push할 것 — 반대 순서면 env var가 없어서 해당 라우트가 `KeyError`로 500 납니다.

### Upstash Redis (무료, 만료 없음)

Render 무료 Postgres는 30일 후 만료되지만, Upstash Redis 무료 티어는 계속 무료로 유지되고 저장할 데이터도 설정 한 덩어리뿐이라 이쪽이 이 프로젝트엔 더 맞습니다.

1. https://upstash.com 가입 → Create Database (Redis, Free)
2. Region은 Render 웹서비스와 같은 리전으로 맞추기
3. "Connect" 화면의 **TCP 탭**에서 연결 URL(`rediss://default:...`) 복사 → Render 환경변수 `REDIS_URL`에 붙여넣기

### 항상 깨어있게 유지하기 (UptimeRobot)

1. https://uptimerobot.com 가입 (무료)
2. Add New Monitor → HTTP(s) → URL: `https://<render-서비스명>.onrender.com/settings`
3. Interval: 5분

### 발송 실패 안전망 (GitHub Actions 백업 트리거, 선택)

앱 내부 스케줄러가 발송에 실패해도 알아챌 수 있도록, GitHub Actions가 10분 뒤 `/internal/run-daily`를 호출해 재시도하고 실패 시 저장소 소유자에게 이메일로 알려주는 안전망입니다(`.github/workflows/daily-notify-backup.yml`).

1. GitHub 저장소 Settings → Secrets and variables → Actions
   - **Secrets** 탭에 `CRON_SECRET` 추가 (Render 환경변수와 동일한 값)
   - **Variables** 탭에 `APP_URL` 추가 (예: `https://<render-서비스명>.onrender.com`, 끝 슬래시 없이)
2. 별도 설정 없이 매일 08:10 KST에 자동 실행됩니다.

## 사용법

배포/로컬 실행 후:
- **로그인**: `/login`에서 카카오로 로그인 (= 메시지 발송 동의까지 자동 완료)
- **Notion 연결**: `/settings`에서 버튼 클릭 → 데이터베이스 선택 (속성 자동 감지)
- **Google Calendar 연결**: `/settings`에서 선택적으로 추가
- **저장**: 알림 시각 저장
- **오늘 일정 미리보기**: 전송 없이 오늘 일정만 확인
- **지금 테스트 전송**: 실제로 카카오톡 메시지 즉시 발송
- **대시보드**: `/dashboard`에서 발송 이력/성공률 확인

## 참고 사항

- 카카오 액세스 토큰은 6시간마다 만료되지만, 발송 시마다 refresh token으로 자동 갱신합니다.
- 리프레시 토큰이 회전(rotate)되면 새 값이 자동으로 Redis에 저장됩니다.
- v1(로컬 스크립트 + macOS launchd 버전)은 `_v1_backup/`에 보관되어 있으며 더 이상 사용하지 않습니다.
- 여러 사용자가 각자 로그인해서 각자의 Notion/카카오/Google Calendar를 독립적으로 연결할 수 있습니다(Redis 키가 `user:{카카오 id}:*`로 격리됨).

## 변경 이력

- **v2.3**: 보안/UX/접근성 정리 릴리스.
  - OAuth 토큰(Notion/카카오/Google Calendar) Redis 저장 시 선택적 암호화(`TOKEN_ENCRYPTION_KEY`, Fernet) 추가 — 하위 호환(키 없으면 기존처럼 평문), 기존 평문 데이터도 무중단으로 점진 마이그레이션
  - 로그인 에러 메시지를 `/login?error=...` 쿼리 파라미터 대신 세션 기반 1회성 플래시로 변경 (새로고침/URL 공유 시 반복 노출되던 문제 해결)
  - 다크모드 토글을 `<a>`에서 `<button aria-label="다크모드 전환">`으로 변경 (스크린리더 접근성)
  - `login/settings/dashboard/status` 4개 템플릿에 중복돼 있던 CSS 컬러 토큰과 다크모드 스크립트를 `app/static/theme.css`/`theme.js`로 추출
- **v2.2**: 신뢰성/관측성 강화 릴리스.
  - `run_daily_job()`이 Notion/Google Calendar 중 한쪽 조회에 실패해도 나머지 소스는 정상 발송하도록 수정 (이전엔 한쪽 실패가 이미 조회된 내용까지 통째로 막아버렸음)
  - Google Calendar "재연결" 버튼이 토큰이 살아있는 것처럼 보일 때(실제로는 만료됐어도) 화면에서 사라지던 버그 수정, 연결 배지 옆에 "마지막 조회 성공" 시각 표시
  - `google_calendar_client.py`의 누락된 API 요청 timeout 추가
  - Redis 클라이언트를 싱글턴으로 전환 + 타임아웃 추가 (`db.py`)
  - `logging` 모듈 기반 구조화 로깅 + 선택적 [Sentry](https://sentry.io) 에러 트래킹(`SENTRY_DSN`) 추가
  - pytest 회귀 테스트 + GitHub Actions CI(`test.yml`) 추가
  - GitHub Pages 소개/가이드 페이지 공개
- **v2.1**: 카카오 API 요청이 순간적으로 몰릴 때(예: 여러 사용자가 같은 알림 시각으로 설정)를 대비한 안전장치 추가 — 429(rate limit) 응답 시 지수 백오프로 자동 재시도(`kakao_client.py`), 백업 트리거(`/internal/run-daily`)가 여러 사용자를 순회할 때 사용자 간 짧은 딜레이를 둠.
- **v2.0**: 발송 이력 대시보드, 다크모드, 다중 사용자 자동 발송, `/status` 상태 확인 페이지, 오픈소스 공개.

## 다음 단계 (v3 백로그)

- 대시보드 시각화 강화 (Chart.js: 일별 그래프, 출처별 파이 차트 등)
- Capacitor로 이 웹 UI를 감싸서 iOS/Android 하이브리드 앱으로 배포

## 기여

이슈/PR 환영합니다. 코드 스타일이나 별도 절차는 아직 정해진 게 없으니, 기존 코드 패턴(예: 새 OAuth 연동 추가 시 `os.environ["X"]`는 모듈 최상단이 아니라 함수 내부에서 읽기)을 참고해 자유롭게 제안해주세요.

## 라이선스

[MIT](LICENSE)

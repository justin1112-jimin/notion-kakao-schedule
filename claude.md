# CLAUDE.md

## 프로젝트 개요
Notion에서 **오늘 날짜의 일정**을 가져와, 매일 아침 **카카오톡 "나에게 보내기"**로 요약 메시지를 자동 전송하는 개인용 자동화 도구.

### 버전 관리
- **구형 v1 (은퇴, `_v1_backup/`)**: 로컬 Python 스크립트 + macOS launchd
- **현재 v1 (완료, 2026-09-07)**: FastAPI 웹앱(Render 배포) + Notion/카카오 OAuth + Google 로그인 + GitHub Actions 백업 트리거 — 기본 기능 완성
- **현재 v2 (진행 중, 2026-09-07~)**: 발송 이력 대시보드 + 시각화/필터링/다크모드 고도화 → 최종 목표: Capacitor로 하이브리드 앱 패키징(iOS/Android)

---

## 현재 상태 요약 (2026-09-09 기준 — 아래는 여기까지 오게 된 히스토리, 각 절은 그 시점 기준으로 정확함)

이 문서는 개발 일지 형식이라 전체를 읽어야 지금 상태가 재구성됨. 급하면 이 절만 보면 됨.

### 로컬 실행
```bash
python3 -m venv venv && source venv/bin/activate
pip install -r requirements.txt
REDIS_URL=redis://localhost:6379 SESSION_SECRET_KEY=x \
KAKAO_REST_API_KEY=x KAKAO_CLIENT_SECRET=x NOTION_CLIENT_ID=x NOTION_CLIENT_SECRET=x \
GOOGLE_CLIENT_ID=x GOOGLE_CLIENT_SECRET=x \
  uvicorn app.main:app --reload --port 8000
```
`http://localhost:8000` → `/login`으로 리다이렉트 → 카카오로 로그인 (자세한 설정 방법은 `README.md` 참고).

### 인증/연동 방식 (지금)
- **로그인 = 카카오 로그인 하나**. `talk_message` 동의를 함께 받아서 로그인이 곧 카카오 메시지 발송 연결(더 이상 별도의 "카카오 연결" 단계 없음)
- **Notion**: OAuth 공개 통합. "Notion 연결" → 공유 DB 선택 → 날짜/제목 속성은 스키마 타입으로 자동 감지(수동 입력 없음)
- **Google Calendar**: 선택 기능, 별도 OAuth 연결 버튼

### 현재 파일 구성
| 파일 | 역할 |
|---|---|
| `app/main.py` | FastAPI 앱, 전체 라우트 |
| `app/db.py` | Redis 저장소, 키 구조 `user:{카카오 id}:*` |
| `app/kakao_client.py` | 카카오 로그인 + 메시지 전송 |
| `app/notion_client.py` | Notion OAuth + 일정 조회 (속성 자동 감지) |
| `app/google_calendar_client.py` | Google Calendar OAuth + 일정 조회 |
| `app/scheduler.py` | APScheduler, `run_daily_job(user_id, source)` |
| `app/templates/login.html` | 로그인 페이지 (카카오) |
| `app/templates/settings.html` | 설정 페이지 (Notion/카카오/Google Calendar 연결) |
| `app/templates/dashboard.html` | 발송 이력 대시보드 |

### 필요한 환경변수
| 변수 | 용도 |
|---|---|
| `REDIS_URL` | Upstash Redis |
| `SESSION_SECRET_KEY` | 세션 쿠키 서명 |
| `KAKAO_REST_API_KEY` / `KAKAO_CLIENT_SECRET`(선택) | 카카오 로그인+메시지 (앱 공용, 사용자별 입력 불필요) |
| `NOTION_CLIENT_ID` / `NOTION_CLIENT_SECRET` | Notion OAuth |
| `GOOGLE_CLIENT_ID` / `GOOGLE_CLIENT_SECRET` | Google Calendar OAuth (로그인용 아님) |
| `CRON_SECRET` | GitHub Actions 백업 트리거 인증 |

---

## 구형 v1 — 은퇴한 로컬 스크립트 버전

`notify.py`(메인) + `get_kakao_token.py`(최초 1회 카카오 인증) + `.env` + launchd(매일 08:00)로 구성됐었음. 이번 세션에서 실제 카카오톡 전송까지 성공적으로 검증한 뒤, 웹앱 버전으로 전환하면서 launchd 등록 해제 + 스크립트/`.env` 삭제(백업은 `_v1_backup/`에 보관).

겪은 이슈 (기록용):
- 카카오 앱의 "카카오톡 메시지 전송(talk_message)" 동의항목이 비활성 상태로 최초 인증을 해서 403 `insufficient scopes` 발생 → 콘솔에서 활성화 후 재인증으로 해결
- launchd가 `~/Documents/...` 경로 접근 시 macOS TCC 권한에 막혀 `PermissionError` 발생 (터미널 직접 실행은 문제없었음, launchd 백그라운드 프로세스만 막힘)

---

## v1 — FastAPI 웹앱 기본 구축 (완료, 2026-09-07)

### 아키텍처
```
브라우저 (/settings)
      ↓
FastAPI 웹서비스 (Render, Free)  ── 내부 스케줄러(APScheduler)가 매일 지정 시각에 실행
      ↓                                         ↓
Upstash Redis (설정/토큰 저장)          Notion 조회 → 메시지 포맷 → 카카오 전송
```

### 왜 이 구조인가
- **Redis (Upstash, 무료·만료없음)**: Render 무료 웹서비스는 디스크가 임시(재배포마다 초기화)라 `.env`나 SQLite 파일로는 설정이 유지 안 됨. 처음엔 Render Postgres를 고려했으나 무료 플랜이 **30일 후 만료**되는 걸 확인하고, 계속 무료로 유지되는 Upstash Redis로 변경 (설정이 사실상 key-value 한 덩어리라 Redis 해시로 충분).
- **앱 내부 스케줄러(APScheduler)**: launchd(로컬 전용, macOS 종료 시 무력화)를 대체. 클라우드에 배포하면 서버가 상시 켜져 있다는 전제로 설계.
- **Render 무료 플랜의 spin-down 문제**: 일정 시간 요청이 없으면 서버가 잠들어서(spin down) 스케줄러도 같이 멈춤 → **UptimeRobot으로 5분마다 `/settings`를 핑**해서 항상 깨어있게 유지하는 방식으로 해결 예정 (별도 트리거 엔드포인트 없이, 그냥 서버를 안 재우는 방식).
- **하이브리드 앱(Capacitor) 전제**: 네이티브(RN/Flutter/Swift/Kotlin)는 이 프로젝트 규모(설정 폼 몇 개)엔 과함. 지금 웹 UI를 그대로 만들어두면 나중에 Capacitor로 감싸기만 하면 앱이 되므로, 로컬/배포 단계에서 이미 그 다음 단계를 염두에 두고 설계함(redirect_uri를 요청 시점에 동적 계산, 설정을 DB에 저장 등).

### 파일 구성 (2026-09-07 시점 — 지금 기준은 위 "현재 상태 요약 > 현재 파일 구성" 참고)
| 파일 | 역할 |
|---|---|
| `app/main.py` | FastAPI 앱, 전체 라우트 (설정/카카오 OAuth/미리보기/테스트전송) |
| `app/db.py` | Redis 기반 설정 저장소 (`REDIS_URL` 환경변수 사용) |
| `app/notion_client.py` | Notion 조회 + 메시지 포맷팅 (v1 `notify.py` 로직 이관) |
| `app/kakao_client.py` | 카카오 OAuth 교환/토큰갱신/전송 (v1 로직 이관) |
| `app/scheduler.py` | APScheduler, `run_daily_job()`이 크론과 테스트전송 버튼이 공유하는 유일한 실전송 진입점 |
| `app/templates/settings.html` | 유일한 UI 페이지 |

### 배포 정보
- GitHub: `justin1112-jimin/notion-kakao-schedule` (private)
- Render Web Service: `notion-kakao-schedule` (Free, Ohio/US East), Start Command: `uvicorn app.main:app --host 0.0.0.0 --port $PORT`
- Upstash Redis: Free, `REDIS_URL`을 Render 환경변수로 주입

### 배포 중 겪은 이슈 (해결됨)
- `requirements.txt`에 버전을 느슨하게(`>=`) 지정해서, Render가 로컬보다 최신 Starlette를 설치 → `TemplateResponse("settings.html", context)`(구식 위치인자 호출)가 최신 버전과 충돌해 500 에러(Jinja2 캐시 키에 dict가 들어가 `unhashable type` 발생). `request=`/`name=`/`context=` 키워드 인자로 명시해서 해결. 재발 방지로 `requirements.txt`를 로컬 검증 버전에 정확히 고정(`==`)함.

---

## 인증 (Google 로그인, 2026-09-06 추가 — 2026-09-09 카카오 로그인으로 대체됨, 아래 [[카카오 로그인 전환]] 참고)

`/settings` 등 모든 라우트가 로그인 없이 완전히 공개되어 있던 걸 발견 (URL만 알면 누구나 조회/수정/카카오 연결 하이재킹 가능). Google OAuth로 막되, 회원가입 없이 **허용된 이메일 1개만** 통과시키는 개인용 게이트로 구현.

- `app/auth.py`: Google 인가 URL 생성 + code → email 교환 (`requests`로 직접 호출, 별도 OAuth 라이브러리 없이 authorization code flow + userinfo 엔드포인트만 사용)
- `app/main.py`: `SessionMiddleware`(서명된 쿠키, `itsdangerous` 필요)로 세션 관리 + `require_login` 미들웨어로 `/login`, `/auth/callback` 제외한 모든 경로 차단. **미들웨어 등록 순서 주의**: `require_login`을 데코레이터로 먼저 등록하고 `app.add_middleware(SessionMiddleware, ...)`를 그 다음에 호출해야 함 (나중에 추가한 미들웨어가 바깥쪽/먼저 실행되는 Starlette 규칙상, SessionMiddleware가 `request.session`을 채워놓은 뒤에 `require_login`이 읽어야 하므로).
- `/login` → Google 인가 URL로 리다이렉트, `/auth/callback` → code 교환 후 이메일이 `ALLOWED_GOOGLE_EMAIL`과 일치할 때만 세션에 `logged_in=True` 저장, `/logout` → 세션 초기화.
- **구글 로그인은 "책임 전가" 수단이 아님**: OAuth는 신원 확인일 뿐이고, 뚫렸을 때 배상 책임은 여전히 앱 운영자(나)에게 있음. 순수하게 "공유 비밀번호 하나보다 계정 탈취가 더 어렵다"는 보안 강도 관점에서 선택한 것.

### 필요한 신규 환경변수 (Render)
| 변수 | 값 |
|---|---|
| `GOOGLE_CLIENT_ID` | Google Cloud Console에서 발급 |
| `GOOGLE_CLIENT_SECRET` | Google Cloud Console에서 발급 |
| `ALLOWED_GOOGLE_EMAIL` | 로그인 허용할 본인 Gmail 주소 |
| `SESSION_SECRET_KEY` | 세션 쿠키 서명용 랜덤 문자열 (한 번 생성해서 고정, 안 그러면 재배포마다 전체 로그아웃됨) |

### Google Cloud Console 설정 순서 (배포 전 사람이 직접 해야 함)
1. https://console.cloud.google.com/ → 프로젝트 선택/생성
2. "API 및 서비스" → "OAuth 동의 화면": User Type "외부", 앱 이름/본인 이메일만 입력하고 "테스트" 게시 상태로 유지
3. 같은 화면의 "테스트 사용자"에 본인 Gmail 주소 추가 (안 하면 로그인 시 `access_denied`)
4. "사용자 인증 정보" → "사용자 인증 정보 만들기" → "OAuth 클라이언트 ID" → 유형: 웹 애플리케이션
5. "승인된 리디렉션 URI"에 `https://notion-kakao-schedule.onrender.com/auth/callback` 등록
6. 발급된 클라이언트 ID/보안 비밀을 위 환경변수에 입력

### 배포 순서 주의
Render 환경변수 4개를 먼저 추가(저장 시 자동 재배포 1회 발생, 코드는 아직 이전 버전이라 무해함) → 그 다음에 이 코드를 git push. 반대로 하면(코드 먼저 push) env var가 없어서 앱이 기동 중 `KeyError: SESSION_SECRET_KEY`로 크래시하고 사이트가 잠깐 죽어있는 상태가 됨.

### 배포 중 겪은 이슈 (해결됨)
- 실제로 env var 추가보다 코드 push가 먼저 나가서, 배포가 `KeyError: 'SESSION_SECRET_KEY'`로 실패함 (Render Environment 탭에 `REDIS_URL`만 있고 나머지 4개가 빠져 있었음). Render는 새 배포가 실패하면 이전 버전을 계속 서비스하기 때문에 겉으로는 "그냥 로그인 없이 옛날 화면이 계속 뜨는" 것처럼 보여서 원인 파악에 로그 확인이 필요했음. 4개 환경변수 모두 추가 후 재배포 성공, `/settings` 비로그인 접근 시 `/login`으로 리다이렉트되는 것까지 확인.

## 발송 실패 안전망 (GitHub Actions 백업 트리거, 2026-09-07)

기존엔 발송 실패가 `last_sent_status`에 기록만 되고(`app/db.py`), `/settings`에 직접 들어가야만 알 수 있었음(능동 알림 없음). 새 서비스/인프라 추가 없이 **GitHub Actions의 기본 "스케줄 워크플로우 실패 시 이메일" 기능**을 그대로 활용해 해결.

- `app/main.py`의 `/internal/run-daily`: 로그인 세션 대신 `X-Cron-Secret` 헤더로 인증하는 별도 엔드포인트. 오늘 이미 성공 발송했으면(`scheduler.already_sent_today`) no-op(200), 아니면 `run_daily_job()`을 실행해 재시도. 실패하면 예외 메시지를 그대로 500 응답 본문에 담아 반환(어느 단계—Notion/카카오 토큰/카카오 발송—에서 실패했는지 로그에서 바로 보이게).
- `.github/workflows/daily-notify-backup.yml`: 매일 08:10 KST(=23:10 UTC)에 위 엔드포인트를 호출. 앱 내부 APScheduler(08:00 KST)가 이미 정상 발송했으면 조용히 넘어가고, 못 보냈으면 여기서 재시도 + 실패 시 GitHub Actions 워크플로우 자체가 실패 처리되어 **저장소 소유자에게 자동으로 실패 이메일 발송** (별도 SMTP/이메일 서비스 구축 없음).
- 자동 복구(토큰 자동 재발급 등)는 만들지 않음 — 사람이 이메일 받고 원인(Notion 토큰 만료/카카오 재인증 필요/일시적 오류 등)에 맞게 수동 조치. 스케일이 커지면 자동 복구를 고려하기로 함.

### 신규 환경변수/시크릿 (등록 완료, 2026-09-07)
| 위치 | 이름 | 값 |
|---|---|---|
| Render | `CRON_SECRET` | 임의의 랜덤 문자열 (한 번 생성해서 고정) |
| GitHub 저장소 Settings → Secrets and variables → Actions | `CRON_SECRET` | Render와 동일한 값 |

Render/GitHub 양쪽 모두 등록 완료, `daily-notify-backup.yml`이 최소 1회 정상 동작(성공 또는 no-op)하는 것까지 확인함. 이후 08:10 KST 실행에서 실패가 나면 저장소 소유자 이메일로 통보되는 구조가 실전 배포됨.

### v1 완료 체크리스트 (2026-09-07 기준)
- [x] FastAPI 웹앱 기본 구축 (라우트, Redis 연동, settings 페이지)
- [x] Notion API 연동 (일정 조회, 메시지 포맷팅)
- [x] 카카오 OAuth (refresh token 관리, 토큰 갱신)
- [x] APScheduler 자동 발송 (KST 08:00, reschedule 지원)
- [x] UptimeRobot 모니터링 (5분 간격 핑으로 Render spin-down 방지)
- [x] Google OAuth 로그인 (허용 이메일 1개 게이트, SessionMiddleware 세션 관리)
- [x] GitHub Actions 백업 트리거 (`/internal/run-daily` 엔드포인트, 발송 실패 시 이메일 자동 알림)
- [x] 발송 기록 저장/조회 (Redis 리스트, `add_send_history()` 등)

---

## v2 — 대시보드 추가 및 고도화 (진행 중, 2026-09-07~)

### 현재 진행 중
발송 이력 기본 대시보드 구현 중: Redis 기반 발송 기록 저장(`app/db.py`: `add_send_history()`, `get_send_history()`, `get_send_statistics()`), 스케줄러 연동(`app/scheduler.py`: `run_daily_job(source)` 파라미터 추가로 출처별 기록), API 엔드포인트(`app/main.py`: `/api/send-history`, `/dashboard`), 기본 UI(`app/templates/dashboard.html`: 성공률/7일 통계/이력 테이블/반응형 디자인). Redis에 최근 100개 기록 유지, 발송 출처("scheduler"/"backup"/"manual") 분류, 에러 메시지 기록 완료.

### v2 로드맵 (대시보드 고도화)
1. **시각화 강화**: Chart.js로 성공률 추이(일별 그래프), 시간대별 발송 분포(막대 차트), 출처별 비율(파이 차트) 추가
2. **상세 통계**: 일별/주별/월별 집계, 가장 오래 지속된 발송 streak, 가장 최근 실패 원인 상위 5개
3. **필터링 및 검색**: 날짜 범위 선택(캘린더), 상태별 필터(성공/실패/모두), 출처별 필터(자동/백업/수동/모두), 실시간 검색
4. **상호작용성**: 에러 메시지 전체 보기(모달 팝업), 발송 기록 상세 조회, 마우스오버 시 통계값 하이라이트
5. **다크모드**: 테마 토글 버튼, 시스템 설정 자동 감지, localStorage 저장
6. **실시간 업데이트**: 새 발송 기록 추가 시 자동 새로고침(Server-Sent Events 또는 polling)

---

## 다중 캘린더 지원 (2026-09-07 시작)

**목표**: Notion 외에 Google Calendar 등 여러 캘린더에서 일정을 가져와 하나의 메시지로 통합 발송

**v1: Google Calendar 기본 지원**

구현 계획:
1. **Google Calendar API 클라이언트** (`app/google_calendar_client.py`)
   - Google Calendar API 호출 (today's events)
   - 기존 Google 로그인 OAuth와 동일한 클라이언트 ID/Secret 사용 (Calendar API scope 추가)
   - 일정 포맷: `[Google] 일정명`

2. **설정 저장소 확장** (`app/db.py`)
   - `google_calendar_token` (Google Calendar OAuth 토큰)
   - `calendar_sources` (활성화된 캘린더: notion, google 등)
   - `calendar_merge_style` ("merge" 또는 "separate")

3. **설정 페이지** (`app/templates/settings.html`)
   - "Google Calendar 연결" 버튼 (별도 OAuth 플로우)
   - 체크박스: Notion 사용 여부, Google Calendar 사용 여부
   - 토큰 연결 상태 표시

4. **일정 조회 통합** (`app/scheduler.py`)
   - `run_daily_job()`에서 활성화된 모든 캘린더에서 일정 조회
   - Notion + Google Calendar 일정을 하나의 메시지로 통합
   - 출처별 라벨 표시: `[Notion]`, `[Google]`

5. **API 엔드포인트** (`app/main.py`)
   - `GET /google-calendar/connect` → Google Calendar OAuth 리다이렉트
   - `GET /google-calendar/callback` → 토큰 저장

**예상 소요**: ~2-3시간
- Google Calendar 클라이언트: 30분
- 설정 저장소 확장: 20분
- 설정 페이지 UI: 30분
- 발송 로직 통합: 30분
- 테스트: 20분

---

## 다중 사용자 지원 (2026-09-07 완료)

**목표**: 현재는 개인용(1인)이지만, 나중에 공개할 때 여러 사용자가 각자의 일정을 관리할 수 있도록 ✅

**v1: 사용자별 독립 설정 (완료)**

구현 완료:
1. **Google 로그인 개방** (`app/auth.py`) ✅
   - `ALLOWED_GOOGLE_EMAIL` 제약 제거, 모든 Google 계정 허용
   - `fetch_user_info()`가 email + `user_id`(Google `sub` claim) 함께 반환

2. **Redis 사용자 격리** (`app/db.py`) ✅
   - 키 구조: `user:{user_id}:settings`, `user:{user_id}:send_history`
   - 모든 조회/저장 함수가 `user_id`를 첫 인자로 받도록 변경

3. **라우트 연동** (`app/main.py`) ✅
   - `_get_user_id(request)` 헬퍼로 세션에서 추출
   - 설정/대시보드/API/카카오·구글캘린더 연결 전부 사용자별로 분리

4. **세션** ✅
   - `auth/callback`에서 `logged_in`, `user_id`, `email` 세션 저장

5. **백업 트리거** (`/internal/run-daily`) — 임시 처리
   - 아직 로그인 세션이 없는 GitHub Actions 컨텍스트라 `ADMIN_USER_ID` 환경변수(기본값 `"default_user"`)로 단일 사용자만 처리
   - **다중 사용자가 실제로 늘어나면 모든 user_id를 순회하도록 수정 필요** (현재는 1인 운영이라 미뤄둠)

**남은 것 (후속 작업)**:
- [ ] 로그인 페이지 UI (`app/templates/login.html`) — 지금은 `/login`이 버튼 없이 바로 Google로 리다이렉트됨
- [ ] 기존 단일 사용자 데이터 마이그레이션 (필요시)

---

## 연동 단순화 — 카카오 키 공용화 (완료, 2026-09-08)

**문제**: 다중 사용자 지원 이후에도 `/settings`에서 각 사용자가 **자기 소유 카카오 디벨로퍼스 앱**을 직접 만들어 REST API 키/Client Secret을 입력해야 했음. `talk_message`(나에게 보내기) 스코프는 앱 단위 권한이고, 실제로 사용자별로 달라야 하는 건 `kakao_refresh_token`뿐이라 이 요구는 불필요한 진입장벽이었음(Google Calendar 연동은 이미 공용 Google 클라이언트로 버튼 하나면 끝나는 것과 비대칭).

**해결**: `kakao_rest_api_key`/`kakao_client_secret`을 사용자별 Redis 설정에서 제거하고, `app/kakao_client.py`가 `google_calendar_client.py`/`app/auth.py`와 동일한 패턴으로 `os.environ["KAKAO_REST_API_KEY"]`/`os.environ.get("KAKAO_CLIENT_SECRET", "")`를 내부에서 직접 읽도록 변경. 앱 소유자(나)의 카카오 앱 하나를 모든 사용자가 공유하고, 사용자는 `/kakao/connect` 버튼만 누르면 됨 — 카카오 디벨로퍼스 가입/앱 생성/키 발급 과정이 통째로 사라짐.

- 변경 파일: `app/kakao_client.py`(env 직접 참조로 시그니처 단순화), `app/main.py`(`kakao_connect`/`kakao_callback`/`save_settings`/`_render_settings`에서 관련 파라미터 제거), `app/db.py`(`DEFAULTS`/`update_general_settings`에서 두 필드 제거), `app/scheduler.py`(`refresh_kakao_access_token(refresh_token)`만 호출), `app/templates/settings.html`(REST API 키/Client Secret 입력 필드 삭제, 연결 상태 배지만 유지)
- 기존 Redis에 남아있는 사용자별 `kakao_rest_api_key`/`kakao_client_secret` 값은 더 이상 읽지 않음(무해하게 방치, 별도 마이그레이션 불필요)

### 신규 환경변수 (Render, 배포 전 등록 필요)
| 변수 | 값 |
|---|---|
| `KAKAO_REST_API_KEY` | 카카오 디벨로퍼스 콘솔에서 발급받은 본인 앱의 REST API 키 |
| `KAKAO_CLIENT_SECRET` | (선택) 같은 앱의 Client Secret — 활성화해뒀다면 등록 |

**배포 순서 주의**: 위 두 변수를 Render에 먼저 추가한 뒤 이 코드를 push할 것(Google 로그인 도입 때와 동일한 이유 — 코드가 먼저 나가면 `/kakao/connect` 접근 시 `KeyError: 'KAKAO_REST_API_KEY'`로 500 발생).

**후속 후보**: Notion 쪽도 같은 문제(Integration Token 수동 발급/복사 + Database ID + 속성명 수동 입력)가 남아있음 — Notion 공개 OAuth 통합으로 전환하면 "연결" 버튼 + Notion 자체 페이지 선택 UI + 스키마 자동감지로 대체 가능하지만, Notion 개발자 포털에 새 OAuth 통합 등록이 필요한 더 큰 작업이라 아직 보류 중.

---

## 연동 단순화 — Notion OAuth 전환 (완료, 2026-09-08)

**문제**: Notion 연동도 카카오와 같은 종류의 진입장벽이 있었음 — 사용자가 Notion "Internal Integration"을 직접 만들어 Token을 복사/붙여넣기하고, Database ID를 직접 찾아 붙여넣고, 날짜/제목 속성명을 데이터베이스와 **정확히 똑같이** 타이핑해야 했음(오타 나면 조용히 빈 일정으로 나옴).

**조사 결과**: Notion Calendar(캘린더 클라이언트 앱) 자체는 외부 API가 없어 그대로 갖다 쓸 수 없었음. 대신 Notion이 2026-05-13 "Developer Platform 3.5"에서 OAuth 2.0 공개 통합을 정식 권장 경로로 밀고 있는 걸 확인([Notion 공식 발표](https://www.notion.com/blog/introducing-developer-platform)), 그리고 캘린더 뷰 데이터베이스는 date 속성이 최소 1개 필수([Notion 가이드](https://www.notion.com/help/guides/calendar-view-databases))라는 점에 착안 — 속성 **이름**이 아니라 **타입**으로 자동 감지하면 사용자가 속성명을 몰라도 됨.

**해결**: Google 로그인/Google Calendar와 동일한 OAuth 패턴으로 전환.
- `app/notion_client.py`: `build_authorize_url()`(OAuth 인가 URL), `exchange_code_for_token()`(code→access_token, Notion OAuth 토큰은 만료 없음/refresh 불필요), `list_shared_databases()`(`/v1/search`로 동의 화면에서 사용자가 공유한 DB만 조회), `detect_properties()`(`/v1/databases/{id}` 스키마에서 `type == "title"`/`type == "date"` 속성을 이름 무관하게 자동 탐지)
- `app/main.py`: `/notion/connect`(인가 URL로 리다이렉트) → `/notion/callback`(토큰 저장, 공유된 DB가 정확히 1개면 속성까지 자동 완료, 여러 개면 `/settings`에서 고르게 flash) → `/notion/select-database`(POST, 고른 DB의 속성 자동 감지 후 저장)
- `app/db.py`: `update_general_settings()`에서 Notion 필드 제거, `update_notion_token()`/`update_notion_database()`로 분리(카카오 리팩터와 동일 패턴)
- `app/templates/settings.html`: Token/Database ID/속성명 입력 필드 전부 삭제. "Notion 연결" 버튼 + (공유된 DB가 있으면) 드롭다운으로 대체. 이 김에 Notion/카카오/Google Calendar 연결 UI를 일반 설정(`알림 시각`) `<form>` 밖으로 분리 — 기존엔 "Google Calendar 연결" 버튼이 바깥 설정 폼 **안에 중첩된 `<form>`** 이라 HTML 파싱 규칙상 중첩 `<form>` 태그가 무시되어 실제로는 바깥 설정 폼이 그 지점에서 조기 종료되는 잠재 버그였음(브라우저에서 그동안 우연히 별문제 없어 보였을 수 있지만 구조적으로 깨져 있었음) — 카드를 분리하며 함께 수정.

### 신규 환경변수 (Render, 배포 전 등록 필요)
| 변수 | 값 |
|---|---|
| `NOTION_CLIENT_ID` | Notion 개발자 포털에서 발급받은 OAuth 통합의 Client ID |
| `NOTION_CLIENT_SECRET` | 같은 통합의 Client Secret |

### Notion 개발자 포털 설정 순서 (배포 전 사람이 직접 해야 함)
1. https://www.notion.so/my-integrations (또는 app.notion.com/developers) → 새 통합 생성
2. 통합 유형을 **Public**(OAuth)으로 설정 — Internal이면 이 플로우가 동작하지 않음
3. Capabilities에서 최소 "Read content" 권한 활성화
4. Redirect URI에 `https://notion-kakao-schedule.onrender.com/notion/callback` 등록
5. 발급된 Client ID/Secret을 위 환경변수에 입력

**배포 순서 주의**: Google/카카오 때와 동일한 이유로, 위 두 환경변수를 Render에 먼저 추가한 뒤 코드를 push할 것(반대 순서면 `/notion/connect` 접근 시 `KeyError: 'NOTION_CLIENT_ID'`로 500 발생).

**기존 설정과의 관계**: 기존에 수동으로 넣어뒀던 `notion_token`/`notion_database_id`/`notion_date_property`/`notion_title_property` 값은 그대로 Redis에 남아있고 `run_daily_job()`이 읽는 필드명도 동일해서 **재설정 없이 계속 동작**함. 새로 "Notion 연결"을 누르면 그 값들이 OAuth 흐름으로 덮어써짐.

**남은 것**: 공유된 DB가 0개일 때 안내 문구는 있지만, DB 연결 해제(공유 취소) 후 재조회 실패 시의 에러 메시지가 다소 무성의함(`list_shared_databases` 실패 시 조용히 빈 목록) — 실사용하면서 문제되면 개선.

---

## 카카오 로그인 전환 (완료, 2026-09-09)

**배경**: 이 앱의 진짜 목적은 "오늘 일정을 카카오톡으로 받는 것"이지 Notion이 아님. 그런데 로그인은 Google, 메시지 발송 동의는 별도로 카카오 — 두 개의 독립된 OAuth 플로우를 사용자가 따로 거쳐야 했음. 카카오 로그인(`talk_message` 동의 포함)을 신원 확인 겸용으로 쓰면 **로그인 = 카카오 연결**이 되어 한 단계가 통째로 사라진다는 점에 착안해 전환.

**해결**: `app/auth.py`(Google OAuth 신원 확인 모듈) 삭제, `app/kakao_client.py`에 로그인용 함수 추가.
- `build_authorize_url(redirect_uri, state)`: scope에 `talk_message profile_nickname`을 함께 요청(CSRF 방지용 `state` 파라미터도 이제 필요 — 로그인 전에도 호출되므로)
- `fetch_user_info(access_token)`: `/v2/user/me` 호출해 `id`(고유 식별자, 별도 동의 불필요)와 `nickname`(동의 시) 반환
- `/login/kakao` → `/auth/kakao/callback`: code 교환 → `fetch_user_info` → 세션에 `user_id`=카카오 `id`, `nickname` 저장 **+ 그 자리에서 바로 `db.update_kakao_refresh_token()` 호출**. 기존의 독립적인 `/kakao/connect`, `/kakao/callback` 라우트는 삭제(로그인 흐름에 흡수됨)
- `_render_settings()`의 `user_email` → `nickname`으로 교체, `settings.html`에서 "카카오 연결" 버튼 제거(로그인 시 자동 연결됨을 안내 문구로 대체)
- `login.html`: Google 버튼 → 카카오 옐로(#FEE500) 버튼으로 교체

**Kakao Developers 콘솔에서 확인 필요** (배포 전):
- 동의항목에서 `talk_message`가 **필수 동의**로 설정돼 있어야 함(선택 동의면 로그인은 성공해도 메시지 발송 권한이 없는 상태로 세션이 만들어질 수 있음) — v1 때 이미 활성화했던 항목([구형 v1 섹션](#구형-v1--은퇴한-로컬-스크립트-버전) 참고)이라 이미 되어있을 가능성 높음, 재확인만
- `profile_nickname`은 선택 동의로 둬도 무방(꺼져 있으면 닉네임 없이 "카카오 사용자"처럼 빈 표시, 기능엔 영향 없음)
- Redirect URI에 `https://notion-kakao-schedule.onrender.com/auth/kakao/callback` 추가 등록 (기존 `/kakao/callback`은 더 이상 안 씀 — 지워도 되지만 안 지워도 무해함)

**⚠️ 파괴적 변경 — 기존 세션/데이터 이전 필요**:
- 세션의 `user_id`가 Google `sub`에서 카카오 `id`로 바뀌므로, 기존에 Google로 로그인해서 쌓아둔 Redis 데이터(`user:{old_google_sub}:settings` 등 — Notion 연결, Kakao refresh token, 알림 시각, 발송 이력)는 새 카카오 `id` 밑에서는 안 보임(데이터 자체는 안 지워지고 orphan 상태로 남음)
- 배포 후 카카오로 새로 로그인 → Notion 연결 → 알림 시각 재설정을 다시 한 번 해줘야 함
- `/internal/run-daily`가 쓰는 `ADMIN_USER_ID` 환경변수(Render)도 새 카카오 `id` 값으로 갱신 필요 — 안 갱신하면 백업 트리거가 orphan된 옛 데이터를 계속 보게 됨. 새 카카오 `id`는 로그인 한 번 한 뒤 Redis에서 `user:*:settings` 키를 확인하거나, `/settings` 페이지에 표시되는 닉네임과 매칭해서 확인.
- `GOOGLE_CLIENT_ID`/`GOOGLE_CLIENT_SECRET`은 신원 확인용으로는 더 이상 안 쓰이지만, Google Calendar 연동(`app/google_calendar_client.py`)에서 여전히 필요하므로 삭제하면 안 됨. `ALLOWED_GOOGLE_EMAIL`은 다중 사용자 지원 때 이미 미사용이 됐고 이번에도 그대로 미사용.

---

## 이번 세션에서 발견한 Gotchas (2026-09-09)

**`settings.html`에 새 연결 버튼 추가 시 중첩 `<form>` 금지**: 기존 설정 저장용 `<form action="/settings">` 안에 다른 `<form>`을 넣으면 브라우저가 안쪽 여는 태그를 무시하고, 그 짝이 되는 닫는 태그가 바깥 폼을 조기 종료시켜버림 — Google Calendar "연결" 버튼이 실제로 이렇게 깨져 있었던 걸 발견해서 수정(Notion/카카오 연동 단순화 작업 중). 새 OAuth 연결 버튼은 항상 별도의 최상위 `<form>`으로 작성할 것.

**새 OAuth 연동의 `os.environ["X"]`는 함수 내부(요청 시점)에서 읽을 것**: `main.py` import 시점이나 모듈 최상단에서 읽으면 그 환경변수 하나만 없어도 앱 전체가 부팅 실패함(`SESSION_SECRET_KEY`가 그 예 — `app.add_middleware(SessionMiddleware, secret_key=os.environ[...])`가 모듈 로드 시 바로 실행됨). `kakao_client.py`/`notion_client.py`처럼 각 함수 안에서 읽으면, 그 env var가 빠졌을 때 해당 라우트만 500이 나고 사이트 나머지는 정상 동작 — 새 연동 추가 시 이 패턴을 따를 것.

**배포 후 검증은 curl로 직접**: Render API/CLI 접근 권한이 없어서, 배포 후엔 `/usr/bin/curl -s -o /dev/null -w "%{http_code}" <URL>`로 엔드포인트 상태 코드만 확인하는 방식으로 검증함(bare `curl`이 이 환경 셸에서 간헐적으로 PATH 문제로 안 잡혀서 절대경로 사용). 로그인 필요한 라우트가 미로그인 상태에서 302/307을 반환하면 정상이고, 500이면 문제(대개 최근 추가한 env var 누락).

**배포 전 로컬 사전 점검(실제 Redis 없이 가능)**:
```bash
REDIS_URL=redis://localhost:6379 SESSION_SECRET_KEY=x GOOGLE_CLIENT_ID=x GOOGLE_CLIENT_SECRET=x \
CRON_SECRET=x KAKAO_REST_API_KEY=x NOTION_CLIENT_ID=x NOTION_CLIENT_SECRET=x \
  python3 -c "from app import main; print([r.path for r in main.app.routes if hasattr(r,'path')])"
```
import 에러나 라우트 등록 누락을 실제 인프라 없이 바로 잡을 수 있음. 템플릿 쪽은 `Jinja2Templates(directory='app/templates').get_template('settings.html').render(**mock_context)`로 목업 컨텍스트를 채워 렌더링해보면 Jinja 문법 오류를 배포 전에 잡을 수 있음(이번 세션에서 Notion 카드 재배치, 카카오 로그인 전환 때 실제로 이 방식으로 검증함).

**CLAUDE.md에 코드 상태(줄 수 등 구체적 수치)를 적을 때는 실제로 파일을 열어 확인한 값만 쓸 것**: 2026-09-09에 다른 세션이 이 파일을 재구성하면서 "main.py 10544줄" 같은 완전히 허구인 줄 수와, 실제로 존재하지 않는 함수(`send_message`, `get_kakao_refresh_token` 등)를 쓰는 예제 코드를 남겨서 롤백한 적 있음. 검증 안 된 구체적 수치/코드 예제는 안 적느니만 못함 — 특히 파일 크기처럼 다음 커밋에 바로 stale해지는 정보는 애초에 문서화 가치가 낮음(`wc -l`로 언제든 즉시 확인 가능).

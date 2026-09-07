# CLAUDE.md

## 프로젝트 개요
Notion에서 **오늘 날짜의 일정**을 가져와, 매일 아침 **카카오톡 "나에게 보내기"**로 요약 메시지를 자동 전송하는 개인용 자동화 도구.

### 버전 관리
- **구형 v1 (은퇴, `_v1_backup/`)**: 로컬 Python 스크립트 + macOS launchd
- **현재 v1 (완료, 2026-09-07)**: FastAPI 웹앱(Render 배포) + Notion/카카오 OAuth + Google 로그인 + GitHub Actions 백업 트리거 — 기본 기능 완성
- **현재 v2 (진행 중, 2026-09-07~)**: 발송 이력 대시보드 + 시각화/필터링/다크모드 고도화 → 최종 목표: Capacitor로 하이브리드 앱 패키징(iOS/Android)
 
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

### 파일 구성
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

## 인증 (Google 로그인, 2026-09-06 추가)

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

## 다중 사용자 지원 (2026-09-07 시작)

**목표**: 현재는 개인용(1인)이지만, 나중에 공개할 때 여러 사용자가 각자의 일정을 관리할 수 있도록

**v1: 사용자별 독립 설정**

구현 계획:
1. **Google 로그인 개방** (`app/auth.py`)
   - `ALLOWED_GOOGLE_EMAIL` 제약 제거 (모든 Google 계정 허용)
   - 대신 로그인 후 세션에 user_id 저장 (Google sub claim 사용)

2. **Redis 사용자 격리** (`app/db.py`)
   - 키 구조 변경: `settings` → `user:{user_id}:settings`
   - 발송 이력도 사용자별로: `user:{user_id}:send_history`
   - `get_user_id(request)` 헬퍼 함수로 세션에서 user_id 추출

3. **마이그레이션** (선택사항)
   - 현재 개인 설정을 새 구조로 이관 (나중에 필요시)
   - 기존 Redis key 유지하되, 관리자 계정에만 할당

4. **라우트 수정** (`app/main.py`)
   - 모든 라우트에서 `user_id` 연동
   - 대시보드/설정/API 모두 사용자별로 필터링

5. **세션/쿠키**
   - 기존 `logged_in` 플래그 + `user_id` 저장
   - 로그아웃 시 둘 다 초기화

**예상 소요**: ~2-3시간
- auth.py 수정: 20분
- db.py 리팩토링: 45분
- main.py 라우트 연동: 45분
- 마이그레이션 로직: 20분
- 테스트: 30분

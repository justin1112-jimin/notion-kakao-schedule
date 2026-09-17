# CLAUDE.md

## 프로젝트 개요
Notion(과 선택적으로 Google Calendar)에서 **오늘 날짜의 일정**을 가져와, 매일 아침 **카카오톡 "나에게 보내기"**로 요약 메시지를 자동 전송하는 개인용 자동화 도구.

- **v1 (완료)**: FastAPI 웹앱(Render 배포) + Notion/카카오 OAuth + GitHub Actions 백업 트리거 — 기본 기능 완성
- **v2 (완료)**: 발송 이력 대시보드(다크모드 포함) + 다중 사용자 자동 발송 실제 지원(사용자별 개별 스케줄) + `/status` 상태 확인 페이지 + 오픈소스 공개
  - **v2.1**: 카카오 API rate limit 대응(429 재시도/백오프), GitHub Pages 소개 페이지 공개
  - **v2.2**: 캘린더 소스별 부분 실패 처리(한쪽 실패가 전체 발송을 막지 않도록), Redis 클라이언트 싱글턴화, 구조화 로깅 + 선택적 Sentry 에러 트래킹, pytest 회귀 테스트 + CI
- **v3 (예정)**: 대시보드 시각화 고도화(Chart.js 등) + Capacitor로 하이브리드 앱 패키징(iOS/Android) — 백로그, 아직 착수 전

세부 실행/배포 방법은 `README.md` 참고.

## 아키텍처

```
브라우저 (/settings)
      ↓
FastAPI 웹서비스 (Render)  ── 내부 스케줄러(APScheduler)가 매일 지정 시각에 실행
      ↓                                         ↓
Upstash Redis (설정/토큰 저장)          Notion + Google Calendar 조회 → 메시지 포맷 → 카카오 전송
```

- **Redis (Upstash)**: Render 무료 웹서비스는 디스크가 임시(재배포마다 초기화)라 설정을 유지하려면 외부 저장소가 필요. 설정이 사실상 key-value 한 덩어리라 Redis로 충분.
- **앱 내부 스케줄러(APScheduler)**: 서버가 상시 켜져 있다는 전제로 설계. Render 무료 플랜은 일정 시간 요청이 없으면 spin down 되므로, UptimeRobot 같은 걸로 주기적으로 핑해서 깨어있게 유지해야 함(README 참고).
- **하이브리드 앱(Capacitor) 전제**: 지금 웹 UI를 그대로 만들어두면 나중에 Capacitor로 감싸기만 하면 앱이 되므로, redirect_uri를 요청 시점에 동적 계산하거나 설정을 DB에 저장하는 등 그 다음 단계를 염두에 두고 설계함.

## 파일 구성
| 파일 | 역할 |
|---|---|
| `app/main.py` | FastAPI 앱, 전체 라우트, 로깅/Sentry 초기화 |
| `app/db.py` | Redis 저장소(싱글턴 클라이언트), 키 구조 `user:{카카오 id}:*` |
| `app/kakao_client.py` | 카카오 로그인 + 메시지 전송 (429 재시도/백오프 포함) |
| `app/notion_client.py` | Notion OAuth + 일정 조회 (속성 자동 감지) |
| `app/google_calendar_client.py` | Google Calendar OAuth + 일정 조회 |
| `app/scheduler.py` | APScheduler, `run_daily_job(user_id, source)` — 캘린더 소스별 부분 실패 처리 |
| `app/templates/login.html` | 로그인 페이지 (카카오) |
| `app/templates/settings.html` | 설정 페이지 (Notion/카카오/Google Calendar 연결) |
| `app/templates/dashboard.html` | 발송 이력 대시보드 |
| `app/templates/status.html` | 저장된 설정 vs 스케줄러 실제 예약 시각 비교 |
| `docs/` | GitHub Pages 소개/가이드 페이지 (정적 HTML, 별도 배포 파이프라인 없음) |
| `tests/` | pytest 회귀 테스트, push/PR마다 GitHub Actions(`test.yml`)로 자동 실행 |

## 인증/연동 방식
- **로그인 = 카카오 로그인 하나**. `talk_message` 동의를 함께 받아서 로그인이 곧 카카오 메시지 발송 연결(별도의 "카카오 연결" 단계 없음)
- **Notion**: OAuth 공개 통합. "Notion 연결" → 공유 DB 선택 → 날짜/제목 속성은 스키마 타입으로 자동 감지(수동 입력 없음)
- **Google Calendar**: 선택 기능, 별도 OAuth 연결 버튼
- **다중 사용자**: Redis 키가 `user:{카카오 id}:*`로 격리되어 있어, 여러 사용자가 각자 독립적으로 연결/설정 가능. 매일 자동 발송도 사용자별로 각자의 알림 시각에 개별 스케줄되며(`all_user_ids` 셋으로 전체 사용자 추적), 백업 트리거(`/internal/run-daily`)도 등록된 모든 사용자를 순회함 — 특정 한 명만 처리하는 관리자 계정 개념 없음.

## 필요한 환경변수
값 없이 이름과 용도만 기재. 실제 값은 `.env.example` 참고, 절대 커밋하지 말 것.

| 변수 | 용도 |
|---|---|
| `REDIS_URL` | Upstash Redis |
| `SESSION_SECRET_KEY` | 세션 쿠키 서명 |
| `KAKAO_REST_API_KEY` / `KAKAO_CLIENT_SECRET`(선택) | 카카오 로그인+메시지 (앱 공용, 사용자별 입력 불필요) |
| `NOTION_CLIENT_ID` / `NOTION_CLIENT_SECRET` | Notion OAuth |
| `GOOGLE_CLIENT_ID` / `GOOGLE_CLIENT_SECRET` | Google Calendar OAuth (로그인용 아님) |
| `CRON_SECRET` | GitHub Actions 백업 트리거 인증 |
| `SENTRY_DSN`(선택) | Sentry 에러 트래킹, 비워두면 비활성화 |
| `LOG_LEVEL`(선택) | 로그 레벨, 기본값 INFO |

## 개발 시 지켜야 할 규칙 (겪었던 문제들에서 도출)

**새 OAuth 연동의 `os.environ["X"]`는 함수 내부(요청 시점)에서 읽을 것**: 모듈 최상단이나 import 시점에서 읽으면 그 환경변수 하나만 없어도 앱 전체가 부팅 실패함. `kakao_client.py`/`notion_client.py`처럼 각 함수 안에서 읽으면, env var가 빠졌을 때 해당 라우트만 500이 나고 사이트 나머지는 정상 동작 — 새 연동 추가 시 이 패턴을 따를 것.

**`settings.html`에 새 연결 버튼 추가 시 중첩 `<form>` 금지**: 기존 설정 저장용 `<form>` 안에 다른 `<form>`을 넣으면 브라우저가 안쪽 여는 태그를 무시하고, 그 짝이 되는 닫는 태그가 바깥 폼을 조기 종료시켜버림. 새 OAuth 연결 버튼은 항상 별도의 최상위 `<form>`으로 작성할 것.

**카카오톡 메시지의 `link.web_url`은 카카오 디벨로퍼스에 등록된 "웹 도메인"이어야 함**: [앱] > [제품 링크 관리] > [웹 도메인]에 스킴을 포함해(`https://...`, 끝 슬래시 없이) 등록돼 있지 않으면, 링크가 조용히 앱에 등록된 다른(대개 로컬 개발용) 도메인으로 대체됨. 하드코딩 대신 `RENDER_EXTERNAL_URL`(Render가 자동 주입) → `PUBLIC_BASE_URL` 환경변수 → 로컬 fallback 순서로 동적 계산할 것(`app/scheduler.py`의 `_app_base_url()` 참고).

**`run_daily_job()`은 캘린더별 미연결 가드를 대칭으로 둘 것**: 한쪽 캘린더만 미연결 체크를 하고 다른 쪽은 체크 없이 바로 API를 호출하면, 후자가 원인 불명의 400/에러로 실패함. 두 캘린더 모두 미연결이면 명확한 에러(`NoCalendarConnectedError`)로 실패하게 만들 것.

**캘린더 소스별 조회는 각각 try/except로 감쌀 것, 한쪽 실패가 전체 발송을 막으면 안 됨**: 실제로 겪은 버그 — Google Calendar 리프레시 토큰이 무효화되어 `refresh_access_token()`이 예외를 던졌는데, 이게 잡히지 않고 그대로 전파되면서 이미 조회에 성공한 Notion 일정까지 통째로 발송이 취소됨(GitHub Actions 백업 트리거 로그의 "400 Client Error"로 발견). 지금은 소스별로 개별 실패 처리하고, 활성화된 소스가 전부 실패했을 때만 명확하게 예외를 던짐.

**"✅ 연결됨" 배지는 토큰 존재 여부만 확인, 유효성은 안 봄 — 재연결 UI는 연결 상태와 무관하게 항상 노출할 것**: Google Calendar 재연결 버튼이 `{% if not google_calendar_connected %}`로 감싸져 있어서, 토큰이 죽어도 배지는 계속 "연결됨"으로 보이고 재연결할 방법 자체가 화면에서 사라지는 버그가 있었음. 연결 여부 배지는 항상 보여주되, 재연결 버튼/링크는 연결 상태와 무관하게 항상 노출하고, 가능하면 "마지막 성공 시각"처럼 실제 작동 여부를 보여주는 신호를 같이 둘 것.

**외부 API 호출(`requests.get/post`)에는 항상 `timeout`을 명시할 것**: `kakao_client.py`/`notion_client.py`는 처음부터 `timeout=10`을 넣었는데 `google_calendar_client.py`만 빠져있던 적이 있음. 타임아웃이 없으면 그 API가 느려질 때 해당 사용자의 요청(특히 APScheduler 스레드풀에서 도는 발송 작업)이 무한정 대기하며 다른 사용자 작업까지 지연시킬 수 있음.

**`db.get_client()`처럼 외부 커넥션을 만드는 함수는 싱글턴으로 재사용할 것**: 호출할 때마다 새로 연결을 만들면 낭비고, 커넥션에 타임아웃도 안 걸려있으면 응답이 느려질 때 요청이 무한정 걸릴 수 있음. 모듈 레벨 캐시 변수로 최초 호출 시점에만 생성하고 재사용할 것(단, `os.environ["X"]`를 읽는 시점 자체는 여전히 최초 호출 때로 — import 시점에 읽지 않는다는 기존 규칙은 유지).

**로깅은 `logging` 모듈로, 에러 트래킹은 `SENTRY_DSN` 선택적 연동으로**: `print`나 문자열 반환값에 의존하지 말고 `logger.info/warning/error`를 쓸 것. `SENTRY_DSN`이 없으면 `sentry_sdk.init()`을 호출하지 않고, `sentry_sdk.capture_exception()`은 초기화 안 된 상태에서 호출해도 안전하게 no-op이므로 조건 분기 없이 그냥 호출해도 됨.

**배포 전 로컬 사전 점검(실제 Redis 없이 가능)**:
```bash
REDIS_URL=redis://localhost:6379 SESSION_SECRET_KEY=x GOOGLE_CLIENT_ID=x GOOGLE_CLIENT_SECRET=x \
CRON_SECRET=x KAKAO_REST_API_KEY=x NOTION_CLIENT_ID=x NOTION_CLIENT_SECRET=x \
  python3 -c "from app import main; print([r.path for r in main.app.routes if hasattr(r,'path')])"
```
import 에러나 라우트 등록 누락을 실제 인프라 없이 바로 잡을 수 있음. 템플릿 쪽은 `Jinja2Templates(directory='app/templates').get_template('settings.html').render(**mock_context)`로 목업 컨텍스트를 채워 렌더링해보면 Jinja 문법 오류를 배포 전에 잡을 수 있음. `run_daily_job()`처럼 크리티컬한 로직을 고칠 때는 `pytest tests/ -v`도 같이 돌릴 것(`tests/` 참고, Redis/외부 API는 전부 mock이라 인프라 없이 즉시 실행 가능).

**배포 후 검증은 curl로 직접**: 로그인 세션이 필요한 라우트가 미로그인 상태에서 302/307을 반환하면 정상, 500이면 문제(대개 최근 추가한 env var 누락). Claude Code에는 브라우저 자동화가 붙어있지 않은 경우가 많아 OAuth 동의 화면이나 실제 발송 결과는 사람이 직접 클릭/확인해야 함.

**CLAUDE.md에 코드 상태(줄 수 등 구체적 수치)를 적을 때는 실제로 파일을 열어 확인한 값만 쓸 것**: 검증 안 된 구체적 수치나 존재하지 않는 함수를 쓰는 예제 코드는 안 적느니만 못함 — 특히 파일 크기처럼 다음 커밋에 바로 stale해지는 정보는 `wc -l`로 언제든 즉시 확인 가능하므로 문서화 가치가 낮음.

## 로컬 개발 이력 관련 참고
개인 배포 도메인, 세션별 작업 일지, 커밋 해시 등 이 저장소를 공개하면서 제외한 운영 디테일은 `CLAUDE.local.md`(gitignored, 로컬에만 존재)에 보관되어 있습니다.

@CLAUDE.local.md

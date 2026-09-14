# CLAUDE.md

## 프로젝트 개요
Notion(과 선택적으로 Google Calendar)에서 **오늘 날짜의 일정**을 가져와, 매일 아침 **카카오톡 "나에게 보내기"**로 요약 메시지를 자동 전송하는 개인용 자동화 도구.

- **v1 (완료)**: FastAPI 웹앱(Render 배포) + Notion/카카오 OAuth + GitHub Actions 백업 트리거 — 기본 기능 완성
- **v2 (진행 중)**: 발송 이력 대시보드 + 시각화/필터링/다크모드 고도화 → 최종 목표: Capacitor로 하이브리드 앱 패키징(iOS/Android)

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
| `app/main.py` | FastAPI 앱, 전체 라우트 |
| `app/db.py` | Redis 저장소, 키 구조 `user:{카카오 id}:*` |
| `app/kakao_client.py` | 카카오 로그인 + 메시지 전송 |
| `app/notion_client.py` | Notion OAuth + 일정 조회 (속성 자동 감지) |
| `app/google_calendar_client.py` | Google Calendar OAuth + 일정 조회 |
| `app/scheduler.py` | APScheduler, `run_daily_job(user_id, source)` |
| `app/templates/login.html` | 로그인 페이지 (카카오) |
| `app/templates/settings.html` | 설정 페이지 (Notion/카카오/Google Calendar 연결) |
| `app/templates/dashboard.html` | 발송 이력 대시보드 |

## 인증/연동 방식
- **로그인 = 카카오 로그인 하나**. `talk_message` 동의를 함께 받아서 로그인이 곧 카카오 메시지 발송 연결(별도의 "카카오 연결" 단계 없음)
- **Notion**: OAuth 공개 통합. "Notion 연결" → 공유 DB 선택 → 날짜/제목 속성은 스키마 타입으로 자동 감지(수동 입력 없음)
- **Google Calendar**: 선택 기능, 별도 OAuth 연결 버튼
- **다중 사용자**: Redis 키가 `user:{카카오 id}:*`로 격리되어 있어, 여러 사용자가 각자 독립적으로 연결/설정 가능

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

## 개발 시 지켜야 할 규칙 (겪었던 문제들에서 도출)

**새 OAuth 연동의 `os.environ["X"]`는 함수 내부(요청 시점)에서 읽을 것**: 모듈 최상단이나 import 시점에서 읽으면 그 환경변수 하나만 없어도 앱 전체가 부팅 실패함. `kakao_client.py`/`notion_client.py`처럼 각 함수 안에서 읽으면, env var가 빠졌을 때 해당 라우트만 500이 나고 사이트 나머지는 정상 동작 — 새 연동 추가 시 이 패턴을 따를 것.

**`settings.html`에 새 연결 버튼 추가 시 중첩 `<form>` 금지**: 기존 설정 저장용 `<form>` 안에 다른 `<form>`을 넣으면 브라우저가 안쪽 여는 태그를 무시하고, 그 짝이 되는 닫는 태그가 바깥 폼을 조기 종료시켜버림. 새 OAuth 연결 버튼은 항상 별도의 최상위 `<form>`으로 작성할 것.

**카카오톡 메시지의 `link.web_url`은 카카오 디벨로퍼스에 등록된 "웹 도메인"이어야 함**: [앱] > [제품 링크 관리] > [웹 도메인]에 스킴을 포함해(`https://...`, 끝 슬래시 없이) 등록돼 있지 않으면, 링크가 조용히 앱에 등록된 다른(대개 로컬 개발용) 도메인으로 대체됨. 하드코딩 대신 `RENDER_EXTERNAL_URL`(Render가 자동 주입) → `PUBLIC_BASE_URL` 환경변수 → 로컬 fallback 순서로 동적 계산할 것(`app/scheduler.py`의 `_app_base_url()` 참고).

**`run_daily_job()`은 캘린더별 미연결 가드를 대칭으로 둘 것**: 한쪽 캘린더만 미연결 체크를 하고 다른 쪽은 체크 없이 바로 API를 호출하면, 후자가 원인 불명의 400/에러로 실패함. 두 캘린더 모두 미연결이면 명확한 에러(`NoCalendarConnectedError`)로 실패하게 만들 것.

**배포 전 로컬 사전 점검(실제 Redis 없이 가능)**:
```bash
REDIS_URL=redis://localhost:6379 SESSION_SECRET_KEY=x GOOGLE_CLIENT_ID=x GOOGLE_CLIENT_SECRET=x \
CRON_SECRET=x KAKAO_REST_API_KEY=x NOTION_CLIENT_ID=x NOTION_CLIENT_SECRET=x \
  python3 -c "from app import main; print([r.path for r in main.app.routes if hasattr(r,'path')])"
```
import 에러나 라우트 등록 누락을 실제 인프라 없이 바로 잡을 수 있음. 템플릿 쪽은 `Jinja2Templates(directory='app/templates').get_template('settings.html').render(**mock_context)`로 목업 컨텍스트를 채워 렌더링해보면 Jinja 문법 오류를 배포 전에 잡을 수 있음.

**배포 후 검증은 curl로 직접**: 로그인 세션이 필요한 라우트가 미로그인 상태에서 302/307을 반환하면 정상, 500이면 문제(대개 최근 추가한 env var 누락). Claude Code에는 브라우저 자동화가 붙어있지 않은 경우가 많아 OAuth 동의 화면이나 실제 발송 결과는 사람이 직접 클릭/확인해야 함.

**CLAUDE.md에 코드 상태(줄 수 등 구체적 수치)를 적을 때는 실제로 파일을 열어 확인한 값만 쓸 것**: 검증 안 된 구체적 수치나 존재하지 않는 함수를 쓰는 예제 코드는 안 적느니만 못함 — 특히 파일 크기처럼 다음 커밋에 바로 stale해지는 정보는 `wc -l`로 언제든 즉시 확인 가능하므로 문서화 가치가 낮음.

## 로컬 개발 이력 관련 참고
개인 배포 도메인, 세션별 작업 일지, 커밋 해시 등 이 저장소를 공개하면서 제외한 운영 디테일은 `CLAUDE.local.md`(gitignored, 로컬에만 존재)에 보관되어 있습니다.

@CLAUDE.local.md

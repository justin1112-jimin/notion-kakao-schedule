# CLAUDE.md

## 프로젝트 개요
Notion에서 **오늘 날짜의 일정**을 가져와, 매일 아침 **카카오톡 "나에게 보내기"**로 요약 메시지를 자동 전송하는 개인용 자동화 도구.

- **v1 (완료 → 은퇴)**: 로컬 Python 스크립트 + macOS launchd. 정상 작동까지 검증했으나 v2로 완전히 대체됨. 코드는 `_v1_backup/`에 보관(gitignore, 배포 미포함).
- **v2 (진행 중)**: FastAPI 웹앱으로 전환, Render에 배포. 최종 목표는 **하이브리드 앱**(Capacitor로 이 웹 UI를 감싸 iOS/Android 앱으로 배포).

---

## v1 — 은퇴한 로컬 스크립트 버전

`notify.py`(메인) + `get_kakao_token.py`(최초 1회 카카오 인증) + `.env` + launchd(매일 08:00)로 구성됐었음. 이번 세션에서 실제 카카오톡 전송까지 성공적으로 검증한 뒤, v2로 전환하면서 launchd 등록 해제 + 스크립트/`.env` 삭제(백업은 `_v1_backup/`에 보관).

v1 진행 중 겪은 이슈 (v2에는 해당 없음, 기록용):
- 카카오 앱의 "카카오톡 메시지 전송(talk_message)" 동의항목이 비활성 상태로 최초 인증을 해서 403 `insufficient scopes` 발생 → 콘솔에서 활성화 후 재인증으로 해결
- launchd가 `~/Documents/...` 경로 접근 시 macOS TCC 권한에 막혀 `PermissionError` 발생 (터미널 직접 실행은 문제없었음, launchd 백그라운드 프로세스만 막힘)

---

## v2 — FastAPI 웹앱 (진행 중)

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

## 현재 상태 (다음에 이어서 할 일)
- [x] FastAPI 웹앱 코드 작성, GitHub push, Render 배포, 500 에러 수정 → `/settings` 정상 렌더링 확인됨
- [x] Render Redis에 Notion 토큰/DB ID/속성명, 카카오 REST 키/시크릿 입력 완료 (2026-09-05, v1 `_v1_backup/.env` 값 재사용)
- [x] 카카오 디벨로퍼스 콘솔에 Redirect URI `https://notion-kakao-schedule.onrender.com/kakao/callback` 등록 완료
- [x] "카카오 연결" 버튼으로 배포 환경에서 OAuth 재인증 완료 (연결 상태 ✅ 확인)
- [x] "지금 테스트 전송"으로 배포 환경 end-to-end 검증 완료 (2026-09-05 14:30 성공, Notion 일정 정상 수신)
- [x] UptimeRobot으로 5분 간격 핑 설정 완료 (2026-09-05, `notion-kakao-schedule.onrender.com` 모니터링 중)
- [ ] 알림 시각 08:00 자동 발송이 실제로 되는지 하루 지켜보고 확인

## 그다음 이어서 할 수 있는 작업 (v2 로드맵)
- Capacitor로 하이브리드 앱 패키징 (iOS/Android)
- Google Calendar / Apple Calendar 등 캘린더 어댑터 추가

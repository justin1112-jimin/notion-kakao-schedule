# CLAUDE.md

## 프로젝트 개요
Notion을 비롯한 여러 캘린더/일정 앱에서 **오늘 날짜의 일정**을 가져와, 매일 아침 **카카오톡 "나에게 보내기"**로 요약 메시지를 자동 전송하는 자동화 도구.

- **v1 (완료)**: 개인용 로컬 스크립트. Notion 단일 소스, macOS launchd로 무인 실행
- **v2 (진행 예정)**: 모바일 앱(iOS/Android)으로 전환. Notion 외 Google Calendar / Apple Calendar 등 여러 캘린더 소스를 연동해 일정 데이터를 통합

---

## v1 — 현재 완료된 로컬 스크립트 버전

### 아키텍처 / 데이터 흐름
```
Notion DB (오늘 일정 조회)
      ↓
notify.py 가 필터링 + 메시지 포맷팅
      ↓
카카오 리프레시 토큰으로 액세스 토큰 갱신
      ↓
카카오톡 "나에게 보내기" API로 전송
```

### 파일 구성
| 파일 | 역할 |
|---|---|
| `notify.py` | 매일 실행되는 메인 스크립트. Notion 조회 → 메시지 생성 → 카카오 토큰 갱신 → 전송까지 전체 담당 |
| `get_kakao_token.py` | 최초 1회만 실행. 로컬 웹서버(포트 8888)를 띄워 카카오 OAuth 인가 코드를 받고, refresh token을 발급받아 `.env`에 저장 |
| `.env.example` | 필요한 환경변수 템플릿 |
| `com.user.notionkakao.plist` | macOS launchd 스케줄 등록 파일 (매일 08:00 실행) |
| `README.md` | 설정 가이드 (Notion 통합 생성 → 카카오 앱 생성 → 인증 → 스케줄 등록) |

### 환경 변수 (.env)
- `NOTION_TOKEN`, `NOTION_DATABASE_ID`, `NOTION_DATE_PROPERTY`, `NOTION_TITLE_PROPERTY`
- `KAKAO_REST_API_KEY`, `KAKAO_REFRESH_TOKEN`(자동 채워짐)

### v1 알려진 제약사항
- macOS가 잠자기 상태면 launchd 스케줄이 실행되지 않을 수 있음
- Notion 속성 이름은 자동 감지가 아니라 사용자가 직접 확인 후 입력해야 함
- 단일 사용자, 단일 캘린더 소스(Notion)만 지원

---

## v2 — 모바일 앱 확장 계획

### 목표
- 로컬 스크립트/PC 의존성을 없애고, 모바일 앱에서 캘린더 연동 설정과 알림 시각 관리를 할 수 있게 한다
- Notion 외에 Google Calendar, Apple Calendar(CalDAV), Outlook 등 여러 캘린더 소스를 동시에 조회해 하나의 요약 메시지로 통합한다

### 아키텍처 변경 방향
로컬 스크립트 단독 실행 구조에서, **모바일 앱 + 백엔드 서버 + 캘린더 어댑터 계층** 구조로 전환.

```
[모바일 앱] --(캘린더 연동 OAuth, 알림 시각 설정)--> [백엔드 서버]
                                                          ↓
                                              [스케줄러: Cloud Function / Cron]
                                                          ↓
                     [캘린더 어댑터: Notion / Google Calendar / Apple Calendar / Outlook]
                                                          ↓
                                              일정 병합 + 메시지 포맷팅
                                                          ↓
                                        카카오 "나에게 보내기" API 전송
```

**왜 서버가 필요한가**: iOS는 백그라운드 실행 제약이 강해서 앱 자체가 매일 아침 정해진 시각에 스스로 깨어나 실행되는 걸 보장할 수 없음. macOS launchd가 하던 "매일 정해진 시각 실행" 역할을 백엔드 스케줄러(Cloud Function/Cron)가 대신 맡아야 함.

### 신규 컴포넌트
| 컴포넌트 | 역할 |
|---|---|
| 모바일 앱 (React Native 등) | 캘린더 계정 연동 UI, 알림 시각 설정, 오늘 일정 미리보기 |
| 백엔드 API 서버 | 사용자별 캘린더 연동 토큰 저장, 알림 설정 관리, 스케줄러 트리거 |
| 캘린더 어댑터 계층 | Notion/Google/Apple/Outlook 등 서로 다른 API를 공통 인터페이스로 추상화해 "오늘 일정 리스트"로 정규화 |
| 스케줄러 (Cloud Function/Cron) | 서버가 상시 켜져 있을 필요 없이 매일 정해진 시각에 실행 (로컬 launchd 대체) |

### v1 → v2 마이그레이션 전략
1. `notify.py`의 Notion 조회 로직을 그대로 "Notion 어댑터"로 재사용
2. 카카오 토큰 갱신/저장 로직을 `.env` 파일 방식에서 서버 DB(암호화 저장)로 이식
3. Google Calendar 어댑터 우선 추가 (OAuth 표준적이고 API 문서 잘 정리되어 있어 난이도 낮음) → 이후 Apple/Outlook 확장
4. 모바일 앱에서 캘린더 연동 설정 UI 제공 (연동 계정 추가/삭제, 알림 시각 변경)

### v2에서 아직 정해지지 않은 사항 (다음 논의 필요)
- 백엔드 호스팅: Supabase / Firebase / 자체 서버 중 선택
- 모바일 프레임워크: React Native vs Flutter vs 네이티브(Swift/Kotlin)
- 1인용으로 유지할지, 추후 다른 사용자에게도 배포할지 — 이 결정에 따라 카카오 비즈니스 심사 필요 여부가 갈림

### v2 알려진 제약사항 / 리스크
- 카카오 "나에게 보내기"(memo API)는 앱에 등록된 테스트 사용자(최대 100명)까지는 별도 심사 없이 사용 가능하지만, 다수 사용자 대상으로 확장하면 카카오 비즈니스 채널 심사가 필요함
- 캘린더 소스가 늘어날수록 사용자별 OAuth 토큰이 여러 개 쌓이므로, 서버 측 토큰 저장 보안(암호화, 만료 처리)이 v1보다 훨씬 중요해짐
- Apple Calendar는 CalDAV 기반이라 Google Calendar보다 연동 난이도가 높음 (OAuth가 아닌 앱 암호/CalDAV 인증 방식)

---

## 현재 상태
- v1: 코드/스크립트/README/launchd 설정 파일까지 전부 작성 완료. 사용자가 Notion 통합 생성, 카카오 앱 생성, 최초 인증(`get_kakao_token.py` 실행), launchd 등록을 아직 직접 수행해야 함
- v2: 아키텍처 방향만 정해진 상태, 실제 구현은 미착수

## 다음에 이어서 할 수 있는 작업
- 백엔드 호스팅 플랫폼 및 모바일 프레임워크 선택
- Google Calendar 어댑터부터 구현 시작
- 카카오 토큰 저장 방식을 `.env` → 서버 DB로 이식하는 작업 설계
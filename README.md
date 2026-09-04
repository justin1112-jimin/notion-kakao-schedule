# Notion → 카카오톡 오늘 일정 알림 자동화

Notion 데이터베이스에서 오늘 날짜의 일정을 가져와, 매일 아침 카카오톡 "나에게 보내기"로 요약해서 보내주는 개인용 자동화 도구입니다.

## 폴더 구성
```
notion-kakao-schedule/
├── notify.py                    # 매일 실행되는 메인 스크립트
├── get_kakao_token.py           # 최초 1회만 실행하는 카카오 인증 스크립트
├── requirements.txt
├── .env.example                 # 이 파일을 복사해서 .env로 만들고 값 채우기
└── com.user.notionkakao.plist   # macOS 스케줄러(launchd) 등록 파일
```

## 1단계. 환경 준비

```bash
cd notion-kakao-schedule
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt
cp .env.example .env
```

## 2단계. Notion 연동 설정

1. https://www.notion.so/my-integrations 에서 **New integration** 생성 → Internal Integration Token 복사 → `.env`의 `NOTION_TOKEN`에 붙여넣기
2. 일정이 있는 Notion 데이터베이스 페이지 우측 상단 `•••` → **연결(Connections)** → 방금 만든 통합 추가 (이 단계를 빼먹으면 API가 데이터베이스를 못 읽습니다)
3. 데이터베이스 URL에서 32자리 ID를 복사해 `NOTION_DATABASE_ID`에 입력
   - 예: `notion.so/xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx?v=...` → `xxxx...` 부분
4. 본인 데이터베이스의 실제 속성 이름을 확인해서 `NOTION_DATE_PROPERTY`(날짜 속성), `NOTION_TITLE_PROPERTY`(제목 속성)에 입력

## 3단계. 카카오 개발자 앱 설정

1. https://developers.kakao.com → 애플리케이션 추가
2. **앱 키 > REST API 키** 복사 → `.env`의 `KAKAO_REST_API_KEY`에 입력
3. **제품 설정 > 카카오 로그인** 활성화
4. **Redirect URI**에 `http://localhost:8888/oauth` 추가
5. **동의항목**에서 "카카오톡 메시지 전송(talk_message)" 항목을 선택 동의로 설정
   - 참고: 개인 개발자 계정은 별도 심사 없이 본인 카카오 계정으로 "나에게 보내기"를 바로 사용할 수 있습니다.

## 4단계. 최초 인증 (딱 한 번만)

```bash
python get_kakao_token.py
```
브라우저가 열리면 본인 카카오 계정으로 로그인 + 동의 → 자동으로 `.env`에 `KAKAO_REFRESH_TOKEN`이 저장됩니다.

## 5단계. 테스트 실행

```bash
python notify.py
```
카카오톡 "나에게 보내기" 채팅방으로 오늘 일정 요약이 오면 성공입니다.

## 6단계. 매일 아침 자동 실행 등록 (macOS)

```bash
# plist 파일의 YOUR_USERNAME과 경로를 본인 환경에 맞게 수정 후:
cp com.user.notionkakao.plist ~/Library/LaunchAgents/
launchctl load ~/Library/LaunchAgents/com.user.notionkakao.plist
```
기본값은 매일 **오전 8시** 실행이며, plist의 `Hour`/`Minute` 값을 바꾸면 시간 변경 가능합니다.

등록 해제하려면:
```bash
launchctl unload ~/Library/LaunchAgents/com.user.notionkakao.plist
```

## 참고 사항
- 카카오 액세스 토큰은 6시간마다 만료되지만, `notify.py`가 실행될 때마다 리프레시 토큰으로 자동 갱신합니다.
- 카카오 리프레시 토큰 자체도 보안 정책상 주기적으로 회전(rotate)될 수 있는데, 새 값이 오면 스크립트가 자동으로 `.env`를 갱신하므로 별도 조치가 필요 없습니다.
- 맥이 잠자기 모드(sleep)이면 launchd 스케줄이 실행되지 않을 수 있습니다. 항상 켜두는 컴퓨터가 아니라면, 나중에 GitHub Actions 등 클라우드 스케줄러로 옮기는 것도 방법입니다 (이 경우 리프레시 토큰을 GitHub Secrets에 자동 반영하는 로직이 추가로 필요해요 — 필요하시면 확장해드릴게요).

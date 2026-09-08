---
name: test-deploy
description: Render 배포 직후 /settings, /dashboard, /api/send-history 엔드포인트가 정상 작동하는지 빠르게 검증합니다. 배포 후 "엔드포인트 테스트", "배포 확인", "test-deploy" 등의 명령으로 즉시 사용하세요.
---

# test-deploy 스킬

Render에 배포된 notion-kakao-schedule 서비스의 핵심 엔드포인트를 자동 테스트합니다.

## 테스트 항목

| 엔드포인트 | 목적 | 예상 상태 |
|-----------|------|---------|
| `/settings` | 설정 페이지 | 200 또는 302 |
| `/dashboard` | 발송 이력 대시보드 | 200 |
| `/api/send-history` | JSON API | 200 |
| `/login` | 로그인 페이지 | 302 또는 200 |

## 실행

```bash
test-deploy
```

## 결과 예시

```
🧪 배포 테스트 시작: https://notion-kakao-schedule.onrender.com
✅ /settings: OK (200)
✅ /dashboard: OK (200)
✅ /api/send-history: OK (200)
✅ /login: OK (302)
✨ 배포 테스트 완료!
```

## 상태 코드 해석

- **200**: ✅ 정상
- **302**: 리다이렉트 (로그인 필수)
- **500**: ❌ 서버 오류 (Render 로그 확인)
- **503**: 배포 진행 중 (잠시 후 재시도)

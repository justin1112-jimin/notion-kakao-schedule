---
name: deploy-render
description: Git 변경사항을 Render에 자동으로 배포합니다. "배포하기", "push하고 배포", "변경사항 적용", "deploy-render" 등으로 Git push부터 배포 완료까지 한 번에 처리하세요.
---

# deploy-render 스킬

Git 변경사항을 Render로 자동 배포합니다.

## 배포 프로세스

1. **Git 상태 확인**
   - 커밋되지 않은 변경사항 확인
   - 배포 준비 상태 체크

2. **Git Push**
   - 현재 브랜치를 origin으로 push

3. **Render 배포 감시**
   - 배포 시작 대기
   - 실시간 배포 로그 모니터링
   - 배포 완료 확인

4. **배포 후 검증**
   - 엔드포인트 상태 확인 (test-deploy 자동 실행)
   - 배포 성공 여부 판단

## 실행

```bash
deploy-render
```

## 결과 예시

```
🚀 Render 배포 시작

📋 Git 상태 확인...
✅ 커밋 준비 완료

📤 Git Push...
[main abc1234] Fix: 대시보드 필터 버그
 1 file changed, 15 insertions(+)
✅ Push 완료

⏳ Render 배포 감시...
🔄 배포 시작됨 (2026-09-08 15:45:30)
📊 빌드 진행 중... (30% 완료)
📊 빌드 진행 중... (60% 완료)
📊 빌드 완료! 
🚀 배포 진행 중... (60% 완료)
✅ 배포 완료! (2026-09-08 15:47:15)

🧪 배포 후 검증...
✅ /settings: OK (200)
✅ /dashboard: OK (200)
✅ /api/send-history: OK (200)

🎉 배포 성공!
```

## 배포 실패 시

배포 중 오류가 발생하면:

1. **Render 대시보드에서 직접 로그 확인**
   - https://dashboard.render.com
   - notion-kakao-schedule 서비스 선택
   - "Logs" 탭에서 오류 메시지 확인

2. **일반적인 오류**
   - `requirements.txt 설치 오류`: 패키지 버전 확인
   - `환경변수 누락`: 환경변수 재확인
   - `포트 바인딩 오류`: 다른 프로세스 종료

## 주의사항

- main 브랜치로만 배포됩니다
- 배포 시간은 보통 2-3분 소요됩니다
- 배포 중 서비스가 일시적으로 불가능할 수 있습니다

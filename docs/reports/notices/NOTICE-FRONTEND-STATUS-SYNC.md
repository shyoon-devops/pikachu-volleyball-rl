# Frontend Engineer → DevOps: Frontend 재배포 요청 (CRITICAL 핫픽스)

> **Date**: 2026-04-12 | **From**: Frontend Engineer
> **To**: DevOps | **Priority**: CRITICAL — refresh 시 UI 오동작

---

## 요약

사용자 피드백 CRITICAL 버그 수정 `dev`에 머지 완료. **프론트엔드 번들 재배포 필요**.

- Branch: `yoon/frontend-engineer`
- Merged into: `dev`
- 변경 영역: `frontend/src/hooks/useTrainingState.ts` + 테스트

## 증상

1. 학습 실행 중 새로고침(F5)하면 **Start 버튼**이 노출 (Stop이 아니라)
2. 결과적으로 사용자가 Stop을 누를 수 없음 (Stop 버튼이 화면에 없음)

## Root cause

`useTrainingStateImpl` 의 `status` 초기값이 `{ state: 'stopped', ... }` 하드코딩.
WebSocket `training:status` 메시지는 상태가 **변경될 때만** 방송되므로, 이미 running 중인 세션에 새로 접속하면 브라우저는 "stopped" 상태로 남음.
→ `TrainingControls` 는 Start 버튼만 렌더링, Stop 버튼은 DOM에 존재하지 않음.

## Fix

`useTrainingStateImpl` 에 REST 기반 초기 동기화 추가:

1. **마운트 시**: `GET /api/training/status` 한 번 호출 → 현재 서버 상태 반영
2. **WS 재연결 시**: `connectionState === 'connected'` 로 전환될 때마다 재fetch
3. 에러는 silent — WS 가 여전히 live channel 로 동작

```typescript
// mount-time sync
useEffect(() => {
  let cancelled = false
  getTrainingStatus().then(fresh => { if (!cancelled) setStatus(prev => ({ ...prev, ...fresh })) })
  return () => { cancelled = true }
}, [])

// reconnect sync
useEffect(() => {
  if (connectionState !== 'connected') return
  // same fetch
}, [connectionState])
```

## Tests

- `frontend/src/hooks/useTrainingState.test.tsx` 신규 (3 tests)
  - mount 시 REST fetch 수행 + status running 반영
  - WS 재연결 시 재fetch
  - REST 실패 시 silent fallback
- `frontend/src/components/dashboard/Dashboard.test.tsx` 회귀 가드 추가
  - **"page loads with active training → shows Stop, not Start"**

전체 테스트: **141 passed / 17 files** — tsc clean, ESLint clean.

## 배포 요청

**DEV 환경 frontend 번들 재배포** 요청드립니다.

- 기존 번들: `JHqpaRFn` (BE WS 핫픽스 `7b5b4d6d` 시점)
- 필요 동작: `/frontend` 재빌드 + 3개 환경 동기화

## 검증 방법 (배포 후)

1. DEV URL 접속 → 훈련 시작 → 새로고침(F5)
2. 새로고침 직후 **Stop** 버튼이 보여야 함 (Start 아님)
3. Stop 클릭 → WS `training:stop` 전송 → 훈련 중단 정상 동작
4. DevTools → Network 탭에서 마운트 시 `/api/training/status` 요청 확인

## 관련 이슈

- 이전 커밋: `9f050c87 fix(ui): remove duplicate Start button, unify training controls`
- 이전 번들: `JHqpaRFn` (이미 배포, 이번 수정 미포함)

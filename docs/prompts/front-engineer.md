# Front Engineer Prompt

## Role
너는 Pikachu Volleyball RL 프로젝트의 **Front Engineer**야.
React + TypeScript + PixiJS 프론트엔드 전체를 담당해.

## Context
프로젝트 전체 계획은 `docs/PLAN.md`를 반드시 먼저 읽어.
CLAUDE.md도 읽어서 프로젝트 구조와 컨벤션을 파악해.

## Your Scope — 수정할 파일
```
frontend/package.json
frontend/tsconfig.json
frontend/vite.config.ts
frontend/index.html
frontend/src/main.tsx
frontend/src/App.tsx
frontend/src/components/game/GameCanvas.tsx
frontend/src/components/game/sprites.ts
frontend/src/components/game/GameOverlay.tsx
frontend/src/components/dashboard/Dashboard.tsx
frontend/src/components/dashboard/MetricsChart.tsx
frontend/src/components/dashboard/TrainingControls.tsx
frontend/src/components/dashboard/HyperparamForm.tsx
frontend/src/components/replay/ReplayList.tsx
frontend/src/components/replay/ReplayPlayer.tsx
frontend/src/components/replay/ReplayControls.tsx
frontend/src/components/evaluation/EvalPanel.tsx
frontend/src/components/evaluation/EvalChart.tsx
frontend/src/hooks/useWebSocket.ts
frontend/src/hooks/useTrainingState.ts
frontend/src/lib/api.ts
frontend/src/lib/types.ts
frontend/Dockerfile
```

**backend/ 디렉토리는 절대 수정하지 마.**

## Tasks — Wave 1 (병렬 시작 가능)

### Task 1: 프로젝트 초기화
```bash
cd frontend
npm create vite@latest . -- --template react-ts
npm install pixi.js @pixi/react recharts react-router-dom
npm install -D @types/react @types/react-dom vitest @testing-library/react
```

vite.config.ts에 proxy 설정:
```typescript
server: {
  proxy: {
    '/api': 'http://localhost:8000',
    '/ws': { target: 'ws://localhost:8000', ws: true }
  }
}
```

### Task 2: TypeScript 타입 정의
`frontend/src/lib/types.ts`:
```typescript
interface PlayerState {
  x: number; y: number; vx: number; vy: number;
  isJumping: boolean; isDiving: boolean; isPowerHitting: boolean;
}

interface BallState {
  x: number; y: number; vx: number; vy: number;
  rotation: number;
}

interface GameState {
  player1: PlayerState; player2: PlayerState; ball: BallState;
  score1: number; score2: number; frame: number;
}

interface TrainingMetrics {
  step: number; episode: number; reward: number;
  winRate: number; loss: number;
}

interface GameRecord {
  id: string; timestamp: string; botLevel: number;
  score1: number; score2: number; winner: number;
  durationFrames: number; rallyCount: number;
}

interface EvalResult {
  modelPath: string; botLevel: number; nGames: number;
  winRate: number; avgScore: number; avgRallyLength: number;
}

// WebSocket 메시지 타입
type WSMessageType = 
  | 'training:metrics' | 'training:frame' | 'training:status'
  | 'game:result' | 'replay:data';

interface WSMessage<T = unknown> {
  type: WSMessageType; payload: T;
}
```

### Task 3: GameCanvas (PixiJS)
`frontend/src/components/game/GameCanvas.tsx`:
- PixiJS Application으로 코트 렌더링
- 코트 크기: 432x304 (스케일링하여 컨테이너에 맞춤)
- 초록 바닥, 네트 (중앙), 두 피카추 (왼쪽=노랑, 오른쪽=빨강 원 또는 사각형), 공 (노란 원)
- GameState props를 받아 매 프레임 위치 업데이트
- 30fps 입력 → 60fps 보간 (lerp)

`frontend/src/components/game/GameOverlay.tsx`:
- 점수 표시 (Score1 : Score2)
- 게임 상태 텍스트 (서빙, 라운드 종료 등)

### Task 4: WebSocket Hook
`frontend/src/hooks/useWebSocket.ts`:
```typescript
function useWebSocket(url: string) {
  // WebSocket 연결 관리
  // 자동 재연결 (exponential backoff: 1s, 2s, 4s, max 30s)
  // 메시지 타입별 콜백 등록
  // send(type, payload) 메서드
  // connectionState: 'connecting' | 'connected' | 'disconnected'
}
```

`frontend/src/hooks/useTrainingState.ts`:
```typescript
function useTrainingState() {
  // useWebSocket 사용
  // training:metrics → metrics 배열에 누적
  // training:frame → 최신 GameState 업데이트
  // training:status → status 업데이트
  // game:result → recentGames 배열에 추가
}
```

## Tasks — Wave 3 (Backend API 완료 후)

### Task 5: Dashboard
`frontend/src/components/dashboard/Dashboard.tsx`:
- docs/PLAN.md "4.2 Dashboard 레이아웃" 참조
- 왼쪽: TrainingControls + Live GameCanvas
- 오른쪽: MetricsChart들 (reward, win_rate, loss)
- 하단: Recent Games 테이블

`frontend/src/components/dashboard/MetricsChart.tsx`:
- Recharts LineChart
- X축: step 또는 episode, Y축: metric 값
- 실시간으로 데이터 추가 (최근 1000 포인트 유지)

`frontend/src/components/dashboard/TrainingControls.tsx`:
- Start / Stop / Resume 버튼
- 봇 레벨 셀렉터 (1~5)
- 현재 상태 표시 (running/stopped/paused)
- step/episode 카운터

`frontend/src/components/dashboard/HyperparamForm.tsx`:
- learning_rate, n_steps, batch_size, gamma, clip_range 입력 필드
- Start 버튼 클릭 시 값 전달

### Task 6: Replay
`frontend/src/components/replay/ReplayList.tsx`:
- REST API `/api/games`에서 히스토리 로드
- 테이블: 날짜, 봇 레벨, 점수, 승패, 리플레이 버튼
- 페이지네이션

`frontend/src/components/replay/ReplayPlayer.tsx`:
- `/api/replays/{game_id}`에서 프레임 데이터 로드
- GameCanvas에 현재 프레임 전달
- 재생/일시정지 토글
- 배속: 0.5x, 1x, 2x, 4x
- 시크바 (프레임 인덱스 기반)

### Task 7: Evaluation
`frontend/src/components/evaluation/EvalPanel.tsx`:
- 모델 목록 로드 (`/api/models`)
- 평가 트리거: 모델 선택 + 봇 레벨 + n_games → POST `/api/evaluation/run`
- 결과 테이블: 모델별 win_rate, avg_score, avg_rally_length

`frontend/src/components/evaluation/EvalChart.tsx`:
- Recharts BarChart 또는 LineChart
- X축: 모델 버전, Y축: win_rate
- 난이도별 필터

### Task 8: App Router
`frontend/src/App.tsx`:
```tsx
<BrowserRouter>
  <Routes>
    <Route path="/" element={<Dashboard />} />
    <Route path="/replay/:id" element={<ReplayPlayer />} />
    <Route path="/evaluation" element={<EvalPanel />} />
  </Routes>
</BrowserRouter>
```

네비게이션 바: Dashboard | History | Evaluation

### Task 9: API Client
`frontend/src/lib/api.ts`:
- fetch 래퍼 (base URL, error handling)
- `getGames(page, limit)`, `getReplay(gameId)`, `getModels()`, `runEvaluation(...)`, `getEvalResults()`

## Design Direction
- **깔끔한 다크 모드** 대시보드 스타일
- 게임 캔버스는 레트로 느낌 (원본 게임 분위기)
- 차트는 밝은 컬러로 가독성 확보
- 반응형 레이아웃 (최소 1024px)

## Tech & Skills
- `/frontend-design` 스킬 참고
- `/e2e` 스킬로 E2E 테스트
- React 18, TypeScript strict, PixiJS 7+, Recharts, React Router v6
- Vite, Vitest, ESLint, Prettier

## Dependencies
- **Wave 1 선행**: 없음 (UI 스켈레톤, 게임 캔버스, WebSocket 훅은 즉시 시작)
- **Wave 3 선행**: Backend API + WebSocket 완료 필수 (실제 데이터 연동)
- **후행**: Docker 통합 시 Dockerfile 필요

## Acceptance Criteria
- [ ] `npm run build` 에러 없이 성공
- [ ] `npm run lint` 에러 없음
- [ ] Dashboard에서 게임 캔버스가 렌더링됨
- [ ] WebSocket 연결/재연결 정상 동작
- [ ] 차트에 메트릭 데이터 표시
- [ ] 리플레이 재생 (재생/일시정지/배속/시크바)
- [ ] 평가 트리거 및 결과 표시

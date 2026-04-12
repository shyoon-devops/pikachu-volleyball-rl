# Pikachu Volleyball RL — Implementation Plan

## 1. Game Engine Spec (`backend/game/`)

### 1.1 Constants (`constants.py`)

| Constant | Value | Note |
|----------|-------|------|
| GROUND_WIDTH | 432 | 코트 너비 |
| GROUND_HEIGHT | 304 | 코트 높이 |
| NET_PILLAR_X | 216 | 네트 중앙 X |
| NET_PILLAR_HALF_WIDTH | 25 | 네트 기둥 반폭 |
| NET_PILLAR_TOP_Y | 176 | 네트 상단 Y |
| PLAYER_HALF_LENGTH | 32 | 플레이어 반지름 (64x64) |
| PLAYER_GROUND_Y | 244 | 플레이어 바닥 Y |
| PLAYER_SPEED | 6 | 이동 속도 |
| PLAYER_DIVE_SPEED | 8 | 다이브 속도 |
| PLAYER_JUMP_VELOCITY | -16 | 점프 초기 속도 |
| PLAYER_DIVE_VELOCITY | -5 | 다이브 초기 속도 |
| BALL_RADIUS | 20 | 공 반지름 |
| BALL_GROUND_Y | 252 | 공 바닥 Y |
| BALL_INIT_Y_VELOCITY | 1 | 공 초기 Y속도 |
| GRAVITY | 1 | 중력 |
| MAX_SCORE | 15 | 게임 종료 점수 |
| FPS | 30 | 게임 프레임레이트 |

### 1.2 Engine (`engine.py`)

**데이터 클래스:**
```python
@dataclass
class PlayerState:
    x: int; y: int; vx: int; vy: int
    is_jumping: bool; is_diving: bool; is_power_hitting: bool
    lying_down_duration: int

@dataclass
class BallState:
    x: int; y: int; vx: int; vy: int
    rotation: int; punch_effect_x: int; punch_effect_y: int

@dataclass
class GameState:
    player1: PlayerState; player2: PlayerState; ball: BallState
    score1: int; score2: int; serving_player: int
    is_round_over: bool; frame: int

PlayerInput = NamedTuple('PlayerInput', [('x_dir', int), ('y_dir', int), ('power_hit', bool)])
```

**PikachuVolleyball 클래스:**
- `reset() → GameState`
- `step(p1_input, p2_input) → GameState`
- 내부: `_update_player`, `_update_ball`, `_check_ball_player_collision`, `_check_ball_net_collision`, `_check_ball_boundary_collision`, `_check_scoring`

**물리 규칙:**
- 공-플레이어 충돌: `|ball.x - player.x| ≤ 32 AND |ball.y - player.y| ≤ 32`
- 충돌 시 ball.vy = `min(ball.vy, -15)`
- 충돌 시 ball.vx = `(|ball.x - player.x| / 3)` (방향은 플레이어 반대)
- 파워 히트: vx = `±(|input_x| + 1) * 10`, vy = `|original_vy| * input_y * 2`
- 득점: `ball.y >= BALL_GROUND_Y` → 반대편 점수
- 네트 충돌: `|ball.x - NET_PILLAR_X| < NET_PILLAR_HALF_WIDTH AND ball.y > NET_PILLAR_TOP_Y` → vx 반전

### 1.3 Rule-based Bot (`bot.py`)

| Parameter | L1 | L2 | L3 | L4 | L5 |
|-----------|-----|-----|-----|-----|-----|
| reaction_delay (frames) | 8 | 5 | 3 | 1 | 0 |
| prediction_error | 0.4 | 0.25 | 0.15 | 0.05 | 0.0 |
| miss_probability | 0.15 | 0.08 | 0.04 | 0.01 | 0.0 |
| move_range | 0.6 | 0.75 | 0.85 | 0.95 | 1.0 |
| jump_timing_error (frames) | 4 | 3 | 2 | 1 | 0 |

**봇 전략:**
1. 공 궤적 예측 (단순 포물선 외삽 + prediction_error 노이즈)
2. 예측 착지점으로 이동 (move_range 내)
3. 공 가까이 + 하강 중 → 점프 (jump_timing_error 적용)
4. 공중 + 공 근접 → 파워 히트 시도 (레벨 비례 확률)
5. miss_probability → 해당 프레임 no-op

---

## 2. RL Environment Spec (`backend/rl/`)

### 2.1 Gymnasium 환경 (`env.py`)

```
observation_space = Box(low=-1, high=1, shape=(12,), dtype=float32)
# [p1.x, p1.y, p1.vx, p1.vy, p2.x, p2.y, ball.x, ball.y, ball.vx, ball.vy, score_diff, serving]

action_space = Discrete(6)
# 0=noop, 1=left, 2=right, 3=jump, 4=left+jump, 5=right+jump
# 파워 히트는 점프 중 공 근접 시 자동 발동
```

**Reward:**
| Event | Reward |
|-------|--------|
| 득점 | +10.0 |
| 실점 | -10.0 |
| 게임 승리 | +20.0 |
| 게임 패배 | -20.0 |
| 공 터치 (랠리) | +0.5 |
| 공이 상대 코트에 있을 때 | +0.1/frame |
| 시간 패널티 | -0.01/frame |

### 2.2 Training Pipeline (`trainer.py`)

**TrainingManager 클래스:**
- `start(hyperparams, bot_level)` → 백그라운드 스레드 시작
- `stop()` → 그레이스풀 정지
- `resume()` → 최근 체크포인트에서 재개
- `set_bot_level(level)` → 커리큘럼 러닝
- `status` → "running" | "stopped" | "paused"

**기본 하이퍼파라미터:**
```python
learning_rate: 3e-4, n_steps: 2048, batch_size: 64, n_epochs: 10,
gamma: 0.99, gae_lambda: 0.95, clip_range: 0.2, ent_coef: 0.01,
policy: "MlpPolicy", net_arch: [256, 256]
```

SubprocVecEnv 8개 병렬 환경.

### 2.3 Callbacks (`callbacks.py`)

- **MetricsCallback**: N step마다 reward/loss/win_rate → asyncio.Queue
- **CheckpointCallback**: K step마다 `models/{experiment_id}/{step}.zip` 저장
- **LiveFrameCallback**: 주기적으로 1게임 실행, 프레임 데이터 → Queue

### 2.4 Evaluator (`evaluator.py`)

- `evaluate(model_path, bot_level, n_games=50) → EvalResult`
- `compare_checkpoints(paths, bot_level) → list[EvalResult]`
- EvalResult: win_rate, avg_score, avg_rally_length

---

## 3. Backend API Spec (`backend/app/`)

### 3.1 REST Endpoints

| Method | Path | Purpose |
|--------|------|---------|
| GET | /api/health | Health check |
| GET | /api/training/status | 훈련 상태 |
| GET | /api/games | 게임 히스토리 (페이지네이션) |
| GET | /api/games/{id} | 단일 게임 상세 |
| GET | /api/replays/{game_id} | 리플레이 프레임 데이터 |
| GET | /api/models | 체크포인트 목록 |
| POST | /api/evaluation/run | 평가 실행 트리거 |
| GET | /api/evaluation/results | 평가 결과 |

### 3.2 WebSocket (`/ws`)

**Client → Server:**
```json
{ "type": "training:start", "payload": { "hyperparams": {...}, "bot_level": 1 } }
{ "type": "training:stop" }
{ "type": "training:resume" }
{ "type": "training:set_level", "payload": { "level": 3 } }
{ "type": "replay:request", "payload": { "game_id": "..." } }
```

**Server → Client:**
```json
{ "type": "training:metrics", "payload": { "step": 1000, "episode": 50, "reward": 3.2, "win_rate": 0.45, "loss": 0.12 } }
{ "type": "training:frame", "payload": { "player1": {...}, "player2": {...}, "ball": {...}, "score1": 3, "score2": 2 } }
{ "type": "game:result", "payload": { "game_id": "...", "score1": 15, "score2": 10, "winner": 1, "duration_frames": 4500, "rally_count": 23 } }
{ "type": "training:status", "payload": { "state": "running", "current_step": 5000, "current_episode": 250 } }
{ "type": "replay:data", "payload": { "frames": [...] } }
```

### 3.3 MongoDB Collections

- **games**: `{ _id, experiment_id, timestamp, bot_level, score1, score2, winner, duration_frames, rally_count }`
- **metrics**: `{ _id, experiment_id, step, episode, reward, win_rate, loss, timestamp }`
- **evaluations**: `{ _id, model_path, bot_level, n_games, win_rate, avg_score, avg_rally_length, timestamp }`

### 3.4 Replay Storage

- 포맷: msgpack 직렬화 → `replays/{game_id}.msgpack`
- 자동 정리: 최근 1000개 유지

---

## 4. Frontend Spec (`frontend/src/`)

### 4.1 페이지 구조

| Route | Component | 설명 |
|-------|-----------|------|
| / | Dashboard | 훈련 대시보드 (메트릭 + 라이브 게임) |
| /replay/:id | ReplayPlayer | 리플레이 재생 |
| /evaluation | EvalPanel | 모델 평가 비교 |

### 4.2 Dashboard 레이아웃
```
┌─────────────────────────────────────────────┐
│  Training Controls    │  Status / Counters   │
├───────────────────────┤                      │
│  Live Game Canvas     │  Reward Chart        │
│  (PixiJS)             │  Win Rate Chart      │
│                       │  Loss Chart          │
├───────────────────────┴──────────────────────┤
│  Recent Games Table                          │
└──────────────────────────────────────────────┘
```

### 4.3 핵심 컴포넌트

- **GameCanvas.tsx**: PixiJS 렌더러. GameState → 코트/피카추/공 시각화. 30fps 프레임을 60fps로 보간.
- **MetricsChart.tsx**: Recharts 라인 차트 (reward, win_rate, loss)
- **TrainingControls.tsx**: 시작/중지/재개 버튼 + 봇 레벨 셀렉터
- **HyperparamForm.tsx**: 하이퍼파라미터 입력 폼
- **ReplayPlayer.tsx**: 재생/일시정지/배속/시크바
- **EvalPanel.tsx**: 평가 트리거 + 버전 비교 테이블/차트

### 4.4 Hooks

- **useWebSocket.ts**: `ws://host:8000/ws` 연결, 자동 재연결, 메시지 디스패치
- **useTrainingState.ts**: WS 메시지 → training state 관리

---

## 5. Docker Compose

```yaml
services:
  mongodb:
    image: mongo:7
    ports: ["27017:27017"]
  backend:
    build: ./backend
    ports: ["8000:8000"]
    volumes: [./models:/app/models, ./replays:/app/replays]
    deploy.resources.reservations.devices: [nvidia gpu]
    depends_on: [mongodb]
  frontend:
    build: ./frontend
    ports: ["5173:80"]
    depends_on: [backend]
```

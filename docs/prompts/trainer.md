# Trainer Prompt

## Role
너는 Pikachu Volleyball RL 프로젝트의 **Trainer**야.
SB3 PPO 훈련 파이프라인과 콜백 시스템을 담당해.

## Context
프로젝트 전체 계획은 `docs/PLAN.md`를 반드시 먼저 읽어.
CLAUDE.md도 읽어서 프로젝트 구조와 컨벤션을 파악해.

## Prerequisites
AI Engineer가 완성한 파일들을 먼저 확인해:
- `backend/game/engine.py` — 게임 엔진
- `backend/game/bot.py` — Rule-based 봇
- `backend/rl/env.py` — Gymnasium 환경

이 파일들이 존재하고 테스트가 통과하는지 확인 후 작업 시작해.

## Your Scope — 수정할 파일
```
backend/rl/trainer.py        # TrainingManager 클래스
backend/rl/callbacks.py      # SB3 콜백들
backend/tests/test_trainer.py # 훈련 테스트
backend/pyproject.toml       # 의존성 추가 (필요시)
```

**다른 디렉토리(app/, frontend/, game/ 등)는 절대 수정하지 마.**

## Tasks (순서대로)

### Task 1: Callbacks
`backend/rl/callbacks.py` 작성.

**MetricsCallback(BaseCallback):**
- `_on_step()`: N step마다 (기본 100) 메트릭 수집
- 메트릭: step, episode, mean_reward, win_rate, policy_loss, value_loss
- `asyncio.Queue`에 dict로 push (생성자에서 queue 받음)
- win_rate는 최근 100 에피소드 기준

**CheckpointCallback(BaseCallback):**
- K step마다 (기본 10000) 모델 저장
- 경로: `models/{experiment_id}/{step}.zip`
- 디렉토리 자동 생성

**LiveFrameCallback(BaseCallback):**
- M step마다 (기본 5000) 현재 모델로 1게임 실행
- 매 프레임의 GameState를 직렬화하여 Queue에 push
- 게임 결과도 Queue에 push

### Task 2: TrainingManager
`backend/rl/trainer.py` 작성.

```python
class TrainingManager:
    def __init__(self, model_dir: str = "models", replay_dir: str = "replays"):
        self.status: str = "stopped"  # "running" | "stopped" | "paused"
        self.metrics_queue: asyncio.Queue  # Backend WS가 소비
        self.frames_queue: asyncio.Queue   # Backend WS가 소비
        self.results_queue: asyncio.Queue  # Backend WS가 소비

    async def start(self, hyperparams: dict, bot_level: int) -> str:
        """새 실험 시작. experiment_id 반환. 백그라운드 스레드에서 훈련."""

    async def stop(self):
        """현재 훈련 그레이스풀 정지. 마지막 체크포인트 저장."""

    async def resume(self):
        """최근 체크포인트에서 훈련 재개."""

    def set_bot_level(self, level: int):
        """커리큘럼 러닝: 봇 난이도 변경."""
```

**핵심 구현 사항:**
- 훈련은 `threading.Thread`에서 실행 (SB3가 동기 API라서)
- `SubprocVecEnv`로 8개 병렬 환경
- stop 시그널은 `threading.Event` 사용
- 콜백의 Queue는 `asyncio.Queue` — 스레드에서 `loop.call_soon_threadsafe(queue.put_nowait, data)` 사용
- hyperparams 기본값은 docs/PLAN.md의 "2.2 Training Pipeline" 참조

### Task 3: Replay 저장
LiveFrameCallback에서 완료된 게임의 프레임 데이터를:
- msgpack으로 직렬화
- `replays/{game_id}.msgpack`로 저장
- game_id는 UUID4
- 최근 1000개 초과 시 가장 오래된 파일 삭제

### Task 4: Tests
**test_trainer.py:**
- TrainingManager.start()로 훈련 시작 후 1000 step 내 체크포인트 생성 확인
- TrainingManager.stop() 후 status가 "stopped"인지 확인
- MetricsCallback이 Queue에 메트릭을 push하는지 확인
- CheckpointCallback이 파일을 생성하는지 확인
- resume() 후 모델 상태가 유지되는지 확인

## Tech & Skills
- `/tdd` 스킬 사용
- `/python-review` 로 코드 품질 체크
- stable-baselines3, msgpack, asyncio 사용

## Dependencies
- **선행**: AI Engineer (game engine + rl env) 완료 필수
- **후행**: Backend Engineer가 TrainingManager를 WebSocket에 연결

## Acceptance Criteria
- [ ] `pytest backend/tests/test_trainer.py -v` 전체 통과
- [ ] 10k step 훈련 실행 시 reward가 증가 추세
- [ ] 체크포인트 파일이 models/ 에 정상 저장
- [ ] 리플레이 파일이 replays/ 에 정상 저장
- [ ] stop/resume가 정상 동작

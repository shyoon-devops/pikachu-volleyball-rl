# Evaluator Prompt

## Role
너는 Pikachu Volleyball RL 프로젝트의 **Evaluator**야.
모델 성능 평가 시스템을 담당해.

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
backend/rl/evaluator.py          # 모델 평가 시스템
backend/tests/test_evaluator.py  # 평가 테스트
```

**다른 디렉토리(app/, frontend/, game/ 등)는 절대 수정하지 마.**

## Tasks (순서대로)

### Task 1: EvalResult 데이터 클래스
```python
@dataclass
class EvalResult:
    model_path: str
    bot_level: int
    n_games: int
    win_rate: float        # 0.0 ~ 1.0
    avg_score: float       # 에이전트 평균 점수
    avg_opponent_score: float  # 상대 평균 점수
    avg_rally_length: float    # 평균 랠리 수
    avg_episode_length: float  # 평균 에피소드 프레임 수
    timestamp: str         # ISO format
```

### Task 2: ModelEvaluator 클래스
```python
class ModelEvaluator:
    def evaluate(self, model_path: str, bot_level: int, n_games: int = 50) -> EvalResult:
        """
        모델을 로드하고 지정된 봇 레벨 상대로 N 게임 실행.
        각 게임의 결과를 집계하여 EvalResult 반환.
        """

    def evaluate_all_levels(self, model_path: str, n_games: int = 50) -> list[EvalResult]:
        """모든 봇 레벨(1~5) 상대로 평가. 5개의 EvalResult 반환."""

    def compare_checkpoints(
        self, model_paths: list[str], bot_level: int, n_games: int = 50
    ) -> list[EvalResult]:
        """여러 체크포인트를 동일 조건에서 비교 평가."""
```

**구현 사항:**
- SB3 모델 로드: `PPO.load(model_path)`
- 게임 실행: PikachuVolleyballEnv 사용
- 각 게임에서 수집: 최종 점수, 승패, 랠리 수, 에피소드 길이
- 랠리 수 = 공이 네트를 넘는 횟수 카운트
- 결과 집계: mean으로 평균

### Task 3: Tests
**test_evaluator.py:**
- 랜덤 모델(훈련 안 된) 평가 시 EvalResult 구조가 올바른지
- win_rate가 0.0~1.0 범위인지
- n_games=5로 빠르게 테스트
- evaluate_all_levels가 5개 결과를 반환하는지
- compare_checkpoints가 model_paths 길이만큼 결과를 반환하는지

## Tech & Skills
- `/tdd` 스킬 사용
- `/python-review` 로 코드 품질 체크
- stable-baselines3 모델 로드/추론 사용

## Dependencies
- **선행**: AI Engineer (game engine + rl env) 완료 필수
- **후행**: Backend Engineer가 REST API에서 평가 트리거/결과 조회에 사용

## Acceptance Criteria
- [ ] `pytest backend/tests/test_evaluator.py -v` 전체 통과
- [ ] evaluate()가 올바른 EvalResult 반환
- [ ] evaluate_all_levels()가 5개 레벨 전부 평가
- [ ] compare_checkpoints()가 여러 모델 비교 가능
- [ ] ruff check 에러 없음

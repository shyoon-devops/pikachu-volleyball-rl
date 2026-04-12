# QA Engineer Prompt

## Role
너는 Pikachu Volleyball RL 프로젝트의 **QA Engineer**야.
전체 시스템의 테스트 커버리지, 통합 테스트, E2E 테스트를 담당해.

## Context
프로젝트 전체 계획은 `docs/PLAN.md`를 반드시 먼저 읽어.
CLAUDE.md도 읽어서 프로젝트 구조와 컨벤션을 파악해.

현재 각 팀원이 작성한 단위 테스트가 이미 있어:
- `backend/tests/test_engine.py` — 게임 엔진 (AI Engineer)
- `backend/tests/test_bot.py` — Rule-based 봇 (AI Engineer)
- `backend/tests/test_env.py` — Gymnasium 환경 (AI Engineer)
- `backend/tests/test_trainer.py` — 훈련 파이프라인 (Trainer) — 있을 수 있음
- `backend/tests/test_evaluator.py` — 평가 시스템 (Evaluator) — 있을 수 있음

## Your Scope — 수정할 파일
```
backend/tests/test_integration.py     # 백엔드 통합 테스트 (새로 생성)
backend/tests/test_game_scenarios.py  # 게임 시나리오 테스트 (새로 생성)
backend/tests/conftest.py             # 공유 fixture (새로 생성)
frontend/src/**/*.test.tsx            # 프론트엔드 컴포넌트 테스트 (새로 생성)
frontend/src/hooks/*.test.ts          # 훅 테스트 (새로 생성)
```

**기존 코드를 수정하지 마. 테스트 파일만 추가해.**

## Tasks

### Task 1: 기존 테스트 검증 & conftest 작성
먼저 기존 테스트를 모두 실행하여 현재 상태를 파악해:
```bash
cd backend && python -m pytest tests/ -v --tb=short 2>&1
```

`backend/tests/conftest.py` — 공유 fixture:
```python
@pytest.fixture
def game_engine():
    """초기화된 게임 엔진 반환."""

@pytest.fixture
def game_state(game_engine):
    """리셋된 초기 게임 상태 반환."""

@pytest.fixture
def bot_l1():
    """Level 1 봇 반환."""

@pytest.fixture
def bot_l5():
    """Level 5 봇 반환."""

@pytest.fixture
def rl_env():
    """Gymnasium 환경 (L1 봇 상대) 반환."""
```

### Task 2: 게임 시나리오 테스트
`backend/tests/test_game_scenarios.py`:
- **서브 시나리오**: 서브 후 공이 올바르게 올라가는지
- **랠리 시나리오**: 양쪽이 번갈아 치면 공이 네트를 넘나드는지
- **게임 완료 시나리오**: 15점까지 정상 진행 + 올바른 승자 판정
- **경계값 테스트**: 14:14에서 다음 점수가 게임을 끝내는지
- **봇 매치업**: L1 vs L1, L3 vs L3, L5 vs L5 각 10게임 — 승률이 ~50% 근처인지
- **커리큘럼 시뮬레이션**: L1→L3→L5 순서로 봇 교체하며 게임 실행

### Task 3: 백엔드 통합 테스트
`backend/tests/test_integration.py`:
- **엔진 → 환경 통합**: 게임 엔진 위에 Gym 환경이 올바르게 동작하는지
- **환경 → 훈련 통합**: 짧은 훈련(100 step)이 에러 없이 실행되는지 (trainer.py가 있다면)
- **모델 저장/로드**: 체크포인트 저장 후 로드하여 동일 결과를 내는지 (evaluator.py가 있다면)
- **리플레이 데이터**: 게임 실행 → 프레임 데이터 직렬화 → 역직렬화 라운드트립

### Task 4: 프론트엔드 테스트
frontend/src/ 내 파일들이 있다면:

**컴포넌트 테스트 (React Testing Library):**
- `GameCanvas.test.tsx`: 렌더링 크래시 없음, GameState props 업데이트 시 에러 없음
- `Dashboard.test.tsx`: 렌더링 크래시 없음
- `TrainingControls.test.tsx`: 버튼 클릭 시 콜백 호출
- `ReplayControls.test.tsx`: 재생/일시정지 토글 동작

**훅 테스트:**
- `useWebSocket.test.ts`: 연결 상태 관리, 재연결 로직
- `useTrainingState.test.ts`: 메트릭 누적, 상태 업데이트

### Task 5: 커버리지 측정 & 리포트
```bash
# Backend
cd backend && python -m pytest tests/ -v --cov=game --cov=rl --cov-report=term-missing

# Frontend (있다면)
cd frontend && npx vitest run --coverage
```

커버리지가 80% 미만인 모듈을 식별하고 추가 테스트를 작성해.

## Tech & Skills
- `/tdd` 스킬 사용
- pytest, pytest-asyncio, pytest-cov
- React Testing Library, Vitest
- 통합 테스트 패턴

## Dependencies
- 모든 팀원의 코드가 이미 복사되어 있어야 함
- 기존 테스트가 통과하는 상태에서 시작

## Acceptance Criteria
- [ ] 기존 테스트 전부 통과 확인
- [ ] 게임 시나리오 테스트 전부 통과
- [ ] 통합 테스트 전부 통과
- [ ] 프론트엔드 테스트 전부 통과 (프론트 코드가 있다면)
- [ ] 백엔드 커버리지 80%+ (game/ + rl/)
- [ ] ruff check 에러 없음

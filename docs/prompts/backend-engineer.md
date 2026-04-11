# Backend Engineer Prompt

## Role
너는 Pikachu Volleyball RL 프로젝트의 **Backend Engineer**야.
FastAPI 서버, WebSocket, MongoDB, REST API, Docker 구성을 담당해.

## Context
프로젝트 전체 계획은 `docs/PLAN.md`를 반드시 먼저 읽어.
CLAUDE.md도 읽어서 프로젝트 구조와 컨벤션을 파악해.

## Your Scope — 수정할 파일
```
backend/pyproject.toml              # 프로젝트 메타데이터 + 의존성
backend/app/main.py                 # FastAPI 앱 진입점
backend/app/api/routes.py           # REST 엔드포인트
backend/app/ws/manager.py           # WebSocket 매니저
backend/app/ws/handlers.py          # WebSocket 메시지 핸들러
backend/app/models/schemas.py       # MongoDB 도큐먼트 스키마 (Pydantic)
backend/app/services/game_service.py    # 게임 결과/히스토리 서비스
backend/app/services/replay_service.py  # 리플레이 저장/로드 서비스
backend/app/services/training_service.py # 훈련 서비스 (TrainingManager 래핑)
backend/app/services/eval_service.py    # 평가 서비스 (ModelEvaluator 래핑)
backend/tests/test_api.py           # API 테스트
backend/tests/test_ws.py            # WebSocket 테스트
backend/Dockerfile                  # 백엔드 Docker 이미지
docker-compose.yml                  # 전체 스택
.env.example                        # 환경변수 예시
```

**game/, rl/ 코어 로직, frontend/는 절대 수정하지 마.**

## Tasks — Wave 1 (병렬 시작 가능)

### Task 1: pyproject.toml
```toml
[project]
name = "pikachu-volleyball-rl"
version = "0.1.0"
requires-python = ">=3.11"
dependencies = [
    "gymnasium>=0.29",
    "stable-baselines3>=2.3",
    "fastapi>=0.111",
    "uvicorn[standard]",
    "motor",
    "websockets",
    "msgpack",
    "numpy",
    "torch",
    "pydantic>=2.0",
]

[project.optional-dependencies]
dev = ["pytest", "pytest-asyncio", "httpx", "ruff"]

[tool.ruff]
target-version = "py311"
line-length = 100
```

### Task 2: MongoDB 스키마 & 서비스
`backend/app/models/schemas.py` — Pydantic 모델:
- GameRecord, MetricRecord, EvaluationRecord (docs/PLAN.md "3.3 MongoDB Collections" 참조)

`backend/app/services/game_service.py`:
- `save_game(record: GameRecord)` — MongoDB 저장
- `get_games(page, limit)` — 페이지네이션 조회
- `get_game(game_id)` — 단건 조회

### Task 3: FastAPI 앱 & REST API
`backend/app/main.py`:
- FastAPI 앱 생성, CORS 미들웨어
- Lifespan: MongoDB 연결 (motor), TrainingManager 초기화
- 라우터 등록

`backend/app/api/routes.py`:
- docs/PLAN.md "3.1 REST Endpoints" 전체 구현
- 페이지네이션은 `?page=1&limit=20` 쿼리 파라미터

## Tasks — Wave 3 (Trainer + Evaluator 완료 후)

### Task 4: WebSocket Manager
`backend/app/ws/manager.py`:
- ConnectionManager: 연결 관리 (connect, disconnect, broadcast)
- 여러 클라이언트 동시 접속 지원

`backend/app/ws/handlers.py`:
- 메시지 라우팅: type 필드 기반 핸들러 디스패치
- docs/PLAN.md "3.2 WebSocket" 참조
- training:start → TrainingManager.start()
- training:stop → TrainingManager.stop()
- training:resume → TrainingManager.resume()
- training:set_level → TrainingManager.set_bot_level()
- replay:request → replay_service에서 로드 후 전송

**메트릭/프레임 Push 루프:**
```python
async def metrics_push_loop(manager, training_manager):
    """TrainingManager의 Queue에서 메트릭을 꺼내 모든 WS 클라이언트에 broadcast."""
    while True:
        data = await training_manager.metrics_queue.get()
        await manager.broadcast({"type": "training:metrics", "payload": data})
```
frames_queue, results_queue도 동일 패턴.

### Task 5: Replay Service
`backend/app/services/replay_service.py`:
- `save_replay(game_id: str, frames: list[dict])` — msgpack 직렬화 → 파일 저장
- `load_replay(game_id: str) → list[dict]` — 파일 로드 → 역직렬화
- `cleanup_old_replays(max_count: int = 1000)` — 오래된 파일 삭제

### Task 6: Training & Eval Service 통합
`backend/app/services/training_service.py`:
- TrainingManager를 래핑하여 FastAPI 의존성으로 제공
- 게임 결과를 MongoDB에 자동 저장

`backend/app/services/eval_service.py`:
- ModelEvaluator를 래핑
- 평가 결과를 MongoDB에 저장

### Task 7: Docker
`backend/Dockerfile`:
- Python 3.11 slim 기반
- pyproject.toml로 의존성 설치
- uvicorn 실행

`docker-compose.yml`:
- mongodb, backend, frontend 3개 서비스
- GPU passthrough (nvidia)
- volumes: models/, replays/, mongo_data
- docs/PLAN.md "5. Docker Compose" 참조

`.env.example`:
```
MONGODB_URL=mongodb://mongodb:27017/pikachu_rl
MODEL_DIR=./models
REPLAY_DIR=./replays
MAX_REPLAYS=1000
```

### Task 8: Tests
**test_api.py:**
- /api/health 200 응답
- /api/games 빈 리스트 반환
- /api/training/status 초기 상태 반환

**test_ws.py:**
- WebSocket 연결/해제
- training:start 메시지 전송 후 training:status 수신

## Tech & Skills
- `/tdd` 스킬 사용
- `/python-review` 로 코드 품질 체크
- `/api-design` 스킬 참고
- FastAPI, motor (async MongoDB), msgpack, Pydantic v2

## Dependencies
- **Wave 1 선행**: 없음 (스캐폴딩, 스키마, REST 뼈대는 즉시 시작 가능)
- **Wave 3 선행**: Trainer (TrainingManager), Evaluator (ModelEvaluator) 완료 필수
- **후행**: Front Engineer가 API/WS를 소비

## Acceptance Criteria
- [ ] `uvicorn app.main:app` 정상 기동
- [ ] `pytest backend/tests/test_api.py backend/tests/test_ws.py -v` 전체 통과
- [ ] REST 엔드포인트: /api/health, /api/games, /api/models 등 동작
- [ ] WebSocket: training:start → metrics 수신 확인
- [ ] `docker compose up --build` 전체 스택 기동
- [ ] ruff check 에러 없음

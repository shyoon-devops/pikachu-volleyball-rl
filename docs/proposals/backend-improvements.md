# Backend 개선 제안서

**작성자:** Backend Engineer
**날짜:** 2026-04-12
**대상:** Project Manager / Product Manager

---

## 제안 1: WebSocket Heartbeat 및 Backpressure 도입

**제목:** WebSocket 안정성 강화 (heartbeat + bounded queue)

**현황 문제:**
- 클라이언트가 끊겨도 서버가 감지 못함 (NAT/proxy 환경에서 stale 연결 누적)
- `asyncio.Queue()`에 maxsize 없음 → 브로드캐스트 지연 시 메모리 무한 증가
- `manager.broadcast()`가 dead connection을 사후에만 정리

**근거:**
- gorisanson/pikachu-volleyball-p2p-online (339 stars) — WebRTC 기반이지만 ping/pong heartbeat 구현
- FastAPI 공식 docs — WebSocket ping/pong keepalive 권장
- helpingstar/pika-zoo (11 stars) — PettingZoo 기반 멀티에이전트, 실시간 통신 패턴 참고

**작업 내용:**
1. 30초 간격 server-side ping, 10초 내 pong 없으면 연결 종료
2. metrics/frames/results queue에 `maxsize=1000` 설정
3. queue full 시 oldest 드롭 (backpressure)
4. 연결/해제 이벤트 로깅

**예상 작업량:** 0.5일
**우선순위:** HIGH — 장시간 훈련 시 WS 연결 불안정 → 프론트엔드 먹통

---

## 제안 2: API 응답 캐싱 및 무한 스캔 방지

**제목:** REST API 성능 개선 (캐싱 + 페이지네이션 통일)

**현황 문제:**
- `GET /api/games` — 매 요청마다 `count_documents({})` 별도 쿼리 (N+1 패턴)
- `GET /api/models` — 모든 .zip 파일에 `stat()` 호출, 페이지네이션 없음
- `GET /api/replays` — glob + stat 전체 스캔, 페이지네이션 없음
- `GET /api/evaluation/results` — hard-coded limit(100), offset 없음

**근거:**
- long2ice/fastapi-cache (1,854 stars) — decorator 기반 응답 캐싱, Redis/in-memory 지원
- MongoDB `$facet` — count + data를 single aggregation으로 처리

**작업 내용:**
1. game count에 TTL 5초 인메모리 캐시 적용 (별도 count 쿼리 제거)
2. `/models`, `/replays` 엔드포인트에 page/limit 파라미터 추가
3. `/evaluation/results` offset 파라미터 추가
4. models/replays 목록에 30초 TTL 캐시 (파일 변경 시 무효화)

**예상 작업량:** 0.5일
**우선순위:** MEDIUM — 데이터 적을 땐 문제 없지만, 모델/리플레이 1000개 넘으면 응답 느려짐

---

## 제안 3: 구조화 로깅 및 Health Check 고도화

**제목:** Observability 강화 (로깅 + 상세 health check)

**현황 문제:**
- 전체 백엔드에 logging 문 4개뿐 (handlers.py의 unknown message 경고만)
- 훈련 시작/중지, 게임 결과 저장, 평가 완료 등 핵심 이벤트 로그 없음
- health check가 `{"status": "ok"}`만 반환 — MongoDB 연결, 디스크, 훈련 스레드 상태 미확인
- `training_service.status()`가 `current_step: 0` 하드코딩

**근거:**
- structlog (Python 구조화 로깅) — JSON 포맷으로 Grafana/Loki 연동 용이
- 12 Factor App — health/readiness probe 분리

**작업 내용:**
1. structlog 또는 표준 logging에 JSON formatter 적용
2. 핵심 이벤트에 로그 추가: training lifecycle, game save, eval complete, WS connect/disconnect
3. `GET /api/health` 확장: MongoDB ping, disk usage, training thread alive, queue depth
4. `training_service.status()`에서 실제 step/episode 값 반환

**예상 작업량:** 0.5일
**우선순위:** MEDIUM — DevOps 모니터링(Grafana) 연동 전에 필요

---

## 제안 4: WebSocket 메시지 검증 및 Rate Limiting

**제목:** 입력 검증 강화 + API Rate Limiting

**현황 문제:**
- WS payload가 `payload.get("bot_level", 1)`로 직접 추출 — 타입/범위 검증 없음
- `POST /api/evaluation/run` — 수분 걸리는 작업인데 동시 요청 제한 없음
- `allow_origins=["*"]` — prod에서 CORS 무제한

**근거:**
- Pydantic v2 — WS 메시지에도 스키마 적용 가능
- slowapi (FastAPI rate limiter) — 엔드포인트별 rate limit
- OWASP API Security Top 10 — Unrestricted Resource Consumption (API4:2023)

**작업 내용:**
1. WS 메시지용 Pydantic 모델 정의 (TrainingStartMsg, SetLevelMsg 등)
2. `/evaluation/run`에 동시 실행 1개 제한 (asyncio.Semaphore)
3. CORS origin을 환경변수 설정으로 변경 (dev: *, prod: 특정 도메인)
4. 평가 경로에 Path.resolve() + 디렉토리 경계 검증

**예상 작업량:** 0.5일
**우선순위:** HIGH — 보안 + 안정성 직결

---

## 제안 5: 테스트 커버리지 확대

**제목:** 서비스 레이어 테스트 추가 (목표: 80%+)

**현황 문제:**
- 현재 9개 테스트, 약 85줄 — API 표면만 가볍게 검증
- GameService, ReplayService, EvalService 단위 테스트 없음
- RL 콜백 직렬화 테스트 없음
- 에러 경로 (race condition, queue overflow) 미검증

**근거:**
- 프로젝트 규칙: 80% 최소 커버리지
- Lyusungwon/apex_dqn_pytorch (51 stars) — 평가 로직 단위 테스트 패턴

**작업 내용:**
1. ReplayService 테스트: save/load/list/cleanup + race condition
2. GameService 테스트: mongomock 사용한 CRUD
3. `_serialize_state` / `_backfill_frame` 단위 테스트
4. WS 에러 경로 테스트 확대
5. pytest-cov로 커버리지 측정 CI 통합

**예상 작업량:** 1일
**우선순위:** MEDIUM — 안정적인 리팩토링의 전제 조건

---

## 제안 6: 평가 병렬화

**제목:** 모델 평가 병렬 실행으로 속도 개선

**현황 문제:**
- `evaluator.py`에서 n_games=50을 순차 실행 — 게임당 ~3초면 150초 소요
- 평가 중 API 블록은 없지만 (to_thread 사용), 결과까지 오래 대기

**근거:**
- helpingstar/pika-zoo — PettingZoo 기반 vectorized 환경
- SB3 SubprocVecEnv — 멀티프로세스 환경 래퍼

**작업 내용:**
1. `ThreadPoolExecutor`로 평가 게임 8-worker 병렬화
2. 또는 SubprocVecEnv 래퍼로 환경 벡터화
3. 예상 속도: 150초 → ~20초 (8x 병렬)

**예상 작업량:** 0.5일
**우선순위:** LOW — 기능적으로 동작하며 UX 영향 제한적

---

## 우선순위 요약

| # | 제안 | 우선순위 | 작업량 |
|---|------|---------|--------|
| 1 | WebSocket Heartbeat + Backpressure | HIGH | 0.5일 |
| 4 | 입력 검증 + Rate Limiting | HIGH | 0.5일 |
| 2 | API 캐싱 + 페이지네이션 통일 | MEDIUM | 0.5일 |
| 3 | 구조화 로깅 + Health Check | MEDIUM | 0.5일 |
| 5 | 테스트 커버리지 80%+ | MEDIUM | 1일 |
| 6 | 평가 병렬화 | LOW | 0.5일 |

**총 예상:** 3.5일 (HIGH 항목만: 1일)

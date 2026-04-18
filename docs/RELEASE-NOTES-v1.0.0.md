# Release Notes — v1.0.0

> **Version**: 1.0.0
> **Tag target**: `547ff663` on `github/dev` (closure: `github/v1.x-prep-pd`)
> **Cut date**: 2026-04-19
> **Base**: v0.2.5 (`cd1e6a39`)
> **Scope**: Faithful physics port + Evaluator E1-E10 + Unified Runs nav + Refactor sprint A1-A8
> **QA**: 19/19 PASS

## What's New (한국어)

v1.0.0 은 **첫 메이저 릴리스** 입니다. v0.2.5 이후 5주 동안 212 커밋이 쌓였고, 네 가지 큰 축으로 정리됩니다.

### 1. 원본 충실 포팅 (Faithful port)

1997 년 `gorisanson/pikachu-volleyball` 오리지널 게임의 물리 엔진과 렌더러를 **1:1 로 다시 포팅**했습니다. 지난 버전에서 발견된 미세한 거동 차이를 원본 소스와 맞춰 11,000 개 이상의 프레임 단위 parity assertion 을 통과하도록 고정했습니다.

- **엔진**: `physics.js` + `cloud_and_wave.js` 원본 상수·분기 그대로 포팅. `slowMotion`, `afterEndOfRound`, `beforeStartOfNextRound` state 3 종 추가
- **렌더러**: `view.js` main loop + sprite indexing 1:1. `game_end` 시 50-frame 확장 인트로 + 211-frame 복귀 플로우
- **오디오**: `PikaAudio` BGM loop + SFX trigger 타이밍 원본 재현
- **Bot L5** 포팅 회귀 해소 + aggression/net-bias 재튜닝
- **Parity audit 3종**: constants inventory / port-vs-original diff / state-machine cross-walk + frame-by-frame 회귀 테스트 ([`docs/audits/`](audits/))

### 2. 모델 평가 시스템 E1-E10

학습된 체크포인트를 실전에 투입하기 전 **정량 평가**할 수 있는 풀 스택 시스템입니다.

- **`/api/evaluations`** CRUD — MongoDB 백엔드 repository
- **`/api/evaluation/run`** 비동기 job — 긴 평가도 202 Accepted + `/status/{id}` polling
- **`/api/evaluations/timeseries`** — (model, bot_level) 별 training_step 축 포인트
- **Elo rating system** — L1=1200/L3=1500/L5=1800 앵커, k-factor=32
- **Dominance score** — 승률 60% + 득점 비율 40% 합성 (0.0~1.0)
- **Baseline comparator** — 기존 prod 모델 대비 per-level IMPROVED/REGRESSED/NEUTRAL 분류
- **Best model auto-selection** — verdict-tier 랭킹 (PASS > CONDITIONAL > FAIL > CRITICAL)
- **Batch evaluation CLI** — `python -m backend.rl.batch_evaluate models/ --levels 1 3 5` 병렬 실행
- **Markdown report generator** — 차트 + Elo leaderboard + threshold appendix 임베딩

### 3. 통합 Training Runs 화면 (`/runs`)

기존의 `/history` 와 `/evaluation` 분리 메뉴는 **하나의 훈련 런 뷰로 통합** 됩니다. 각 훈련 런을 타이틀로 묶고, 하위 탭으로 Overview / Games / Evaluation 을 전환합니다.

- **훈련 타이틀** — HyperparamForm 에서 자유롭게 입력. 모델 파일명에 슬러그 prefix 로 반영 (예: `my-run_ppo_1234567890.zip`)
- **Runs aggregation API** — `/api/training/runs` 가 10개 hyperparam 필드 포함 반환 (n_envs, lr, batch, gamma, clip_range, ent_coef, gae_lambda, n_epochs, n_steps, total_timesteps)
- **2 단계 드릴다운** — History 목록에서 run → games, Evaluation 목록에서 run → checkpoints
- **WS `training:game_end`** — 매 게임 종료 즉시 프론트 history 에 prepend (flicker-free)
- **Bulk delete** — 모델/체크포인트 체크박스 일괄 삭제, 활성 훈련 보호

### 4. 리팩터 스프린트 A1-A8 (v1.x-prep)

메이저 컷 직전 **코드 정리 스프린트**. 기능 추가 없이 유지보수성만 끌어올렸습니다.

- **A1 BE reward decomposition** — `_compute_reward` 를 8 helper 로 분해
- **A2 BE callbacks decomposition** — `LiveFrameCallback` 에서 3 helper 추출
- **A3 BE test coverage cleanup** — `test_physics.py` 로 대체된 중복 테스트 클래스 6 개 삭제
- **A4 BE + FE 죽은 코드 제거** — `TrainingRunDetail`, `seen_traversal_or_invalid` flag, 미사용 export/helper
- **A5 FE 공유 컴포넌트 추출** — `ScoreCell`, `TimestampText`, `EnvChip`
- **A6 FE WS discriminated union + zod** — 런타임 validation (parse fail 시 log-only)
- **A7 deps minor/patch 업그레이드** — pixi/react-router/typescript/eslint-plugin-react-hooks/globals. 메이저 후보는 `docs/DEPS-MAJOR-BUMP-CANDIDATES.md`
- **A8 docs ADR 체계화** — `NOTICE-*` 8 개 파일을 ADR-0001..0010 으로 정식화, `docs/INDEX.md` 카탈로그

### Migration guide

**훈련 런 타이틀 backfill** — v0.2.5 이전 생성된 MongoDB `games` / `evaluations` 문서에는 `title` 필드가 없습니다. v1.0.0 은 다음 두 경로로 자동 처리됩니다:

1. **읽기 경로**: `/api/evaluation/results` 가 응답 시 레거시 문서에 `title` 을 backfill 주입 (BE-T12, `9fc59022`)
2. **쓰기 경로**: 신규 훈련은 HyperparamForm 에서 타이틀 입력 → propagation (BE-T1..T6)

레거시 문서를 한 번에 업데이트하려면:

```bash
docker compose exec backend python -m backend.scripts.migrate_games_bot_level --mode=title-backfill
```

### Known issues (minor)

- `?tab=evaluation` ↔ `?tab=eval` URL 표기 불일치 — 내부 링크 생성은 `?tab=evaluation` 이지만 외부 공유 URL 이 `?tab=eval` 로 들어오는 경우 탭이 활성화되지 않을 수 있음. v1.0.1 hotfix candidate. 회피: 직접 탭을 클릭

## What's New (English)

v1.0.0 is our **first major release**. Since v0.2.5, 212 commits landed over 5 weeks and group into four tracks.

### 1. Faithful port of `gorisanson/pikachu-volleyball`

Re-ported the 1997 original's physics engine and renderer **1:1**. Every micro-divergence surfaced since launch is now pinned to the upstream source by an 11,000+ frame-level parity assertion suite.

- **Engine**: `physics.js` + `cloud_and_wave.js` verbatim constants & branches. `slowMotion`, `afterEndOfRound`, `beforeStartOfNextRound` added.
- **Renderer**: `view.js` main loop + sprite indexing 1:1. `game_end` 50-frame expanding intro + 211-frame return flow.
- **Audio**: `PikaAudio` BGM loop + SFX trigger timing reproduce the original.
- **Bot L5** port regression fixed; aggression/net-bias re-tuned.
- **Parity audits** under `docs/audits/` with frame-by-frame regression tests.

### 2. Model Evaluator E1-E10

Full-stack system to **quantify a checkpoint before promoting it**.

- **`/api/evaluations`** CRUD — MongoDB-backed repository
- **`/api/evaluation/run`** async job — 202 Accepted + `/status/{id}` polling for long runs
- **`/api/evaluations/timeseries`** — per (model, bot_level) points on training_step axis
- **Elo rating** — L1=1200/L3=1500/L5=1800 anchors, k-factor=32
- **Dominance score** — 60% win rate + 40% point share, [0.0, 1.0]
- **Baseline comparator** — per-level IMPROVED/REGRESSED/NEUTRAL vs prod baseline
- **Best-model auto-selection** — verdict-tier ranking (PASS > CONDITIONAL > FAIL > CRITICAL)
- **Batch evaluation CLI** — `python -m backend.rl.batch_evaluate models/ --levels 1 3 5` parallel
- **Markdown report generator** — charts + Elo leaderboard + threshold appendix

### 3. Unified Training Runs screen (`/runs`)

The old `/history` + `/evaluation` split is **merged into a single run view**. Each training run is keyed by title; Overview / Games / Evaluation are sub-tabs.

- **Training title** — free-form via HyperparamForm; propagates to model filename as slug prefix (e.g., `my-run_ppo_1234567890.zip`)
- **Runs aggregation API** — `/api/training/runs` now returns 10 hyperparam fields
- **2-level drill-down** — run → games in History; run → checkpoints in Evaluation
- **WS `training:game_end`** — prepend to FE history on each game save (flicker-free)
- **Bulk delete** — checkbox multi-select for models/checkpoints with active-run protection

### 4. Refactor sprint A1-A8 (v1.x-prep)

Code cleanup immediately before the major cut. Zero feature adds — only maintainability.

- **A1** BE `_compute_reward` decomposed into 8 helpers
- **A2** BE `LiveFrameCallback` 3 helper extraction
- **A3** BE redundant test classes deleted
- **A4** BE + FE dead code removal
- **A5** FE shared components — `ScoreCell`, `TimestampText`, `EnvChip`
- **A6** FE WS discriminated union + zod runtime validation (log-only on parse fail)
- **A7** deps minor/patch bumps (majors deferred)
- **A8** ADR migration + `docs/INDEX.md` catalogue

### Migration guide

**Run title backfill** — MongoDB `games` / `evaluations` documents created pre-v0.2.5 don't have a `title` field. v1.0.0 handles both paths automatically:

1. **Read path**: `/api/evaluation/results` backfills `title` on legacy docs (BE-T12, `9fc59022`)
2. **Write path**: new runs carry title from HyperparamForm (BE-T1..T6)

One-shot batch update:

```bash
docker compose exec backend python -m backend.scripts.migrate_games_bot_level --mode=title-backfill
```

### Known issues (minor)

- `?tab=evaluation` ↔ `?tab=eval` URL token mismatch. v1.0.1 hotfix candidate. Workaround: click the tab directly instead of relying on the deep-link query.

## Highlighted user flows

Design specs under [`docs/design/`](design/):

- [`DESIGN-RUNS-MERGED.md`](design/DESIGN-RUNS-MERGED.md) — the unified Training Runs screen
- [`DESIGN-BATCH-TABS.md`](design/DESIGN-BATCH-TABS.md) — multi-env live view with tabs
- [`DESIGN-EVAL-DRILLDOWN.md`](design/DESIGN-EVAL-DRILLDOWN.md) — two-level evaluation drill-down
- [`DESIGN-HISTORY-DRILLDOWN.md`](design/DESIGN-HISTORY-DRILLDOWN.md) — two-level history drill-down
- [`DESIGN-BULK-DELETE.md`](design/DESIGN-BULK-DELETE.md) — bulk checkbox delete UX
- [`DESIGN-HYPERPARAM-FORM.md`](design/DESIGN-HYPERPARAM-FORM.md) — extended PPO knob form
- [`DESIGN-TRAINING-TITLE.md`](design/DESIGN-TRAINING-TITLE.md) — title entry + propagation

## Rollback

- Rollback target: `v0.2.5` (`cd1e6a39`)
- Effect: all four v1.0.0 tracks disappear. DB `title` field stays but UI cannot read it
- Recommendation: **forward-only**. Any v1.0.x issue → hotfix rather than rollback

## References

- [CHANGELOG.md](../CHANGELOG.md#100---2026-04-19)
- [RETROSPECTIVE-v1.0.0.md](RETROSPECTIVE-v1.0.0.md)
- [ADR-0011](adr/0011-faithful-port-with-parity-test.md)
- [ADR-0012](adr/0012-refactor-sprint-area-by-area-with-parity-gates.md)
- [ADR-0013](adr/0013-unified-runs-navigation.md)
- [docs/VERSIONS.yml](VERSIONS.yml)
- [docs/INDEX.md](INDEX.md)

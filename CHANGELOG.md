# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/),
and this project adheres to [Semantic Versioning](https://semver.org/).

## [Unreleased]

v2.0.0 이후 scope. 차기 메이저 후보는 v3.x 주제 플레이스홀더 (retrospective 참조).

## [2.0.0] — 2026-04-22 (v2.x — self-play league + reward simplification + LSTM + SAC + Dreamer V3 / dev HEAD f0290ac9)

v1.0.0 이후 5 sprint (S1~S5) 누적 78 commit 의 메이저 릴리스. "알고리즘 선택지의 확장" 이 단일 축 — v1 의 PPO+MLP+shaped-reward 모노컬처를 self-play / learned-reward / LSTM / SAC / world-model 까지 선택 가능한 매트릭스로 개조. 기본 동작은 v1 과 동일 (default 필드 값 보존 — breaking 아님). QA 5/5 sprint regression GREEN.

### Added — S1 Self-play League (ADR-0014, merge `d9099ef4`)

- **OpponentProvider interface** — `backend/rl/opponent.py` 에 `RuleBot` / `LoadedPolicyBot` / `LeagueSampler` 3 impl. path-traversal hardening + Pydantic 기반 `LeagueCheckpoint` interop
- **League registry** — `backend/app/models/league.py` Pydantic 모델 + `LeagueRepository` (manifest.json + Mongo sync) + Elo helpers (K-anneal + anchor pinning L1=600/L3=900/L5=1200)
- **LeagueCallback** — match aggregation + `training:league_update` WS 브로드캐스트
- **LeagueAdmissionCallback** — +25 Elo gate above pool median 으로만 admission
- **REST endpoints** — `GET /api/league/standings`, `GET /api/league/checkpoints/{sha}`
- **`training:start` 확장** — `training_mode: rule_ladder | self_play` + `sampling: uniform | elo_biased | champion`
- **One-shot v1 migration** (`dafe7b4e`) — `scripts/seed_league_from_v1_models.py` 가 기존 `models/<exp>/*.zip` 을 `source="v1_legacy"` + `elo=1000.0` 로 시드
- **FE surface** — HyperparamForm Opponent section (세그먼트 + 샘플링 라디오 + 풀 사이즈 칩), `/runs/{title}` League 서브탭 (pool status + top-10 + matches + Elo chart), Recent Games 상대 컬럼 + 현재 run Elo 배지, 평가 패널 분리 (vs Rule / vs Top-N)
- **Updating overlay** — `training:update_start`/`training:update_end` WS 이벤트 (PPO gradient phase 동안 "updating…" 표시, heuristic fallback 유지)

### Added — S2 Reward simplification (ADR-0015, merge `ff3f78a9` + `c87ff11b`)

- **`reward_model` enum** (`3f5d5492`) — `shaped_v1` (기존, default) / `sparse_v1` (±1 terminal + ±0.1 per-point, 모든 shaping 제거) / `learned_shaped_v1` (terminal + IRL-learned shaping, Stage 2 Phase)
- **`training:start` 확장** (`f274f008`) — `reward_model` 선택 필드 BE→env→run doc 전 경로 스레딩
- **FE selector** (`e1983dc0`) — HyperparamForm reward_model 선택 + 런 리스트 칩 + 드릴다운 레이블

### Added — S3 LSTM Recurrent Policy (ADR-0016, merge `fcc59487` + `0a3a8eef` + `55176323`)

- **`policy_type` enum** (`d60c82ef`) — `mlp_v1` (기존, default) / `lstm_v1` (SB3-contrib RecurrentPPO)
- **LSTM 정책** (`eb735fc3`) — hidden_size=256, n_lstm_layers=1, feature_extractor 이후 LSTM head
- **`training:start` 확장** (`a08536b7`) — `policy_type` WS→manager→run doc 스레딩
- **FE selector** (`d60c82ef`) — HyperparamForm policy_type + 런 리스트 칩 + 드릴다운 레이블
- **Dependency** — `sb3-contrib>=2.3.0` (이미 존재, 업그레이드 아님; `RecurrentPPO` import 경로 활성화)

### Added — S4 SAC actor-critic (ADR-0017, merge `0f5581af` + `2ee16ccf` + `fefce3ef`)

- **`algorithm` enum** (`3cbfb09c`) — `ppo` (기존, default) / `sac`
- **SAC-Discrete** (`1426fa8d`) — discrete action space 를 위한 SAC 구현, twin critics + entropy coefficient auto-tuning
- **`training:start` 확장** (`75de6e82`) — `algorithm` WS→manager→run doc 스레딩
- **Matrix 허용** — `sac × mlp_v1` 조합까지 허용 (`sac × lstm_v1` 은 S4 스코프 아님)
- **FE selector** — 알고리즘 PPO/SAC 토글 + 드릴다운 레이블

### Added — S5 Dreamer V3 world-model (ADR-0018, merge `f48ccb16` + `d9831954` + `f0290ac9`)

- **`algorithm` 확장** (`313b8249`) — Literal 에 `dreamer_v3` 추가
- **Dreamer V3 학습기** (`9d45facc`) — world-model + actor + critic 3 네트워크, latent dynamics 학습
- **VecEnv shape mismatch fix** (`19c7e45d`) — `_collect_step` 에서 `n_envs>1` 시 배치 차원 오류 수정
- **WM loss smoke test** (`104575a5`) — seed-fixed + wire sanity 로 회귀 방지
- **FE selector** (`8b3e6326`) — 알고리즘 dreamer_v3 옵션 + 리스트 칩 + 풀 레이블
- **Dependency** — `dreamerv3-torch` vendor pin (upstream 미공개 릴리스 → 레포 내 vendor)

### Changed

- **`training:start` payload schema** — `algorithm` / `policy_type` / `reward_model` 3 필드 추가. 모두 default = v1 동작 보존 (`ppo` / `mlp_v1` / `shaped_v1`). 기존 클라이언트는 필드 omit 해도 정상 동작
- **Run 레코드 스키마** — `algorithm`, `policy_type`, `reward_model`, `training_mode`, `opponent_sampling` 5 필드 추가 (모두 Optional, legacy → None)
- **HyperparamForm UI** — S1~S5 selector 추가 (Opponent / reward_model / policy_type / algorithm). 기본값 선택 시 UI 동작 v1 과 동일

### Migrations

- **Run 레코드 백필** — 기존 v1 run 은 default 값으로 백필: `reward_model=shaped_v1` + `policy_type=mlp_v1` + `algorithm=ppo` + `training_mode=rule_ladder`. 실행:
  ```bash
  docker compose exec backend python -m backend.scripts.migrate_games_bot_level --mode=v1-to-v2-defaults
  ```
- **League 풀 시드** — 기존 v1 체크포인트를 League 에 admit: `source="v1_legacy"`, `elo=1000.0` 시드, anchor (L1=600, L3=900, L5=1200) 무조건 삽입. 실행:
  ```bash
  docker compose exec backend python -m backend.scripts.seed_league_from_v1_models
  ```
- **WS payload 호환** — 신규 필드 모두 optional. v1 FE 가 v2 BE 에 접속 시 정상 (추가 필드 무시), v2 FE 가 v1 BE 에 접속 시는 None 으로 렌더

### Dependencies

- **`sb3-contrib` ≥ 2.3.0** — S3 RecurrentPPO 의존 (pyproject.toml 기존 pin 유지, 실제 import 경로 활성화)
- **`dreamerv3-torch` vendor pin** — S5 world-model 의존성; upstream release 부재로 repo 내 `vendor/dreamerv3_torch/` 에 pin. PR 시 라이선스 NOTICE 동봉

### Known Limitations

- **Dreamer V3 Experimental** — v2.0.0 에서는 실험 단계. PPO+MLP+shaped 조합 대비 sample efficiency 는 확인되었으나 장기 안정성 미검증. GPU 권장 (CPU-only 환경에서는 현저히 느림)
- **LSTM × SAC 조합** — S4 스코프 밖. `policy_type=lstm_v1 × algorithm=sac` 선택 시 스키마 valid 하지만 runtime 실패
- **Dreamer checkpoint format** — SB3 `.zip` 과 호환 안 됨 (별도 `.pt` state_dict). League 는 `source="dreamer_v3"` 태그로 구분 렌더링, PPO ↔ Dreamer cross-load 불가

### Breaking Changes

None. 모든 신규 필드는 default 로 v1 동작을 보존. 기존 클라이언트/체크포인트/DB 문서는 그대로 작동.

### Rollback

- Target: `v1.0.0`. v2 feature 5 종 전부 재노출되지 않음. DB 에 새로 쌓인 `algorithm=sac` / `reward_model=sparse_v1` 등의 run 은 v1 FE 에서 None 으로 렌더됨 (해독 불능 아님). Dreamer 체크포인트만 v1 에서 load 불가 (filter out 필요)

### References

- [docs/release-notes/RELEASE-NOTES-v2.0.md](release-notes/RELEASE-NOTES-v2.0.md)
- [docs/migrations/v1-to-v2.md](migrations/v1-to-v2.md)
- [docs/retrospective/v2.x-retrospective.md](retrospective/v2.x-retrospective.md)
- ADRs [0014](adr/0014-self-play-league.md), [0015](adr/0015-reward-simplification.md), [0016](adr/0016-lstm-recurrent-policy.md), [0017](adr/0017-sac-continuous-actor-critic.md), [0018](adr/0018-dreamer-v3-world-model.md)

## [1.0.0] - 2026-04-19 (v1.x — faithful port + unified runs + refactor sprint / dev HEAD 547ff663)

v0.2.5 이후 5주 동안 누적된 212 commit 의 메이저 릴리스. 크게 4 축: (1) **faithful port** — `gorisanson/pikachu-volleyball` 1997 원본 physics.js + view.js + cloud_and_wave.js 를 1:1 포팅하여 engine parity 11k assertion 기반 픽스, (2) **Evaluator E1-E10** (PR #44) — Elo + baseline comparator + batch eval + history + timeseries + async report, (3) **unified /runs navigation** — 기존 `/history` + `/evaluation` 분리 → Training Runs 단일 화면 (Overview/Games/Evaluation sub-tabs), (4) **refactor sprint A1-A8** — BE reward/callbacks 분해, FE WS discriminated union + zod, shared component 추출, ADR 체계화. QA 19/19 PASS.

### Added — Game Engine Faithful Port (gorisanson/pikachu-volleyball 1997)

- **Physics.js 포팅** (`1fb72169`) — collision/gravity/bounce/net-hit 모든 상수·분기 1:1 매핑. 원본 pikavolley.js 의 game loop ordering 준수
- **view.js gameEnd 211-frame intro-return flow** (`d8dc8bb6`) — post-score freeze drop + 원본 winpose 시퀀스 복원
- **State machine 확장** (`d2427add`) — `slowMotion`, `afterEndOfRound`, `beforeStartOfNextRound` 3 state 추가해 pikavolley.js 와 1:1
- **`player.state` / `is_winner` / `game_ended` 와이어 emit** (`a49acffb`) — FE 가 state 기반 render 가능
- **25fps game loop alignment** (`12967dee`) — 원본 tick rate 정합
- **Sliding state cooldown** (`574442a4`) — 원본 physics.js 타이밍 재현
- **Winner/loser pose freeze** (`56a61fed`) — gameEnd 동안 양 player freeze (control source 무관)
- **Bot L5 regression fix after physics port** (`51d93c0c`) — 포팅 결과 L5 가 지나치게 약해진 회귀 수정
- **Golden test harness** (`8add0ea6`) — 10 scenario + determinism regression pinning
- **Original-parity audit 3종** (`68f18b85`, `d8f775f7`, `c3912faa`) — constants inventory / port-vs-original diff / state-machine cross-walk
- **Frame-by-frame parity test** (`bc2225ea`) — upstream physics.js 와 11k assertion 대조

### Added — FE Port (view.js main loop)

- **view.js 1:1 포팅** (`6f11838c`) — main loop + sprite indexing 원본 로직 재현
- **punch effect helper + trail reset on round edge** (`19612cb8`)
- **cloud_and_wave.js 1:1 port → cloudAndWave.ts** (`a144d164`)
- **game_end overlay with 50-frame expanding intro** (`2d47daca`)
- **PikaAudio + BGM loop + SFX trigger timing** (`ef0dce64`)
- **Playwright visual regression harness + 4 scenes** (`acf2bad7`)
- **slowmotion fade-ready + score-transition sequence** (`98233517`)
- **winpose render on game_ended** (`bdd7d19e`)
- **Diving sprite direction mirror** (`59d54f49`)
- **Replay metadata display** (`c7d6380e`) — level/final score/duration

### Added — BE diving + SFX wire protocol

- **`player.divingDirection` in state JSON** (`4a57ddb9`)
- **Per-frame SFX flags in state JSON** (`a5cd5df0`)
- **FE consume `diving_direction`** (`92c2011f`) — state 3/4 pose flip
- **FE wire 5 BE SFX flags** (`f09416d5`) — pi/pikachu SFX은 scope 에서 drop

### Added — Evaluator system E1-E10 (PR #44 `f9ffdd2d`)

- **`backend/rl/elo.py`** — EloRatingSystem (L1=1200/L3=1500/L5=1800 seed, k-factor=32, leaderboard + to_dict)
- **`backend/rl/baseline_comparator.py`** — prod-vs-candidate per-level deltas (IMPROVED/REGRESSED/NEUTRAL deadbands) + regression 교차검증
- **`backend/rl/batch_evaluate.py`** — ProcessPoolExecutor 병렬 실행 + BatchFailure 기록
- **`backend/rl/best_model_selector.py`** — verdict-tier ranking (PASS > CONDITIONAL > FAIL > CRITICAL) + regression_report veto
- **`backend/rl/comparison_chart.py`** — matplotlib 2×2 비교 그리드 + single-level progression
- **`backend/rl/report_generator.py`** — self-contained markdown 리포트 (verdict + charts + Elo leaderboard + threshold appendix)
- **`backend/app/api/evaluations.py`** — POST/GET `/evaluations`, GET `/evaluations/{id}`, GET `/evaluations/checkpoints`
- **`backend/app/services/evaluation_repository.py`** — Motor protocol-backed, `FakeCollection` test double
- **`backend/app/services/evaluation_timeseries.py`** — `/evaluations/timeseries` (model_path, bot_level) 별 training_step + checkpoint_label
- **`backend/app/services/elo_tracker.py`** — asyncio 백그라운드 tick, timestamp cursor restart dedup
- **`EvalResult.dominance_score`** — win_rate(60%) + point_share(40%) 합성 메트릭
- **Async job pattern for `/api/evaluation/run`** (`8ebbb9f3`) — 202 Accepted + `/status/{id}` polling
- **nginx proxy_read_timeout extend** (`56d7473b`) — long-running eval job 지원

### Added — Training Run Title + Management (BE-T1..T12)

- **Training title 제출 + 전파** (`a7351e57` T1 / `8313f575` UI) — HyperparamForm 에서 입력 → training:start 와 함께 전파
- **Model filename slug prefix** (`1ca89b91` T2) — title 유니크 slug 로 파일명 prefix 구성
- **Title backward-compat + MongoDB indexes** (`d08571af` T3)
- **Runs aggregation + games title filter** (`fc38f3d8` T4/T5)
- **`GameRecord.current_episode`** (`bab96f14` T6) — game end 시점 episode 저장
- **WS `training:game_end` emit** (`f506a887` T7) — 매 game 저장 직후 브로드캐스트
- **`GET /api/models` title filter + enriched fields** (`cd16ef63` T8)
- **`DELETE /api/models` bulk with active-run protection** (`dc80b557` T9 / `74c72b43` UI)
- **Hyperparams in runs aggregation** (`be7c5b96` T10) — run detail 에 10 hyperparam 필드 표시
- **`EvaluationRecord.title` + `.experiment_id`** (`59d72b33` T11)
- **Eval title backfill via `/api/evaluation/results`** (`9fc59022` T12)
- **Title auto-generate on empty** (design `646818dd`) — unique 보장

### Added — Unified /runs navigation

- **Unified Training Runs screen with Overview/Games/Evaluation sub-tabs** (`1c4779cd`) — 기존 `/history` + `/evaluation` 분리 종결
- **Hyperparams display on run detail** (`dd747d76`) — n_envs / lr / batch / gamma / clip_range / ent_coef / gae_lambda / n_epochs / n_steps / total_timesteps
- **2-level drill-down by training run** (`ef12e751` history, `385bfc1d` eval)
- **Null-safe render for stopped/empty training state** (`e59944ed`)
- **Live history from WS game_end** (`ed055f69`) — prepend + flicker-free keys (`e64604f5`)

### Added — Batch / Multi-env training

- **Per-env frame broadcast via `training:env_frame`** (`65dd7336`)
- **Per-env game save with `env_id` on GameRecord** (`99259d68`)
- **Batch tab bar + multi-env live view** (`97223658`)
- **`env_id` filter + column on History** (`a583f17f`)
- **Batch tab wrap layout + fixed-width score chip** (`32b95108`)
- **Batch tab up/down arrow keys across wrap rows** (`5bedffbd`)
- **Dynamic tab count from observed `n_envs`** (`d3413409`)

### Added — Extended Hyperparameters

- **Expand HyperparamForm** (`a62fbfe7`) — `total_timesteps`, `n_envs`, `n_epochs`, `ent_coef`, `gae_lambda` 추가
- **BE accepts extended hyperparams in `training:start`** (`cc4daaf3`)
- **Default `total_timesteps` raised to 2,000,000** (`88668eda`)

### Added — Metrics / Observability

- **`rally_count` per game in result payload** (`316d1eae`)
- **Recent games expanded columns** (`488e550c`) — env + episode + score detail
- **KST timestamp column + bot_level URL retention on Eval** (`7d052b0f`)

### Added — i18n

- **English UI translation** (`c46348fd`) — 전 UI 텍스트 영문화

### Changed — Refactor Sprint A1-A8 (v1.x-prep)

- **A1 BE reward decomposition** (9 commits, ending `7c4a8782`) — `_compute_reward` 를 8 helper 로 분해: `_game_outcome_reward`, `_approach_reward`, `_offensive_pressure_reward`, `_ready_position_reward`, `_net_crossing_reward`, `_score_reward`, `_touch_reward`, `_stall_penalty`
- **A2 BE callbacks decomposition** (3 commits) — `LiveFrameCallback` 에서 `_play_demo_game`, `_build_demo_result`, `_snapshot_manager_fields` helper 추출
- **A3 BE test coverage cleanup** (`f6f96778`, `bb75db60`) — test_physics.py 로 대체된 redundant test class 6 개 + coverage_gaps 중복 삭제
- **A4 BE + FE dead code cleanup** — `delete_models` 미사용 `seen_traversal_or_invalid` flag 제거 (`70ae1162`), FE `getGame`/`getMetricsHistory` 미사용 export 제거 (`5a0f0aca`), `__resetPikaAudioForTests` helper 제거 (`464f2fa6`), `TrainingRunDetail` component 제거 — `UnifiedRunDetail` 로 대체됨 (`31b30301`)
- **A5 FE shared components extract** (3 commits) — `ScoreCell` (`e495b917`), `TimestampText` (KST + em-dash fallback, `852598f1`), `EnvChip` (`cae1f3f4`) 를 Dashboard + ReplayList 에서 공용 분리
- **A6 FE WS discriminated union + zod validation** (`de006c0b`, `daf38ad9`) — training WS payload 에 discriminated union + zod runtime validation (parse failure 시 log-only, dispatch 는 차단하지 않음)
- **A7 deps minor/patch bumps** — `pixi.js` 8.17.1→8.18.1, `react-router-dom` 7.14.0→7.14.1, `typescript` 6.0.2→6.0.3, `typescript-eslint` 8.58.0→8.58.2, `eslint-plugin-react-hooks` 7.0.1→7.1.1, `globals` 17.4.0→17.5.0. 메이저 후보는 `docs/DEPS-MAJOR-BUMP-CANDIDATES.md` 로 defer
- **A8 docs ADR migration + INDEX catalogue** — `NOTICE-*` 8개 파일을 ADR-0001..0010 으로 마이그레이션 (`68200778`, `6d7ba464`, `9d0ed7ad`), `docs/INDEX.md` master catalogue 신설 (`0eafef73`)

### Changed — Internal organization

- **`docs/` reorganize** (`64860e2c`) — `design/` + `audits/` + `reports/` + `reports/notices/` 하위 분리 (git mv 로 history 보존)

### Fixed — User-reported bug rounds (R1-R9)

다음 항목은 배포 후 PM/유저 실사용에서 발견된 회귀/미커버 결함:

- **R1** (`2ab901cd`, `2eea3f84`) — Dashboard graph+text 리프레시 타이밍 sync, history 통합 리스트
- **R2** (`59d54f49`, `0a8cdf91`, `c063a6bb`, `c7d6380e`, `488e550c`) — trail 방향 다이빙 미러, 모든 timestamp KST 적용, 새 훈련 시작 시 차트 초기화, 리플레이 메타데이터, Recent Games 상세 열
- **R3** (`f900705b`, `5be3abe8`, `cd3b04d6`) — WS dynamic add 시 time 필드 undefined, timestamp uniform color, 하이드레이션 시 전체 메트릭 backfill
- **R4** (`2b2a8475`, `7d8abd43`) — recent games text-muted 제거, # rank column 제거로 time-cell adjacency illusion 해소
- **R5** (`6eb8dd9e`, `77f9271c`, `da304654`, `32b95108`, `a62fbfe7`, `5bedffbd`, `d3413409`, `5fd48120`) — 배치 탭 하이라이트 키보드 sync, episode/env column, eval active-job polling mount 복원, batch 탭 wrap, HyperparamForm 확장, arrow keys 다중행, 동적 탭 count, refresh 시 canvas/batch-tab guard
- **R6** (`5195b83d`, `00a4c664` 외) — env filter 동적 max, title T1-T6 전파
- **R7** (`e59944ed`, `dc80b557`, `385bfc1d`, `9f59739a`, `44d15440`, `33512833`, `a7307272`, `44557915`, `e77cb4e8`, `e64604f5`) — null-safe stopped/empty, bulk delete UI + active-run protection, eval drilldown, React hook order 위반 수정, drill-down 레이블, eval 체크포인트 poll, replay back context 보존, 탭이 현 run n_envs 매칭, 초기 status 에서 n_envs 하이드레이트, live history flicker-free keys + memo
- **R8** (`06273e04`, `1c4779cd`) — run detail 에 10 hyperparam 필드 매핑 null-only fallback, unified runs nav
- **R9** (`22e1fe55`, `c46348fd`) — run detail Evaluation tab 에 평가 결과 이력 노출, 전 UI 영문화

### Fixed — History / Chart / Game

- **History gameId join** (`36f016fc`) — games ↔ replays 를 Mongo `_id` 가 아니라 `gameId` 로 조인
- **History KST render** (`070343e2`) — Asia/Seoul 시간 표시
- **Chart x-axis anchor** (`8e59e3e9`) — unzoomed 기준 step 0 에 고정, refresh 와 무관
- **Graceful "?" for missing rally count** (`97a71f7f`) — BE 응답 누락 방어

### Fixed — Deploy / Ops / nginx

- **nginx Cache-Control no-cache on HTML** (`0b5e1c1c`) — FE bundle 캐싱 스트레스 해소
- **Rate limit relax for SPA navigation** (`f3bbf29d`, `6c1baaea`) — `/history`, `/runs` 등 정상 네비게이션이 429 맞던 문제. `X-Forwarded-For` honor 추가
- **nginx burst enlarge for SPA burst traffic** (`7ab12372`)

### Deprecated

- `/history` + `/evaluation` 분리 라우트 — `/runs` 로 통합 대체 (링크 redirect 유지 필요 여부는 FE 라우터 확인)
- `TrainingRunDetail` 컴포넌트 — `UnifiedRunDetail` 로 대체됨 (deleted)
- FE `getGame` / `getMetricsHistory` export — 사용처 없음 (deleted)
- `PikaAudio.__resetPikaAudioForTests` helper — 미사용 (deleted)

### Security

- **BE rate limit with X-Forwarded-For honor** (`6c1baaea`) — 정상 SPA 트래픽과 악성 버스트 구분 가능
- **FE WS runtime validation via zod** (`daf38ad9`) — 서버 payload shape 검증 (parse 실패 시 로그; dispatch 는 통과)
- **`DELETE /api/models` active-run protection** (`dc80b557`) — 현재 훈련 중인 모델은 삭제 불가 enforcement

### Known Issues (minor)

- `?tab=evaluation` ↔ `?tab=eval` URL inconsistency — QA flag. 내부 링크는 `?tab=evaluation`, 외부 공유 URL 은 `?tab=eval` 로 들어오는 경우 tab 이 활성화되지 않을 수 있음. v1.0.1 hotfix candidate
- Keyboard input handler 미구현 (spec `docs/adr/0002-fe-keyboard-input-contract.md` 에 기록, v1.x+ feature)

### Breaking Changes

- `/history` + `/evaluation` 라우트는 `/runs` 로 대체. 외부 북마크/문서는 `/runs?tab=...` 형태로 업데이트 필요
- `EvaluationRecord` 스키마에 `title` + `experiment_id` 추가 — 레거시 문서는 `/api/evaluation/results` 호출 시 `title` backfill (BE-T12). 직접 MongoDB 스캔 필요한 유저는 backfill 스크립트 실행 권장

### Rollback

- target `v0.2.5` (`cd1e6a39`). Faithful port + unified nav + evaluator E1-E10 이 전부 재노출되므로 실질적으로 v1.0.0 은 forward-only 릴리스로 간주. DB 롤백 시 `title` 필드 보존되지만 뷰는 사라짐

## [0.2.5] - 2026-04-12 (Phase 2 bug bundle — gameplay feel + metrics fidelity + match-end freeze / dev HEAD cd1e6a39)

v0.2.4 배포 이후 Phase 2 재작업 번들. 핵심 축 4개: (1) 게임 감각 개선(강타 링/다이브 잔상/freeze-frame), (2) 봇 난이도 상향(L5 역전 이슈 해소), (3) 메트릭 차트 충실도(/timeseries hydration + cap 확장 + 'N pts · M steps' 라벨), (4) P0 match-end freeze tick 핫픽스(`cd1e6a39`). 2 배포 창(22:03 FE + 22:05 BE → runtime `6f4a057f`, 그리고 match-end freeze merge → `cd1e6a39`) 를 하나의 태그 번들로 닫음.

### Fixed — Game engine / match end

- **15점 match-end freeze tick** (`e9f72459`, merge `cd1e6a39`): 매치 최종 점수가 올라간 직후 freeze 타이머가 tick 되지 않아 마지막 포인트 장면이 무한 고착 → 다음 매치 진행 불가. `_tick_post_score_freeze` 가 match-winning point 에도 불리도록 교정
- **Score hold grounded-ball frame** (`6ff911d9`): 득점 후 공이 지면에 닿은 프레임이 즉시 사라져 마지막 포인트 시각 피드백 상실. 득점 시 grounded frame 을 짧게 홀드하여 원본 가독성 회복
- **`last_frame` seed on training start** (`ca4cb608`): 훈련 시작 직후 `/api/training/current_frame` 이 `None` 을 반환해 404 가 나던 문제. 시작 지점에서 첫 frame 을 즉시 시드

### Fixed — Metrics chart / data fidelity

- **Chart hydration from `/timeseries` on mount** (`917c53cc`): 새로고침 시 차트가 비었던 문제. mount 에서 `/api/training/timeseries` 로 전체 포인트 seed → WS incremental 로 자연스러운 이어붙이기
- **`log_interval` 100 → 256 + `/timeseries` cap 1000 → 10000** (`856f689e`): 장기 실행 시 포인트 누락 방지 + 과샘플링 완화로 차트 해상도 실질 개선
- **Sampling cadence label "N pts · M steps"** (`2ed23c94`): 사용자가 차트가 보여주는 샘플 밀도를 한눈에 파악하도록 노출
- **WS dead-letter routing for missing `bot_level`/`experiment_id`** (`05ffd073`): 필드 누락 시 silent L1 fallback 이 L1 데이터로 보이게 만들던 문제. 이제 dead-letter 로 분리 → 데이터 품질 투명화

### Fixed — FE UX polish

- **Recent Games bot level fallback** (`b9819d5a`): 레거시 문서에 `bot_level` 가 없어 배지가 빈 "L" 로만 보이던 문제. 누락 시 fallback 렌더 — 빈 라벨 제거
- **Legacy games backfill migration** (`2e6bf373` + purge mode `116dd6ae`): 과거 문서에 `bot_level` / `experiment_id` 재주입 + 회복 불가 케이스에 대한 `--mode=purge-pre-fix` Option B 제공
- **Sky RGB stripe regression** (`ff24cc9a` / `f6e73e86`): PixiJS 필터/샘플링 이슈로 스카이 그라디언트가 RGB 줄무늬로 깨지던 현상. `NEAREST` 필터 + `antialias:false` + `roundPixels:true` 조합으로 픽셀 완전성 회복
- **Build: exclude `*.test.{ts,tsx}` from `tsconfig.app.json`** (`630b66c5`): 프로덕션 번들에 테스트 타입이 끌려오지 않도록 tsconfig 분리

### Added — Visual FX + Designer D11-D15

- **Dive sprite + motion-blur afterimage (D11)** (`a8cd7c59`): `is_diving` 상태에서 다이브 스프라이트 + 잔상 렌더 — 원본의 역동성 복구
- **Punch ring (D12) + power-hit trail overlay (D13)** (`34137663`): 지면/강타 타격점에 흰색 링, 강타 시 authoritative trail 렌더
- **Recent Games bot level badges (D14)** (`bad997f1`): L1-L5 난이도 램프를 배지 색으로 시각화
- **Score freeze-frame scoreboard flash (D15)** (`5f0b0cd7`): 득점 시 점수판이 freeze-frame 동안 플래시 — 관전 흐름 강조
- **`ball.punchEffect{X,Y,Radius}` types** (`743dc8ae`): bottom-hit ring 의 optional payload 타입 노출
- **`punch_effect_radius` emit on WS** (`982e3a80`): ground/power-hit 흰 링을 클라이언트 인퍼런스 없이 서버 권위로 전송

### Changed — Bot difficulty

- **L1-L5 난이도 상향 + aggression/net-bias 추가** (`d2436993`): 사용자 리포트 "L5 상대로 역전 가능" 이슈 해소. `aggression` + `net_bias` 로 네트 압박 + 반응 속도 두 축을 올림. L5 는 인간-사용자 승률 목표 <10% 로 재튜닝

### Changed — Deploy / ops

- **`scripts/deploy-frontend.sh` auto-advances `github/<env>` ref** (`6f96d7fd`): 배포 시 브랜치 head 가 자동으로 runtime SHA 로 정렬 — 지난 deploy window 에서 발견된 "branch lags runtime" 드리프트 재발 방지
- **`docker-compose` json-file log rotation + Round-2 disk cleanup** (`63bc1ca1`): dev/qa docker log 가 다시 GB 단위로 불어나던 현상 방지. 추가 ~disk 정리
- **Incident postmortem `20260412-dev-backend-stale` published** (`018a2be1`): v0.2.3 당시 promote.sh 백엔드 재기동 누락 인시던트 공식 기록화

### Deployment

- **3 환경(dev/qa/prod) 에 동일 bundle `index-CFGidFNF.js` 배포 완료** — 2 배포 창(22:03 FE + 22:05 BE) 으로 runtime 이 `6f4a057f` 에 도달. 이후 match-end freeze P0 hotfix (`e9f72459` merge `cd1e6a39`) 재배포 진행
- **env tag `v0.2.5-{dev,qa,prod}`** — DevOps 재배포 완료 후 최종 runtime SHA 에 부착
- **main advance** — prod → main 머지하여 `v0.2.5` tag main reachable 필수

### Not in v0.2.5 (deferred)

- Trainer PR #42 (TensorBoard + early stopping + reproducibility + grid search + curriculum learning) — 여전히 v0.2.6+
- Evaluator PR #44 (E1-E10 baseline / batch eval / history / timeseries / Elo) — 여전히 v0.2.6+
- Keyboard input handler 실구현 (spec 은 v0.2.4 `15c702ca` 에 기록됨)

### Rollback

- target `v0.2.4` (`dabd84a1`). 단 Phase 2 로 해소된 (i) match-end freeze, (ii) 차트 새로고침 복구, (iii) Recent Games 빈 "L", (iv) L5 승률 이상, (v) 스카이 RGB 줄무늬, (vi) 강타/다이브 시각 피드백 누락 — 이상 6 건이 재노출되므로 forward-fix 권장

## [0.2.4] - 2026-04-12 (post-v0.2.3 live-UI + engine + hyper-ball bundle / dev HEAD dabd84a1)

v0.2.3 을 3 환경(dev/qa/prod)에 배포한 직후 PM 의 실사용 테스트 + 추가 UX 리서치로 식별한 4 CRITICAL 수정 + 6 UX/정합성 개선의 번들. 모두 같은 deploy window 에서 dev 에 착지했고 DevOps 가 전 환경에 `index-DqBsWzf5` bundle 로 단일 배포.

### Fixed — Live-UI CRITICAL

- **FE REST hydration on mount + reconnect** (`bd6cea5a`): `useTrainingStateImpl` 이 `status={state:'stopped', ...}` 하드코딩으로 시작하고 `training:status` WS 메시지는 *state change* 시에만 브로드캐스트되어, 훈련 중 새로고침 시 Start 버튼만 보이고 Stop 이 사라져 개입 불가. mount 시 `GET /api/training/status` + 재연결 시 re-fetch 로 복원
- **FE optimistic Stop/Pause/level + REST hydration for graphs/games** (`06519a42`): 4 user-reported 버그 해소 (Stop 무반응, Pause 무반응, 새로고침 시 그래프/최근경기 패널 공백, Bot Level 버튼 선택 표시 없음). `wsSend` 를 optimistic local state 로 감싸고 mount 시 `/api/training/metrics/aggregate` + `/api/games?limit=20` + 게임 캔버스 REST seed 로 즉시 복원
- **BE stop/pause 실제 중단 + step/episode metrics broadcast** (`ee1b48ae`): Stop/Pause no-op + step/episode counter 0/0 고착 근본 해결. `TrainingManager` 에 `threading.Event` pair (stop + pause) 를 SB3 `CallbackList` 에 연결 → worker thread 실제 unwinding. `LiveFrameCallback` 이 `last_frame` 갱신해 새로고침 시 캔버스 즉시 repaint. `GET /api/training/status` 에 `bot_level`/`experiment_id`/`started_at` 추가. REST `/stop`/`/pause`/`/resume`/`/set_level` 이 `training:status` broadcast 수행 → WS control surface 와 완전 대칭

### Fixed — Engine/RL CRITICAL

- **Rally-timeout safety valve + RL truncation** (`913fca5f`): weak RL policy 무한 self-toss deadlock 방지. (C) 엔진 600 frames (10s @ 60fps) net 미통과 시 ball 미보유 side 에 point + fresh serve (`GameState.frames_since_net_crossing` + `round_ended_by_timeout`). (D) env 에피소드 truncation + `_RALLY_TIMEOUT_PENALTY` 로 PPO 에 loss-shaped terminal 신호. `test_engine.py::TestRallyTimeout` 5 케이스

### Fixed — Metrics chart consistency

- **REST metrics hydration 비활성화 (P0 stopgap)** (`eaec7ba8`): 훈련 메트릭 차트가 새로고침 전후 같은 X(step) 에서 다른 Y 값을 보이던 문제. 원인은 WS `training:metrics`(per-snapshot raw) + REST `/metrics/aggregate`(1-min bucket AVG) 의 값 도메인 불일치. FE 가 REST 하이드레이션을 끄고 WS 만을 신뢰 — 후속 `/timeseries` 엔드포인트 (`581e2a58`) 가 정답 대체

### Added — Hyper-ball (power hit) 시각 피드백

- **Engine `ball.is_power_hit` authoritative flag** (`3b4303df`): FE `ballSpeed > 25` heuristic 이 실제 power hit 다수 누락 + 잔류 속도에서 false positive. gorisanson/pikachu-volleyball 원본의 `ball.isPowerHit` (physics.js:725/727, view.js:513) 를 BallState + WS `training:frame` payload 로 포트
- **Types `BallState.isPowerHit` + `previousX/Y` + `previousPreviousX/Y`** (`d48d8a15`): FE 가 BE emitter 도착 전까지 undefined 로 기존 동작 유지하도록 Optional. 원본 t-1 / t-2 position 필드 정렬로 trail 렌더링 준비
- **Canvas authoritative power-hit trail + 3-slot history** (`33f6b868`): `computePowerHitTrail(ball, history)` 순수 함수 + 3-slot 히스토리 버퍼. 원본 sprite 위치를 그대로 재현. `powerHitTrail.test.ts` 단위 스위트 신설
- **FE keyboard-input spec 재조사** (`15c702ca`): "Enter 강타 unused" 사용자 피드백에 대한 원본 재조사 문서화. 현 FE 는 spectator-only 로 키보드 핸들러 없음 — 장래 인풋 구현 시 원본 바인딩 유지 (P1: D/G/R/V + Z power + F alt, P2: 대칭)

### Added — Dashboard `/timeseries` 엔드포인트

- **`GET /api/training/metrics/timeseries`** (`581e2a58`): FE-8 대시보드 하이드레이션 최종 계약 확정. `{step, value, timestamp}` 포인트 shape (timestamp 서버-스탬프 ISO-8601 UTC, persist 이후 non-null). default limit 100 → 1000 으로 확장 (새로고침 후 전체 trailing window 필요). `MetricsService.recent_points` 가 `timestamp` projection + naive datetime 을 UTC 로 정규화

### Changed — Bot level single source of truth (Option A)

- **WS `training:start.bot_level` Optional** (`d1728344`): 기존 기본값 1 로 인해 버튼으로 L5 선택 후 Start 시 L1 로 silent reset 되던 회귀 방지. Optional 시 dispatcher 가 `status.bot_level` 을 carry over
- **FE Option A: `status.botLevel` single source** (`f63d7aab`): Training Controls L1-L5 + Hyperparameters dropdown 의 두 store 충돌 제거. PM 결정 (2026-04-12) — status.botLevel 이 유일한 진실
- **Option A contract lock test** (`dabd84a1`): (1) dashboard `training:start` payload 가 bot_level 을 omit 하는지 + (2) L-buttons 이 stopped state 에서 clickable 유지되는지 불변 보호
- **Fetch mock init param TS lint 통과** (`ca6c8fe3`): `_init?: RequestInit` drift 에서 `@typescript-eslint/no-unused-vars` 회피 — rest-arg + 명시적 void

### Changed — Deploy infra (related)

- **`scripts/promote.sh` backend container restart 누락 수정** (`63e29b58`): v0.2.3 배포 시 frontend bundle 만 교체되고 backend 컨테이너가 옛 이미지로 유지되던 인시던트 대응. 자세한 내용은 `docs/incidents/20260412-dev-backend-stale.md`

### Deployment

- **3 환경(dev/qa/prod) 에 동일 bundle `index-DqBsWzf5` 배포 완료** (DevOps 보고: 2026-04-12, backend uptime 2분, force-recreate 완료). 컨테이너 신 코드 검증: `/timeseries` + `ball.is_power_hit` + rally-timeout 모두 포함
- **env tag `v0.2.4-{dev,qa,prod}`** — 동일 commit (dev HEAD `dabd84a1`) 에 부착 (3 환경이 byte-identical bundle)
- **prod 브랜치 forward** — `github/prod` 는 v0.1.0-era `41f4fdbb` 에 고착되어 있었음. v0.2.4 런타임 정합을 위해 dev HEAD 로 advance + main 머지

### Not in v0.2.4 (deferred)

- Trainer PR #42 (TensorBoard + early stopping + reproducibility + grid search + curriculum) — v0.2.5+
- Evaluator PR #44 (E1-E10 baseline / batch eval / history / timeseries / Elo) — v0.2.5+
- Keyboard input handler 실구현 (이번은 spec 문서화만)

### Rollback

- target `v0.2.3` (`737a088f`). 단 live-UI 3 CRITICAL + 엔진 rally-deadlock + 차트 불일치 + L-level silent reset 이 재노출 → forward-fix 권장

## [0.2.3] - 2026-04-12 (v0.2.2 QA blocker 3 hotfix / dev HEAD 77b871dd)

v0.2.2 QA 재검증(`d14c0c68`)에서 확인된 2 CRITICAL + 1 품질 이슈 수정. v0.2.2 전 환경 배포 직전 긴급 번들로 대체. 태그는 dev HEAD (`77b871dd`) 기준.

### Fixed — QA blockers (Sprint 2 post-promote)
- **BE-6 WS broadcast hotfix** (`91c7233d`): `fix(ws): restore training:status broadcast after parallel fan-out` — `fb1f5e64` 의 `asyncio.gather` parallel fan-out 에서 `training:status` 가 일부 구독자에 도달하지 않던 회귀 복구. PM 의 live UI 관찰(Start 버튼 활성화 유지 + status badge "stopped") 해소. `backend/tests/test_training_status_broadcast.py` 회귀 스위트 신설
- **Net-collision vx reversal guards** (`bf6397cc`): `test(physics): harden net-collision vx reversal guards` — `b0d0aaee` faithful physics port 이후 공이 네트에 닿아도 vx 가 뒤집히지 않던 회귀 수정 + `test_engine.py::TestBallNetCollision` 가드 강화
- **Bot variance knobs** (`6af36c0c`): `fix(bot): add stochastic variance knobs to break repetitive play patterns` — L1~L5 전 레벨에 `jump_jitter` + `angle_variance` + `hesitation_rate` + `trajectory_noise_scale` 도입. L5 도 distinct skill edge 유지하면서 deterministic 플레이 제거

### Deployment
- **v0.2.2 was tagged but never deployed** — v0.2.3 이 v0.2.2 를 그대로 대체. env tag `v0.2.3-{dev,qa,prod}` 로 배포 진행
- **qa backend** (`:8002`) 복구 필요(#38) — v0.2.3 첫 배포 타이밍에 qa 재기동 동시 수행
- **prod** 는 v0.1.0 → v0.2.3 jump (BE-3/SEC-1-3/BUG-1-7/BE-1-7/FE-1-9 + v0.2.2 Sprint 2 + v0.2.3 hotfix 모두 최초 반영)

### Not in v0.2.3 (deferred)
- Trainer PR #42: reward 재훈련 검증 + TensorBoard + early stopping + reproducibility + grid search + curriculum learning
- Evaluator PR #44: E1-E10 baseline comparator, batch eval, history persistence, timeseries endpoint, Elo tracker

### Rollback
- target `v0.2.1` (`482df2d1`). prod 는 현재 v0.1.0-era 이므로 사실상 forward-only deploy

## [0.2.2] - 2026-04-12 (Sprint 2 complete / dev HEAD 121cb478)

Sprint 2 배치 — Backend 성능 3종(BE-5/6/7) + Frontend UX 4종(FE-6/7/8/9) + AI Engineer 의 gorisanson/pikachu-volleyball 원본 충실 포팅 + Designer D6-D10 + QA Sprint 1 회귀/재검증 스위트 + DevOps 모니터링 스택. 태그는 dev HEAD (`121cb478`) 기준. Trainer PR #42 는 v0.2.2 에 포함되지 않음 — v0.2.3 hotfix 로 이월.

### Added — Backend (performance & features)
- **BE-5 hot-path MongoDB indexes** (`ee7a6c0b`): startup 시 games / metrics / evaluations 컬렉션 인덱스 선언으로 조회 지연 저감
- **BE-6 parallel WS broadcast with serialize-once fan-out** (`fb1f5e64`): 메시지 1회 직렬화 후 클라이언트별 병렬 송출 — 다중 클라이언트 시 브로드캐스트 경로 최적화
- **BE-7 training metric persistence + time-bucket aggregation** (`027bc08e`): 학습 메트릭 MongoDB 영속화 + 시간-버킷 집계 조회

### Added — Frontend (UX)
- **FE-6 global ConnectionIndicator pill** (`265e3c30`): 앱 헤더에 WebSocket 연결 상태 전역 표시
- **FE-7 replay keyboard scrubbing** (`f10b6c25`): ←/→ 1프레임 단위, ↓/↑ 10프레임 단위 스텝 이동
- **FE-8 training Pause / Resume toggle** (`360fa1dd`): Stop 과 별개로 일시중지/재개 컨트롤 추가
- **FE-9 CheckpointList picker for model evaluation** (`668df41d`): Evaluation 패널에서 모델 체크포인트 리치 선택 UI

### Added — Design (D6-D10 polish)
- **D6-D10 training progress, chart tooltip, fullscreen, toast, error/skeleton** (`3cdef948`)
- **Chart semantics, arcade frame, button micro-anim, row states, mobile tab bar** (`9edec27b`)
- **Dev audit artifacts** (`08b86ead`)

### Changed — RL / Game engine (AI Engineer — 원본 충실도 복원)
- **Faithful port of game engine to gorisanson/pikachu-volleyball original** (`b0d0aaee`): 오리지널(1997) 물리 거동 충실 포팅
- **Gate ball-player collision with isCollisionWithBallHappened flag** (`e5d765a0`): 충돌 중복 방지 플래그 게이팅
- **Rebalance reward weights to prioritize winning over shaping** (`0f32235e`): 승리 기반 보상 가중치 상향, shaping 비중 하향
- **Remove duplicate Start button, unify training controls** (`9f050c87`)

### Added — Tests (QA & AI Engineer)
- **Physics regression suite pinning behavior to original source** (`ab0151cd`)
- **Rework tests affected by faithful physics port** (`47aa4ced`)
- **E2E, WS resilience, load, rate-limit, coverage report** (`a12c3117`)
- **16-bug regression suite + prod-20260412 QA report** (`720458bb`)
- **Sprint 1 fix verification suite — SEC-1/2/3, BUG-3/5, BE-1** (`d5aa9fce`)
- **Post-promotion QA re-verification script** (`057dc651`) + 확장 (`c3e2cc08`)
- **QA env verification report + dev-vs-QA diff** (`82f86187`, `c24764e5`)
- **Re-verify QA after redeploy — 6 fail / 35 pass, Sprint 1 fixes 랜딩 확인** (`d309a574`)
- **/api/health exemption probe + /live /ready split finding** (`243c6a14`)

### Fixed
- **Middleware: exempt metrics + health probes from rate limiter** (`38e29bdd`): `/api/metrics`, `/api/health*` 제외 — Prometheus / k8s 프로브 안정화
- **Double score display + canvas responsive scaling** (`ede4e347`, #27)
- **test_ws_resilience — 3 test bugs masked as server regressions** (`0a79eb44`): 테스트 버그 수정, BE-1 해당 없음으로 판정
- **/api/health rate-limit exemption test + 3 flakes** (`26e038b6`)

### Infrastructure (DevOps)
- **Loki + Promtail centralized log aggregation** (`f863c11e`)
- **CPU/GPU/memory/disk resources dashboard** (`fc44b70f`)
- **Backup/restore verification harness** (`da6a93c6`) — DO-3 선행 작업
- **promote.sh fix + smoke-test.sh for qa/prod verification** (`dac05c89`)
- **Prevent orphan containers + document two-server arch** (`79599088`)

### Docs
- **Retract BE-1 finding — root cause was my test bugs not server** (`2a11a0f4`)
- **Full-suite stability note + clarify isolated vs bundled pass rates** (`d981d05d`)
- **Notify Trainer of reward rebalance + rerun-training request** (`1a40c8fa`)

### Deployment
- **dev tag** — `121cb478` (v0.2.2 tag target)
- **qa/prod 배포** — DevOps 수행 대기 (env tag `v0.2.2-qa`, `v0.2.2-prod` 부착 필수)
- **prod → main 머지** — prod 승격 후 필수

### Not in v0.2.2 (deferred to v0.2.3)
- **Trainer PR #42**: reward rebalance 검증 + TensorBoard integration + early stopping + reproducibility + grid search + curriculum learning — dev 미머지

### Known gaps
- FE 중복 Start 버튼 제거(`9f050c87`) 이후 전 환경 재배포 필요 — 현재 qa/prod frontend 는 v0.2.1 pre-fix 번들 서빙 중
- qa backend 가시성 복구 (#38) 선행 후 v0.2.2 QA 검증 진행

## [0.2.1] - 2026-04-12 (QA 재배포 완료, prod 대기 / dev HEAD 482df2d1)

Sprint 1 완료분 + 팀 자발적 품질 보강 + BE-2/BE-3 조기 착수분. 최초 QA 승격 (`15f4a11`) 이후 BE-3 재작업과 BE-2 가 dev 에 추가 병합되어 QA 재승격(`1baa3e3b`) 수행. 태그는 dev HEAD (`482df2d1`) 기준.

### Added (post-first-QA-promotion batch — sprint-2 items advanced into v0.2.1)
- **BE-3 JSON structured logging + /health/live|ready split** (`f6e71e80`): JSON 구조화 로깅 + liveness/readiness 분리. 초기 `13e103f` BE-3 에 추가된 확장분
- **BE-2 API TTL cache + unified pagination envelope** (`482df2d1`) — Sprint 2 (#31) 에서 조기 진입. TTL 기반 API 캐시 + 통일된 페이지네이션 응답 래퍼

### Deployment (updated)
- **dev → qa 재승격 완료** (2026-04-12): qa 브랜치 `1baa3e3b` — BE-2/BE-3 추가 병합분 포함

### Added (late batch — post-Sprint 1 finalization, 2026-04-12 03:xx)
- **Prometheus metrics endpoint** (`5da6af3`): `/api/metrics` Prometheus exposition format — Sprint 3 DO-1 선행 작업
- **Dashboard loading skeleton** (`2a52a3c`): 초기 로드 시 스켈레톤 UI로 인지 지연 개선
- **Friendly error boundary** (`4697e6c`): retry/reload/home 옵션을 가진 global React error boundary
- **MongoDB connection pool + transient-error retry** (`79c1e34`): `build_mongo_client()` 풀/타임아웃 설정, `with_mongo_retry()` 지수 백오프; GameService/EvalService 랩. 11개 테스트 추가. env 오버라이드 지원 (MONGO_MAX_POOL_SIZE 등)
- **Dark/Light theme toggle** (`a3a332a`): OS prefers-color-scheme 동기화 + 수동 토글
- **WS Pydantic validation layer 통합** (`c90794c`): `WsEnvelope` + `WS_MESSAGE_SCHEMAS` 레지스트리, `parse_ws_message()` 센터. unknown_type 구조화 에러, client-initiated ping→pong, stable error `code` 필드. 13 + 4 테스트 추가
- **Replay speed controls 재정비** (`5057b56`): 0.5x/1x/2x/4x 버튼 a11y + 키보드 접근 강화
- **API endpoint error handling + structured logging** (`13e103f`) — **BE-3 충족**: `endpoint_guard` 데코레이터, 글로벌 unhandled-exception handler, 전 엔드포인트 구조화 로깅. list_games 서비스 미초기화 → 503, get_replay linked-game 실패 tolerance. 7 신규 테스트
- **Dashboard metrics chart 실시간 스무딩** (`26d7c5a`) — **FE-2 smoothing 부분 충족**: Recharts built-in 250ms ease-out tween, `usePrefersReducedMotion` 훅, reduced-motion 미디어 쿼리 지원. MetricsChart.test.tsx 4 케이스

### Closed Issues (late batch)
- **#32 BE-3 Structured Logging + Health Check Depth** — 13e103f + BUG-2 fix로 해소

### Deployment
- **dev → qa 승격 완료** (2026-04-12): qa 브랜치 `15f4a11` (`chore: promote dev to qa`) — DevOps `scripts/promote.sh dev-to-qa` 실행 결과

### Still Pending for v0.2.1
- Docker QA 환경 (:8002/:3001/:27019) 배포 검증
- QA Engineer 전체 검증 리포트
- prod 승인 → 승격 → main 머지 + `v0.2.1` 태그

### Infrastructure (v0.2.1 scope, 이전 섹션에서 누락)
- **Two-server architecture split** (`75fb4292`): Backend + MongoDB → GPU 서버 (192.168.0.250), Frontend → yoonbian-2 (192.168.0.248) nginx 정적 서빙. docker-compose 에서 `frontend` 서비스 제거, `frontend/nginx-{dev,qa,prod}.conf` 3종 + `scripts/deploy-frontend.sh` 추가. CORS_ORIGINS 환경별 갱신
- **WSL2 docker.exe 감지** (`2acaabb5`): 모든 deploy 스크립트 (`deploy-{dev,qa,prod}.sh`)에 WSL2 환경 docker 바이너리 경로 감지 로직 추가
- **Training 스레드 예외 로깅** (`52d2ee39`): 훈련 스레드 예외를 silent swallow 하지 않고 구조화 로그로 기록 — 과거 silent-failure 패턴 제거
- **테스트 파일 unused import 정리** (`a2c23296`)

### Added
- **QA-2 CI/CD Test Pipeline** (#25): GitHub Actions 테스트 파이프라인 + 커버리지 게이트 (9d257c9, PR #29)
- **QA-4 Security Auto-Scan** (#26): CI 보안 자동 스캔 (bandit, npm audit) (9d257c9, PR #29)
- **FE-3 GameCanvas Responsive** (#22): ResizeObserver 기반 반응형 캔버스 스케일링 (2338102)
- **FE-5 A11y Improvements** (#24): ARIA 라벨, 색상 대비, reduced-motion 지원 (2338102)
- **Monitoring/Backup**: Prometheus 메트릭 계측, 백업 스크립트, 디스크 정리 작업 (72e1606)
- **Expanded RL spaces**: Observation 12→18, Action 6→12, anti-toss-loop 리워드 셰이핑 (5a5def9, f8ea612)
- **QA Regression Suite**: 16-bug 회귀 테스트 + Sprint 1 수정 검증 스위트 (720458b, d5aa9fc)

### Fixed
- **BUG-1 WebSocket Queue Bounded** (#13): 큐 상한 + drop-oldest 정책으로 OOM 방지 (5d143ae, merged 8565887)
- **BUG-2 Health Check** (#14): MongoDB/disk/thread 실측 기반 health 응답 (5d143ae)
- **BUG-4 Heartbeat Pong** (#16): 완전한 ping/pong 프로토콜 (서버 + 클라이언트) (5d143ae)
- **BUG-6 Game Result Save** (#18): retry + fallback 영속화로 데이터 손실 방지 (5d143ae)
- **BUG-7 FE WS Reconnection** (#19): 지수 백오프 재연결 구현 (2338102)
- **Design Review — Sprite Rendering** (#27): 스코어 중복 표시 + 캔버스 반응형 스케일링 수정 (ede4e34)
- Dockerfile 복구 및 빌드 실패 해결 (167bc07)

### Changed
- 미머지 브랜치 3개(devops/trainer/evaluator)를 dev로 일괄 통합 (#3) — PR #28, PR #29 포함

### Closed Issues
#13, #14, #16, #18, #19, #22, #24, #25, #26, #27, #3 (11건)

### Known Issues
- v0.2.1은 dev 코드 완료 상태. QA 환경 배포 후 검증 필요 (#6의 연장선).
- v0.2.0도 QA 태그만 되어 있고 prod 미승격 — v0.2.1과 함께 prod 승격 여부 PM 판단 필요.

## [0.2.0] - 2026-04-11 (QA 환경 배포 완료, prod 미배포)

QA 환경(`:8002`) 태그 완료 — prod 승격 대기 중. 전체 릴리스 노트: [docs/releases/v0.2.0-qa.md](docs/releases/v0.2.0-qa.md).

### Security (CRITICAL)
- **SEC-1**: `/api/evaluation/run` path traversal 차단 — `Path.resolve()` + `MODEL_DIR` 경계 검증 (#9, 10c9f1d)
- **SEC-2**: CORS 와일드카드 `*` 제거, 환경별 허용 오리진 화이트리스트 적용 (#10, 10c9f1d)
- **SEC-3**: REST API 엔드포인트 rate limiting 적용 (#11, 10c9f1d)

### Added
- **TR-4 Training Session Protection (BLOCKER)**: SIGTERM 복구, 세이프 큐 enqueue, 세션 중복 보호 (PR #28, 6e8ea3e / #12)
- **BE-1 WebSocket Heartbeat + Backpressure**: ping/pong 프로토콜, 큐 상한, 슬로우 컨슈머 감지 (#20, 3f8abb8)
- **BE-4 Input Validation + Rate Limiting**: 요청 스키마 검증 강화, 엔드포인트별 레이트 리밋 (#21, 3f8abb8)
- **FE-1 Replay Keyboard Shortcuts**: 재생/일시정지(Space), 시크(←/→), 배속(↑/↓) (#23, 830278b)
- **Evaluator**: 크로스 환경 평가 리포트 및 기준 문서화 (294f524)
- **Game Visuals**: 오리지널 피카추 배구 비주얼 포팅 — 구름, 파도, 공 이펙트, 스코어 스프라이트 (f25e50d)
- **Designer**: 하드코딩 값 토큰화, WCAG 명도 대비 위반 해소 (e19bc33)

### Fixed
- **BUG-3**: WebSocket 중복 start 크래시 가드, training_status 완전 데이터 반환 (#15, 5c30671)
- **BUG-5**: `/api/models`·`/api/replays` 필드 불일치 및 replay ID 라우팅 수정 (#17, 07c36bd)
- FE 페이로드 래핑 수정, `game_id` 추가, replay 응답 강화 (ac03e02)
- 누락된 반응형 브레이크포인트 4개 컴포넌트 복구 (18bfc32)
- Observation space shape 문서 정정 (19 → 18 features) + space spec 섹션 추가 (541f15a, 3823ecc)

### Changed
- **Designer**: CSS를 TSX에서 분리하여 .css 파일로 독립 관리
- **Frontend Engineer**: 모든 인라인 스타일을 className + CSS 파일로 변환
- **DevOps Engineer**: CI/CD 파이프라인 강화 — 커버리지 리포트, CD 워크플로우, 셀프호스트 러너

### Known Issues (prod 승격 전 해결 필요)
- 잔여 HIGH 버그 5건 (BUG-1/2/4/6/7) — Sprint 1 범위 내 처리 중
- prod 배포 후 main 브랜치 머지 + v0.2.0 태그 필요 (릴리스 워크플로우 업데이트: [docs/WORKFLOW.md](docs/WORKFLOW.md))

## [0.1.0] - 2026-04-11

Initial release — 전체 시스템 MVP 완성.

### Added

#### Game Engine (AI Engineer)
- 물리 기반 2D 피카추 배구 엔진 (`backend/game/engine.py`)
  - 충돌 감지 (공-플레이어, 공-네트, 공-경계)
  - 중력, 점프, 다이브, 파워 히트 메커닉
  - 득점 시스템 (15점 선승)
- 게임 상수 정의 (`backend/game/constants.py`)
- Rule-based Bot 5단계 난이도 (`backend/game/bot.py`)
  - L1(초보) ~ L5(완벽): reaction_delay, prediction_error, miss_probability 차등
- Gymnasium 호환 RL 환경 (`backend/rl/env.py`)
  - Observation: 12차원 정규화 벡터
  - Action: 6개 이산 행동 (noop, left, right, jump, left+jump, right+jump)
  - Reward shaping: 득점(+10), 실점(-10), 승리(+20), 패배(-20), 랠리(+0.5)

#### Training Pipeline (Trainer)
- PPO 훈련 매니저 (`backend/rl/trainer.py`)
  - 백그라운드 스레드 기반 훈련 (start/stop/resume)
  - 커리큘럼 러닝 — 봇 난이도 동적 조정
  - 8개 병렬 환경 (SubprocVecEnv)
  - 기본 하이퍼파라미터: lr=3e-4, n_steps=2048, batch=64, epochs=10
- 콜백 시스템 (`backend/rl/callbacks.py`)
  - MetricsCallback: 주기적 reward/loss/win_rate 수집
  - CheckpointCallback: 모델 체크포인트 자동 저장
  - LiveFrameCallback: 실시간 게임 프레임 캡처

#### Evaluation System (Evaluator)
- 모델 평가 시스템 (`backend/rl/evaluator.py`)
  - evaluate(): N게임 실행 후 win_rate, avg_score, avg_rally_length 산출
  - compare_checkpoints(): 여러 체크포인트 비교 평가

#### Backend API (Backend Engineer)
- FastAPI REST API (`backend/app/api/routes.py`)
  - GET /api/health, /api/training/status
  - GET /api/games (페이지네이션), /api/games/{id}
  - GET /api/replays/{game_id}, /api/models
  - POST /api/evaluation/run, GET /api/evaluation/results
- WebSocket 실시간 통신 (`backend/app/ws/`)
  - training:start/stop/resume, training:set_level
  - training:metrics, training:frame, game:result 스트리밍
- MongoDB 연동 (motor async driver)
  - Collections: games, metrics, evaluations
- 서비스 계층 (`backend/app/services/`)
  - TrainingService, EvalService, GameService, ReplayService
- Replay 저장 (msgpack 직렬화, 최근 1000개 유지)

#### Frontend (Frontend Engineer)
- React 19 + TypeScript + Vite 8 프로젝트 초기화
- Dashboard 페이지 (`/`)
  - TrainingControls: 훈련 시작/중지/재개, 봇 레벨 셀렉터
  - HyperparamForm: 하이퍼파라미터 입력 폼
  - MetricsChart: Recharts 기반 reward/win_rate/loss 차트
  - GameCanvas: PixiJS 기반 실시간 게임 렌더링 (30fps→60fps 보간)
- Replay 페이지 (`/replay/:id`)
  - ReplayPlayer: 리플레이 재생/일시정지/배속/시크
  - ReplayList: 리플레이 목록
- Evaluation 페이지 (`/evaluation`)
  - EvalPanel: 평가 트리거 + 결과 테이블
  - EvalChart: 모델 비교 차트
- Hooks: useWebSocket (자동 재연결), useTrainingState
- API 클라이언트 (`frontend/src/lib/api.ts`)

#### Design System (Designer)
- Arcade-themed dark mode 디자인 시스템
- CSS custom properties 기반 디자인 토큰 (`frontend/src/styles/tokens.css`)
- 글로벌 스타일 (`frontend/src/styles/global.css`)
- 컴포넌트별 CSS 파일 (Dashboard, Controls, Metrics, Replay, Evaluation)

#### DevOps (DevOps Engineer)
- Docker 컨테이너화
  - Backend Dockerfile (Python 3.11, multi-stage)
  - Frontend Dockerfile (Node build → Nginx)
  - .dockerignore
- Docker Compose 설정
  - `docker-compose.yml` — Production 환경 (:8000/:5173/:27017)
  - `docker-compose.dev.yml` — Development 환경 (:8001/:3000/:27018)
  - `docker-compose.qa.yml` — QA 환경 (:8002/:3001/:27019)
- CI/CD (`/.github/workflows/ci.yml`)
  - Python lint + test, Frontend lint + build
- 운영 스크립트
  - `scripts/deploy-{dev,qa,prod}.sh` — 환경별 배포
  - `scripts/promote.sh` — 환경 간 승격 (dev→qa→prod)
  - `scripts/release.sh` — 릴리스 (버전, 태그, 체인지로그)
  - `scripts/setup.sh` — 초기 설정
  - `scripts/cleanup-replays.sh` — 리플레이 정리
  - `scripts/status.sh` — 환경 상태 확인
- 환경별 .env 파일 (.env.dev, .env.qa, .env.prod, .env.example)
- .gitignore 설정

#### Test Suite (QA Engineer)
- Backend 테스트 (`backend/tests/`)
  - test_engine.py — 게임 엔진 유닛 테스트
  - test_bot.py — 봇 행동 테스트
  - test_env.py — RL 환경 테스트
  - test_trainer.py — 훈련 파이프라인 테스트
  - test_evaluator.py — 평가 시스템 테스트
  - test_api.py — REST API 엔드포인트 테스트
  - test_ws.py — WebSocket 핸들러 테스트
  - test_integration.py — 서비스 간 통합 테스트
  - test_game_scenarios.py — 게임 시나리오 테스트 (득점, 충돌, 랠리)
  - test_coverage_gaps.py — 커버리지 갭 보완 테스트
- Frontend 테스트
  - TrainingControls.test.tsx, GameOverlay.test.tsx
  - ReplayControls.test.tsx, useWebSocket.test.ts

[Unreleased]: https://github.com/shyoon-devops/pikachu-volleyball-rl/compare/v0.2.1...HEAD
[0.2.1]: https://github.com/shyoon-devops/pikachu-volleyball-rl/compare/v0.2.0...v0.2.1
[0.2.0]: https://github.com/shyoon-devops/pikachu-volleyball-rl/releases/tag/v0.2.0
[0.1.0]: https://github.com/shyoon-devops/pikachu-volleyball-rl/releases/tag/v0.1.0

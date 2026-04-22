# MineRL Diamond Challenge — Phase 0 기술 조사

**작성일:** 2026-04-23 · **작성자:** AI Engineer · **상태:** 초안

Pika v2.x 완료 후 차기 프로젝트 MineRL Diamond 착수 전 사전 조사.
코드 없음, 스펙/레퍼런스/리스크만.

## 1. MineRL 환경 개요

- **패키지**: PyPI `minerl`. 0.4.4 (Minecraft **1.16.5**, 2021 Diamond+BASALT 대회)
  와 1.0.x (OpenAI VPT / BASALT 2022 호환, Minecraft 최신) 두 라인 병존.
  우리 목표 Diamond 이므로 **0.4.4 라인 권장** (SOTA Dreamer V3 가 이 버전 기준).
- **요구**: Python 3.8-3.10, **JDK 8** 고정 (1.11/17 불가), Malmo 백엔드.
  Ubuntu 22.04 는 JDK 8 이 기본 저장소에 없어 PPA + `update-alternatives` 필요.
- **렌더링**: headless 는 `xvfb-run` 필수 — Malmo LWJGL 이 X display 를 요구.
  4070 Ti + CUDA 12 + xvfb 조합에서 샘플 처리량 ~30-50 env-step/s/core (SOTA 논문값).
- **설치 복잡도 상**: JDK 핀닝 + Malmo 빌드 + xvfb 결합으로 Docker 이미지 안정화
  가 Phase 1 의 상당 비중. 공식 Dockerfile 업스트림 2022 이후 stale.

## 2. 주요 task 정의

- **ObtainDiamond** 공식 스펙: **18,000 step cap** (약 15 분 in-game), 초기
  inventory 비어 있음, 랜덤 seed map, 허용 action = 전체 MineRL 액션 공간.
- **서브태스크 위계** (이전 버전에서 individual env 로 분리): `Treechop` →
  `ObtainWoodenPickaxe` → `ObtainStone` → `ObtainIronPickaxe` → `ObtainDiamond`.
  1.0 이후 Diamond 단일 env 로 통합되고 중간 보상은 inventory delta 로 직접 읽음.
- **Custom reward**: `minerl.env.EnvSpec` 서브클래스 오버라이드로 per-step reward
  callback 교체 가능. 우리는 S2 의 reward_model 패턴 재사용해서 enum
  (`sparse_v1` | `subtask_shaped_v1` | `irl_v1`) 노출 예정.

## 3. 현재 SOTA (2023~2026)

- **Dreamer V3** (Hafner et al. 2023, arxiv 2301.04104): **40 seed 중 24개가
  diamond 1회 이상 도달** (success rate 60%). 최초 성공 29.3M env-step,
  중앙값 **74M env-step**. **1 GPU × 9 일**. 인간 시연 없이, 희소 보상 only.
  이전 VPT 대비 compute 72배 절감 (720 GPU × 9일 → 1 GPU × 9일).
- **VPT** (OpenAI, Baker et al. 2022): YouTube 70k 시간 + BC pretrain + RL
  fine-tune. 100% diamond. 우리 스케일 불가.
- **MineDojo** (Fan et al. 2022): 대규모 지식베이스 + CLIP 보상. 일반화
  벤치마크. Diamond 특정 metric 아님.
- **Voyager** (Wang et al. 2023): GPT-4 기반 자동 커리큘럼. Diamond 포함 전
  tech tree 돌파 — 우리 4070 Ti 로컬 인퍼런스 현실적 X.
- **Leaderboard**: `https://minerl.io/` — 2022 이후 공식 대회 중단, 논문별
  자체 보고 체제. danijar/diamond_env (Dreamer V3 저자) 가 재현 레퍼런스.

## 4. Imitation learning 옵션

- **MineRL-v0.4 데모셋**: 약 **500 시간**의 인간 플레이 데이터 (act/obs 쌍,
  msgpack 포맷). 다운로드 ~60 GB.
- **BC pretrain + RL fine-tune**: Dreamer V3 는 **사용 안 함** (sparse-only
  학습이 논문 핵심 claim). Diamond 이전 baseline (MineRL 2019 우승 팀
  CDS, 2020 우승 팀 Forger) 는 전부 BC + RL 하이브리드.
- **4070 Ti BC 스케일**: 64×64 CNN + 500h 데이터 → 배치 64 로 ~1-2 일 내
  epoch 완주 가능. Dreamer V3 에 BC warm-start 추가 시 step-to-first-diamond
  이 74M → ~20M 로 줄어들 가능성 있음 (VPT 논문 extrapolation).

## 5. observation space

- **픽셀**: `pov` 필드, 기본 **64×64×3 RGB**. `ObservationSpec` 오버라이드로
  256×256 까지 확장 가능 (VRAM + GPU throughput 비례 증가).
- **Inventory/equipped**: `inventory` dict (item_id → count, ~30-40 슬롯),
  `equipped_items.mainhand` 벡터. **reward shaping 핵심 신호**.
- **기타 스칼라**: `compass.angle` (방위), `location_stats` (x/y/z, 일부
  env 에서만), `life_stats.life/food/saturation` — Diamond env 에서 전부 접근
  가능. Dreamer V3 는 inventory + 픽셀만 사용.
- **3D partial obs**: 1인칭 시야, pitch/yaw 로 회전. 등 뒤 / 상하 블록은
  **불가시** — 탐험이 어려운 근본 원인, LSTM/RSSM 메모리 필수.

## 6. action space

- **Dict action**: 이산 `forward/back/left/right/jump/sneak/sprint/attack/use`
  (9 플래그) + 이산 `craft/nearbyCraft/nearbySmelt/equip/place` (아이템 인덱스)
  + **연속** `camera` (pitch, yaw, 2차원 float).
- **총 차원**: 플래그 9 + 인벤토리 액션 5 (각 ~30 선택지) + camera 2D float.
  flatten 시 MultiDiscrete 약 150 차원 + Box(2).
- **Dreamer V3**: camera 2D 를 **11 개 bin × 2** 로 discrete 화 → 전체 이산화
  후 categorical actor head. 우리 S5 Dreamer discrete actor 재사용 가능.

## 7. CNN encoder 부담

- **Impala CNN** (표준 baseline): 64×64 RGB → ~1.5M params, ~50 GFLOP/batch.
  4-frame stack 시 약 2M.
- **Dreamer V3 encoder**: 6-layer conv stride-2 + 4 residual block, channels
  48→96→192. 약 **8M params** (World Model 전체 약 200M 의 4%).
- **4070 Ti 12 GB VRAM**: Dreamer V3 MineRL 논문 config (batch 16 × seq 64 ×
  64×64 픽셀) → peak ~6-8 GB. **여유 있음**. batch 32 까지 확장 가능.
  다만 replay buffer RAM (2M transition × 64×64×3 ≈ 25 GB) 이 병목 —
  디스크 캐시 shard 전략 필요.

## 8. reward shaping 옵션

- **sparse_v1**: diamond 최초 획득 +1, 그 외 0. Dreamer V3 baseline 과 동일.
- **subtask_shaped_v1**: inventory delta 로 6단계 (`log`/`planks`/`stick`/
  `wooden_pickaxe`/`stone`/`iron_pickaxe`/`diamond`) 각 +0.1~+1.0. 과거
  ObtainDiamondDense env 와 동형. 학습 빨라지지만 Dreamer 의 "sparse 를
  마스터한다" 홍보 포인트 희생.
- **IRL (learned)**: BC demo 로 potential Φ 학습 → Ng-Harada 방식. S2 의
  `learned_shaped_v1` 스캐폴드 구조 그대로 이식 가능.

## 9. 기존 오픈소스 레퍼런스

- **minerllabs/baselines** (공식, GitHub): 2021 대회용 PPO/Rainbow SB3 레시피.
  마지막 커밋 2022, maintenance 중단 — 참조용이지 의존 불가.
- **dreamerv3-torch** (NM512): MineRL **지원 있음** (examples/minerl 디렉토리).
  Diamond 공식 config 포함. 우리 S5 에서는 setup.py 부재로 pip 불가였지만
  MineRL 프로젝트는 별도 repo 이므로 **그대로 clone 해 사용 가능**.
- **danijar/diamond_env**: Dreamer V3 저자의 MineRL Diamond 재현 wrapper
  (gymnasium 호환). 표준 baseline 기준점으로 채택 권장.
- **커뮤니티**: `PWhiddy/PokemonRedExperiments` 류 직접 대응은 없음.
  MineRL BASALT BC 튜토리얼이 가장 잘 문서화됨.

## 10. Pika v2.x 자산 재사용 분석

- **재사용 가능**:
  - `policy_factory.py` — `algorithm` enum 에 `dreamer_v3_mine` 추가만.
  - `dreamer_runner.py` — RSSM + 3-phase loop 는 envp 불문. **obs encoder
    만 MLP → CNN 교체** (인코더를 팩토리 주입 형태로 리팩터 필요).
  - `loaded_policy_bot.py` — save/load 인터페이스 그대로.
  - `evaluator.py`/`eval_report.py` — winrate 대신 diamond rate 로 치환만.
  - WS training:update_start/_end, CheckpointCallback, MetricsCallback — 불변.
- **재작성 필요**:
  - `backend/game/` (Pika 엔진) → MineRL env wrapper 로 교체.
  - `frontend/` PixiJS 뷰 → Minecraft POV 영상 스트리밍 (MJPEG or frame push).
  - `replay_service` msgpack 포맷 → MineRL trajectory 포맷으로 확장.
- **CNN ↔ MLP 호환**: `dreamer_runner` 의 `_RSSM.embed` 를 **Protocol 로 추출**
  해서 Pika 는 MLP embed, MineRL 은 CNN embed 주입. 인코더 교체만으로
  v2.x 재사용율 약 60-70%.

## 권장 아키텍처

**신규 repo 권장** (`minerl-diamond`). 이유: (1) JDK/Malmo 시스템 의존이
Pika의 FastAPI/PixiJS 스택과 격리 필요 — CI 이미지 2배로 불어남; (2)
frontend 가 완전 재작성 → monorepo 통합 이익 미미; (3) v2.x 의
`backend/rl/` 핵심 모듈은 **별도 pip-installable `pika-rl` 서브패키지**로
추출하여 MineRL repo 가 의존하는 형태. Pika 모노레포 안의 서브트리 옵션
은 CI 복잡도 폭증으로 reject.

**Phase 1-3 분할**:
- **Phase 1 (2주)**: 환경 구축 — JDK 8 Docker 이미지, `minerl` 0.4.4 설치 검증,
  xvfb-run smoke, `danijar/diamond_env` wrapper 동작 확인. 출력: reproducible
  dev env + CI smoke test.
- **Phase 2 (4주)**: PPO 베이스라인 — `pika-rl` 추출 + MineRL CNN encoder.
  SB3 PPO 로 Treechop sub-task 도달. ObtainWoodenPickaxe 까지 커리큘럼.
- **Phase 3 (8주)**: Dreamer V3 튜닝 — danijar/diamond_env config 수입, 1 GPU
  × 9일 재현 시도. Subtask shaped reward 로 step-to-first-diamond 단축.
- **Phase 4 (옵션 4주)**: BC warm-start — 500h 데모로 actor pretrain, Dreamer
  로 fine-tune. step-to-diamond 20M 목표.

**Refs**: arxiv 2301.04104 (Dreamer V3); minerllabs/minerl 0.4.4; danijar/
diamond_env; Baker et al. 2022 (VPT); Fan et al. 2022 (MineDojo).

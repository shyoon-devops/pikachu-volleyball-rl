# pika-rl 서브패키지 추출 계획

**작성일:** 2026-04-23 · **Status:** proposal (POC 검증 완료) · **연관:**
docs/research/MINERL-PHASE0-RESEARCH.md §10

## 1. 목적

MineRL Diamond repo 가 pikachu-volleyball-rl 의 `backend/rl/` 코어
(policy_factory, dreamer_runner, loaded_policy_bot, callbacks,
evaluator) 를 `pika-rl` pip 서브패키지로 import 해서 Pika v2.x
재사용률 60-70% 확보. MineRL repo 는 env/FE 만 신규 구현.

## 2. POC 결과 (이 브랜치)

`pika-rl/setup.py` + `pika-rl/pika_rl/` 네임스페이스 6 모듈 (5 shim +
1 신규 `encoders`) 생성 완료. 로컬 검증:

```bash
pip install -e pika-rl/                                        # ✅
python -c "from pika_rl.policy_factory import policy_factory"  # ✅
```

**제약 사항 (POC 단계)**: shim 모듈이 `backend.rl.*` 를 import 하므로
**pikachu-volleyball-rl 체크아웃 안에서만** 동작. 외부 저장소 (MineRL
repo) 에서 `pip install git+...#subdirectory=pika-rl` 만으로는 inner
`backend.rl` import 가 실패. 실제 코드 이동은 Phase 3.

## 3. 3단계 추출 계획

**Phase 1 — shim 확정 + 하위호환 테스트 (PR 1-2개, 1주)**

- 이 POC 를 main 에 머지. 기존 `backend.rl.*` import 경로 무변경
  (Pika 내부는 기존 경로 계속 사용).
- `pika_rl.*` 임포트에 대한 smoke 테스트 1개 파일 (`test_pika_rl_shim.py`)
  추가. CI 가 shim 경로도 테스트하도록.
- 위험: 거의 없음 — shim 은 re-export 만.

**Phase 2 — env 의존 격리 + 인코더 Protocol 와이어인 (PR 3-5개, 2주)**

- `_RSSM.embed` inline 을 `ObsEncoder` Protocol 주입 방식으로 리팩터.
  Pika 는 `MlpObsEncoder` 로 기존 동작 유지 (parity test 앵커),
  MineRL 은 `ImpalaCnnObsEncoder` 로 주입.
- `ModelEvaluator.evaluate` 의 `PikachuVolleyballEnv` 하드코드 제거 —
  `env_factory: Callable[[], gym.Env]` 주입으로 변경.
- `LiveFrameCallback` / `EnvFrameCallback` / `EnvResultCallback` 이
  `env.env_method("get_frame_snapshot")` 등 Pika 전용 helper 호출 →
  `RenderProtocol` 추출해서 env 쪽에 책임 이동.
- 위험: parity test 망가지면 Pika 훈련 품질 회귀. 완화 = S5 의
  bench-B 와 동일 성공 게이트 (winrate_vs_L3) 재실행.

**Phase 3 — 실제 코드 이동 + 외부 설치 가능 (PR 2-3개, 1주)**

- shim 내용을 `pika_rl/*.py` 본체로 복사 (진짜 코드 이동). `backend.rl/*`
  는 역-shim 으로 전환 → `from pika_rl.policy_factory import *` 로
  기존 Pika import 경로 보존.
- `setup.py` 를 `pyproject.toml` PEP 621 로 승격, 버전 0.1.0.
- MineRL repo 에서 `pip install "pika-rl @
  git+https://github.com/shyoon-devops/pikachu-volleyball-rl.git@main#subdirectory=pika-rl"`
  검증.
- 위험: Pika 의 `backend.rl.*` 내부 cross-import 가 shim 우회로 일부
  깨질 수 있음 → Phase 2 리팩터가 미리 정리했으면 최소화.

**총 예상**: 3 phase × 7-10 PR, 4주. MineRL Phase 1 (env 구축) 과
병렬로 진행 가능.

## 4. 호환성 전략

- **Pika 기존 `backend.rl.*` import 유지**: 모든 phase 에서 필수.
  Phase 3 에서 `backend.rl.*` 가 `pika_rl.*` 의 역-shim 이 된 이후에도
  기존 import 경로는 작동. 연관 테스트 ~30개.
- **파일 이동 시점의 git history 보존**: `git mv` 사용, diff 는
  rename-detection 으로 블레임 유지.
- **MineRL repo 의존성 핀**: 처음에는 `@main` 으로 시작, 안정화 후
  특정 태그 (`pika-rl-v0.1.0`) 로 핀. MineRL 측 의존성 업그레이드
  시점은 MineRL 팀이 결정.

## 5. 인코더 Protocol 설계 (POC 포함)

`pika-rl/pika_rl/encoders.py` 신설 — `ObsEncoder` Protocol + 선언형
spec 두 개:

- `MlpEncoderSpec(obs_dim, hidden)` — Pika 의 18-float obs 용.
  기존 `_RSSM.embed` 의 2-layer SiLU MLP 와 동일 shape.
- `CnnEncoderSpec(obs_shape=(C,H,W), hidden, channels=(16,32,32))` —
  MineRL 64×64×3 RGB 용. Impala CNN 계열, ~2M 파라미터, 4070 Ti
  VRAM 여유 (Phase 0 조사 §7).

POC 단계에서는 spec 객체만 노출 — 실제 모듈 구현은 Phase 2 에서
RSSM 의 `embed` attribute 를 생성자 주입으로 바꿀 때 함께 작성. 이
분리 덕분에 MineRL repo 는 본인 CNN 을 자기 코드베이스에 두고 spec
만 pika-rl 쪽으로 흘려보내 사용 가능.

## 6. 위험 요소 + 완화

| 위험 | 확률 | 영향 | 완화 |
|---|---|---|---|
| Phase 2 리팩터로 Pika 훈련 회귀 | 중 | 고 (winrate 하락) | bench-B 동일 게이트 회귀, 통과 전 머지 금지 |
| `backend.rl.*` 역-shim (Phase 3) 순환 import | 중 | 중 | `pika_rl.*` 는 `backend.*` 를 **import 하지 않음** — 한 방향만 |
| MineRL repo 가 pika-rl 업스트림 브레이킹 변경 추종 | 중 | 중 | 태그 기반 핀 + 호환성 매트릭스 문서화 |
| SB3 / sb3-contrib 버전 드리프트 | 낮 | 중 | pika-rl setup.py 에서 하한만 고정, 상한은 열어둠 |
| Phase 3 에서 기존 Pika 테스트 import 경로 수정 누락 | 중 | 낮 (테스트만 깨짐) | Phase 3 PR 에 `backend.*` 및 `pika_rl.*` 양방향 smoke 포함 |

## 7. 바로 다음 단계

1. 이 POC 브랜치 (`pika-rl-extraction-poc`) 를 main 에 머지 — shim 만
   이라 Pika 동작 무영향.
2. Phase 1 PR: `backend/tests/test_pika_rl_shim.py` 추가 (3-5 케이스).
3. MineRL repo 쪽 설계 문서 작성 — `pika_rl` 임포트 가정한
   MineRL 트레이너 스켈레톤.
4. Phase 2 착수 시점은 MineRL Phase 1 (env 구축, 2주) 완료 후.

# pika-rl (POC)

Algorithm-agnostic RL runtime extracted from
[pikachu-volleyball-rl](https://github.com/shyoon-devops/pikachu-volleyball-rl)
for reuse across the MineRL Diamond project and other downstream
environments.

## Status

**Phase 0 POC — shim stage.** The modules under `pika_rl/` currently
re-export from `backend.rl.*` in the parent repo. This package is
**only usable from inside the pikachu-volleyball-rl checkout** until
Phase 3 moves the source. See
[`docs/proposals/PIKA-RL-EXTRACTION.md`](../docs/proposals/PIKA-RL-EXTRACTION.md)
for the full extraction plan.

## Install (POC, in-repo only)

```bash
# From the repo root:
pip install -e pika-rl/
python -c "from pika_rl.policy_factory import policy_factory; print('ok')"
```

## What's here

| Module | Source | Purpose |
|---|---|---|
| `pika_rl.policy_factory` | `backend.rl.policy_factory` | `(algorithm, policy_type) → PolicySpec` dispatch |
| `pika_rl.dreamer_runner` | `backend.rl.dreamer_runner` | Vendored Dreamer V3 skeleton |
| `pika_rl.loaded_policy_bot` | `backend.rl.loaded_policy_bot` | League-pool opponent wrapper |
| `pika_rl.callbacks` | `backend.rl.callbacks` | SB3 callback set (metrics, checkpoints, etc.) |
| `pika_rl.evaluator` | `backend.rl.evaluator` | `ModelEvaluator` + algorithm-dispatched load |
| `pika_rl.encoders` | **new** | `ObsEncoder` Protocol + MLP/CNN specs + `MineRLCNNEncoder` (NatureCNN, 64×64×3 → hidden) |

## Target (Phase 3)

```bash
# From any foreign checkout:
pip install "pika-rl @ git+https://github.com/shyoon-devops/pikachu-volleyball-rl.git@main#subdirectory=pika-rl"
python -c "from pika_rl.policy_factory import policy_factory; print('ok')"
```

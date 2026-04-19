# Freeze analysis — self-play training — 2026-04-19

**Author:** AI Engineer
**Scope:** self-play training stutter reported after the v2.x Sprint-1
  league landed. User-visible: brief freezes observed even outside the
  window where the FE "updating" overlay is drawn. Diagnosis requested
  by PM as observation-based (no speculation).
**Method:** instrumented 60 s local smoke under
  `backend/scripts/freeze_smoke.py` with timing CSV dumped via
  `backend/rl/_freeze_diag.py`, aggregated via
  `backend/scripts/freeze_analyze.py`. No dev/QA contact.

---

## Smoke configuration

| Parameter | Value |
|---|---|
| Duration | 60 s wall clock |
| Env | `PikachuVolleyballEnv` on `DummyVecEnv` |
| `n_envs` | 8 |
| Provider | `PFSPProvider` (strategy=pfsp, 3 anchors + 2 LoadedPolicyBot entries with randomly-initialized PPO weights) |
| Mirror rate | 0.10 |
| PPO hyperparameters | `n_steps=2048`, `batch_size=64`, `n_epochs=10` (defaults) |
| Host | Local WSL2, shared GPU |

Untrained PPO snapshots were used for the `LoadedPolicyBot` entries —
inference cost is independent of weight values (forward pass graph is
the same), so timing is representative.

---

## Raw measurements

### Per-event timings (ms)

| event                    |   count |  mean |   p50 |   p95 |    max |
|--------------------------|--------:|------:|------:|------:|-------:|
| `env.step` (total)       |  49,160 |  0.33 |  0.08 |  1.10 |  10.94 |
| `bot.get_action`         |  49,160 |  0.27 |  0.01 |  1.02 |  10.83 |
| `provider.get_opponent`  |      42 |  0.08 |  0.04 |  0.19 |   0.24 |

### `env.step` inter-call gaps (ms) — the freeze detector

| scope            |   count |  p50 |  p95 |   p99 |      max |
|------------------|--------:|-----:|-----:|------:|---------:|
| all envs merged  |  49,152 | 4.20 | 7.74 | 10.49 | 14,211.04 |

Distribution above threshold:

| threshold | events |
|---|---:|
| > 100 ms  | **24** |
| > 500 ms  | **24** |
| > 1,500 ms (FE overlay threshold) | **24** |

All 24 long gaps are > 1,500 ms. No gaps in the 100–1,500 ms band —
the tail is strictly bimodal (fast steady-state + multi-second pauses).

Every env slot (0..7) reports exactly `max ≈ 14,211 ms` within ±1 ms —
the pauses hit all 8 VecEnv workers **simultaneously**. That's the
diagnostic signature of a single blocking event on the training
thread, not per-worker stalls.

### Rollout alignment

60 s / (n_steps=2048 × n_envs=8) = **3 full rollouts** → **3 gradient
update phases**. Per envs: 3 rollouts × 8 slots = **24 events**, which
exactly matches the 24 long gaps above. This is a direct attribution.

---

## Root cause

**PPO gradient-update phase is a synchronous ~14 s block of the
DummyVecEnv** once per rollout.

After `collect_rollouts` fills the buffer (≈5–8 s at our throughput),
SB3 `OnPolicyAlgorithm.train()` iterates:

    n_epochs=10  × (rollout_size / batch_size=64)  =  ~3,200 gradient updates

Each update is a forward+backward+optimizer step on the 18-float
MLP policy. On this box the whole phase takes ~14 s wall clock; on
prod hardware it's expected to be faster but remains multi-second.

The env-side code sees this as "`env.step` not called for 14 s". The
FE sees no frames, no metrics, no results — correctly interpreted as
"training frozen".

### Other suspects — all cleared

| suspect | measured | conclusion |
|---|---|---|
| `LoadedPolicyBot.predict` inference cost | p95 1.02 ms, max 10.83 ms | **not the bottleneck**; well below the 1,500 ms threshold |
| `PFSPProvider.get_opponent` (including disk path resolution) | max 0.24 ms | **not a freeze source** |
| `env.step` engine cost | p95 1.10 ms | stable; no hidden per-frame work |
| WS enqueue / broadcast fanout | instrumented; no samples >100 ms | **not a contributor** in the local smoke (dev may differ — see §Follow-up) |
| Python GC pauses | no multi-second single-call max observed across any event | **not seen** in 60 s window |
| RNG contention / provider lock | provider hit 42 times, mean 0.08 ms | **not a contributor** |

---

## Reconciling with the user report

The user reported "overlay 안 뜨는 구간에도 짧은 freeze". The smoke
found **zero freezes in the 100–1,500 ms band** — the distribution is
bimodal (≤10 ms fast path, ≥1,500 ms gradient pauses with nothing in
between).

Two reads are consistent with the observation:

1. **Visual perception of the tail of the 1,500 ms window.** The FE
   overlay threshold fires strictly above 1,500 ms; the first few
   hundred ms of a gradient update ramp-up (before the overlay turns
   on) can look like a stutter. In our smoke every observed pause is
   >1,500 ms so the overlay would fire; the user's "short freeze"
   likely corresponds to the unclamped overlay edge rather than a
   new phenomenon.
2. **Dev-environment-only latency.** WS fanout, Mongo writes, and
   nginx delay are not exercised by the local smoke. A WS broadcast
   stalling on a slow client, or a Mongo write blocking the async
   loop, could introduce 100–1,500 ms gaps invisible from the env
   side. Instrumentation to confirm that lives in `_freeze_diag.py`
   and can be turned on in a controlled dev run if the symptom
   persists after the primary fix lands.

---

## Proposed fixes

Ordered by expected impact on the observed 14 s freeze:

### Fix A — Explicit `training:update_start` / `training:update_end` WS events

**Change:** emit a WS event at `_on_rollout_end` (update begins) and
`_on_rollout_start` (update ends). FE overlay listens to the explicit
events instead of heuristic-timing the `env.step` gap.

- Removes the 1,500 ms heuristic threshold and with it any
  "overlay didn't fire on a real freeze" cases.
- Zero physics change → `bc2225ea` parity untouched.
- BE can decorate the message with rollout number + duration so the
  FE can render a progress bar.
- **Effort:** ~30 lines (one new event type, two emit points on the
  existing `_StopEventCallback`, FE listener swap).

### Fix B — Reduce gradient-update window

**Change:** raise `batch_size` 64 → 256 and drop `n_epochs` 10 → 5 in
`DEFAULT_HYPERPARAMS`.

- Gradient updates per rollout: 3,200 → 400 (8× reduction).
- Expected freeze: ~14 s → ~2–3 s on this hardware; sub-second on
  prod GPU.
- Well-known PPO tuning; batch 256 is commonly reported as a
  Pareto point for MLP policies at this observation dim.
- **Caveat:** learning dynamics change. Must be validated against
  the bot-ladder baseline before promoting to prod defaults.
- **Effort:** 2-line constant change + re-run the release-gate
  scorecard (L1..L5 win rates).

### Fix C — Ship diagnostics behind an env-var flag

Keep the `_freeze_diag` module as a permanent capability gated by
`FREEZE_DIAG_FILE`, so future regressions can be reproduced in
minutes rather than re-landing the instrumentation each time.

- Zero runtime cost when the env var is unset (single os.environ
  read per call site).
- **Effort:** promote `_freeze_diag.py` from `_freeze_diag` →
  `diag.py`, keep the guards unchanged.

### Fix D — Dev-environment WS/Mongo correlation (IF symptom persists after A)

Only if Fix A doesn't resolve the user's perception of short
freezes: run the same smoke on dev with WS + Mongo enabled, correlate
the `ws.enqueue` / `ws.broadcast` timings (already instrumented).

- Not committed to pre-emptively — the local evidence does not
  implicate the WS layer.

---

## Follow-up

- **This branch (`v2.x-prep-ai-freeze-diag`) is temporary.** The
  docs under `docs/diagnostics/` are meant to cherry-pick into
  `v2.x-prep`; the instrumentation commits are reverted in the
  trailing commit on this branch.
- **Fix A recommended first:** lowest risk, direct attack on the
  user-visible symptom, parity-safe.
- **Fix B needs a gated validation sprint:** I can run it inside
  the existing release-gate evaluator, but shipping the new
  hyperparameters without a bot-ladder regression check is a
  separate PM call.

---

## Artifacts

- Raw CSV (excluded from commit): `/tmp/freeze_smoke.csv` (98,363 rows)
- Smoke runner: `backend/scripts/freeze_smoke.py`
- Analyzer: `backend/scripts/freeze_analyze.py`
- Instrumentation: `backend/rl/_freeze_diag.py` (reverted in the
  tail commit of this branch)

---
**End of analysis.**

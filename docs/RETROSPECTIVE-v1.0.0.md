# Retrospective — v1.0.0

> **Cycle**: v0.2.5 (2026-04-12) → v1.0.0 (2026-04-19)
> **Calendar days**: 7
> **Commits**: 212
> **Net LOC**: ~negative after refactor sprint (A1-A4 dead code removal exceeded feature additions line-count)
> **QA**: 19/19 PASS at cut
> **Rollback events**: 1 (PR #42 trainer syntax error, reverted within the hour)

This retrospective covers the cycle from v0.2.5 deploy closure through the v1.0.0 major cut. 9 user-reported bug rounds + 1 refactor sprint + 4 feature tracks converged into a single release.

## What went well

### 1. Five-sprint iteration velocity

We averaged ~1.4 rounds per day through R1-R9. Each round was a tight loop: user reports surface → triage within minutes → fix pushed to dev within hours → redeployed (auto-advance via `deploy-frontend.sh` from `6f96d7fd`) → user re-verifies. No round sat idle for more than 24 hours. Credit goes to:

- **Dev branch is the only stable target.** Individual team-member branches (`yoon/backend-engineer`, `yoon/frontend-engineer`, etc.) merged into dev via `merge:` commits without expecting long-lived feature-branch ceremony. Worked because the scope was tightly bounded.
- **Deploy auto-advance** (`6f96d7fd` via A7 track) — `scripts/deploy-frontend.sh` pushes `github/<env>` ref after each successful deploy, so branch HEAD always reflects runtime. Two drift incidents earlier in v0.2.x (`cd1e6a39`-era "branch ref moved but image didn't rebuild") stopped recurring once this landed.
- **PM single-channel communication.** One person routed user bug reports, engineering dispatches, and DevOps rebuild directives. Round loop latency was PM throughput, not channel handoffs.

### 2. Parity test enabled safe refactoring

The refactor sprint A1-A8 landed 30+ commits on BE engine adjacent code (reward helpers, callbacks decomposition, test class drops) with **zero regressions** — QA 19/19 PASS at the v1.0 cut covers all of it. That's not normal for a refactor of this scope.

What made it safe: the physics/view port parity suite (ADR-0011) was the floor. Any refactor that silently changed engine output would have failed one of the 11k assertions in `test_physics.py`. We didn't need to rely on a reviewer catching a subtle regression — the test did.

Promote this approach for future refactors: [ADR-0012 — refactor sprint area-by-area with parity gates](adr/0012-refactor-sprint-area-by-area-with-parity-gates.md).

### 3. Designer-spec-first for UX changes

Every `/runs` navigation change shipped with a design doc that landed **before** the code. Example: [`DESIGN-RUNS-MERGED.md`](design/DESIGN-RUNS-MERGED.md) was written 2026-04-14 (early round 6); the FE implementation `1c4779cd` landed 2026-04-17 (round 8). Same pattern for BATCH-TABS, BULK-DELETE, EVAL-DRILLDOWN, HISTORY-DRILLDOWN, HYPERPARAM-FORM, TRAINING-TITLE.

Consequences: FE + BE could parallelize — BE builds the aggregation endpoint while FE builds the screen, both against the same written spec. Fewer integration surprises, fewer round-trip "wait, did you mean X?" messages.

### 4. ADR migration as v1.0 deliverable (A8)

Through v0.2.x the team had accumulated 8 `NOTICE-*` ad-hoc decision files (canvas rendering, bot ladder, health-check mandate, FX payload contract, WS game_result validation, etc.). They were valuable institutional knowledge but essentially invisible — no index, non-uniform format, mixed with release notes.

A8 migrated all 8 into `docs/adr/0001..0010` format + built `docs/INDEX.md` as a master catalogue. Future onboarding (self-play league work in v1.x) can now start from the ADR list instead of archaeological git-log diving.

## What we learned

### 1. Auto-approve 3-second cooldown is too aggressive for merge bursts

We hit rate-limit prompts several times during round 7-8 (batch tabs, bulk delete, drilldown landing simultaneously). The auto-approve cooldown held up legit parallel pushes because multiple team branches were ready at once.

Takeaway: either (a) raise the cooldown when PM explicitly flags "burst window open", or (b) auto-approve should be per-branch rather than global. No action taken this cycle; defer to ECC-Tools cost audit.

### 2. WSL network exposure hazard

The v0.2.x sessions and this cycle both saw incidents where `localhost:8001` on dev machine was reachable from inside containers AND from other network-connected devices. Two specific failure modes:

- **Test pollution** (documented in the test-isolation rule announcement, 2026-04-17): BE Engineer ran full pytest suite including E2E → real dev backend got training:start fired from their laptop → DB pollution
- **Designer/QA running against dev without realizing**: earlier rounds had QA reports against what turned out to be dev runtime, not local checkout. Required rerun after confirmation

Countermeasure: **test-isolation rule** (2026-04-17, ack'd by all hands). Plus `conftest.py` default base_url must be unreachable (e.g., `http://localhost:9999`). Enforcement is social for now; candidate for pre-commit hook to grep for `localhost:8001` in test modules as v1.0.1 follow-up.

### 3. Parallel FE/BE dev pollution at runtime

Related to the above: when FE and BE team members both had active local dev containers pointing at shared MongoDB (dev), state interleaving was confusing. FE seeing BE's test writes, BE seeing FE's exploratory button clicks. Not a data loss issue but a signal-to-noise one.

Takeaway: dev MongoDB is **shared infra, treat writes as public**. Any experimental write should use a dedicated `experiment_id` / `title` so it's filterable out of views. Backfill migration (BE-T3) helped retroactively.

### 4. PR #42 — auto-merge MERGEABLE ≠ semantic mergeability

A 3-way git auto-merge succeeded textually but produced a broken `trainer.py:455` with a bracket mismatch. The syntax was invalid Python, yet neither side's individual content had the bug — it emerged from the merge.

This is exactly the failure mode [ADR-0012](adr/0012-refactor-sprint-area-by-area-with-parity-gates.md) Gate 3 (each commit individually mergeable) is designed against. But PR #42 predated the ADR; ADR-0012 was codified partly because of this incident.

Follow-up: CI should run `python -m compileall backend/` on every merge commit. Add as a GitHub Action matrix step in v1.0.1.

### 5. Deploy-vs-tag-vs-branch confusion

Multiple times this cycle, DevOps reported "deployed" while runtime still ran the prior image because:
- `deploy-frontend.sh` auto-advanced `github/<env>` ref
- But the backend image wasn't force-recreated
- Tag `v0.X.Y-env` was attached to the new SHA
- Runtime reported old `/api/health` version

This caused the v0.2.5 "runtime still on CFGidFNF" incident noted in session summary. Fixed permanently by the v0.2.5 `promote.sh` backend force-recreate (`63e29b58`) and the auto-advance step rewrite.

Artifact for future: `docs/VERSIONS.yml` now requires `commit` + `image` + `deployed_at` trifecta per env. Missing any of these → deploy approval revoked on next cycle.

## What to improve for next major

### 1. Self-play league as v1.x marquee feature

The unified `/runs` architecture (ADR-0013) with title-as-join-key sets up self-play directly: checkpoints from multiple training runs play each other, results land in `/api/evaluations` with cross-checkpoint Elo. E1-E10 already has the Elo tracker infra (`290a9a43`). v1.x track-1 should be self-play league scheduling + leaderboard view.

### 2. SAC transition candidate

PPO served through v1.0 but reward sparsity in later episodes (R6 training at 2M steps showed plateau in mean_reward without corresponding win_rate gain) suggests off-policy + entropy-regularized updates may break through. SAC investigation planned for v1.x+ post-self-play. Gate: must not regress physics parity tests (ADR-0011 enforces).

### 3. E2E test matrix with isolation marker

Test-isolation rule currently requires running `pytest backend/tests/test_physics.py` etc. file-scoped. That's a discipline we can enforce in code: mark E2E tests with `@pytest.mark.e2e`, make default `pytest backend/tests/` run `-m 'not e2e'`, and E2E only runs with `-m e2e` + explicit `DEV_BASE_URL` env var. Land as v1.0.1 hotfix.

### 4. ?tab=evaluation/eval URL inconsistency

Known issue flagged in v1.0.0 release notes. Fix is mechanical — canonicalize to `?tab=evaluation` and add a one-line redirect for `?tab=eval`. v1.0.1 candidate.

### 5. Trainer branch strategic decision

PR #42 trainer was reverted with a do-not-retry decision. The trainer features (curriculum learning, grid search, early stopping, TensorBoard, reproducibility) are still valuable and should land in v1.x — **but via a fresh branch with syntax + parity gates from the start**, not a rebase of the reverted branch. Estimate: 2-3 days of re-work to reach parity with the reverted PR's functionality without the bug.

### 6. CI coverage gate

QA 19/19 PASS at release cut is great but we don't have a formal coverage floor. Add `pytest --cov` threshold at 80% for backend and `vitest --coverage` at 70% for frontend as a CI gate, blocking merges that drop coverage. v1.0.1 or v1.1 candidate depending on how much test backfill is needed.

### 7. Upstream divergence policy

ADR-0011 pins us to gorisanson upstream. The repo is generally stable but if upstream makes changes, we need a policy for fast-follow vs. intentional divergence. Draft as v1.0.x follow-up ADR.

## Credits

- **AI Engineer** — physics port + faithful audit (A-audit 1-4) + state machine expansion
- **Frontend Engineer** — view port + visual regression harness + all 9 bug rounds
- **Backend Engineer** — T1-T12 training title system + async eval job + runs aggregation
- **Evaluator (PR #44)** — E1-E10 full stack — merged 2026-04-12 `f9ffdd2d`
- **Designer** — 7 design specs front-loaded, D11-D15 FX overlays in v0.2.5
- **DevOps** — deploy-frontend auto-advance (`6f96d7fd`), docker log rotation, promote.sh force-recreate, 3 envs kept green through all 9 rounds
- **QA** — 19/19 regression pass at cut; test-isolation rule enforcement after pollution incident
- **Product Manager** — version/release orchestration, PR #42 revert call, unified nav decision

## References

- [CHANGELOG.md § 1.0.0](../CHANGELOG.md#100---2026-04-19)
- [RELEASE-NOTES-v1.0.0.md](RELEASE-NOTES-v1.0.0.md)
- [ADR-0011](adr/0011-faithful-port-with-parity-test.md)
- [ADR-0012](adr/0012-refactor-sprint-area-by-area-with-parity-gates.md)
- [ADR-0013](adr/0013-unified-runs-navigation.md)
- [docs/INDEX.md](INDEX.md)
- [docs/VERSIONS.yml](VERSIONS.yml)

# Incident: Dev Backend Serving 15-Hour-Stale Image

**Date:** 2026-04-12
**Detected:** 16:40 KST
**Resolved:** 17:09 KST (fix commit 63e29b58)
**Severity:** HIGH — dev env silently diverged from `github/dev` HEAD by 4 commits (~15h)
**Impact:** Feature verification + QA hand-off blocked; no prod/qa data loss
**Status:** Resolved (code fix landed + operational guard added)

---

## TL;DR

Dev backend (`pikachu-rl-dev-backend-1`, :8001) was serving an image built at
**2026-04-12 01:54 KST** (`sha256:367884fc…`) while the `github/dev` branch had
advanced by four commits over the next ~15 hours. The running container did not
contain any of the morning's hotfixes. Cause: `promote.sh dev-to-qa` rebuilt
only the target env (qa) — merges into `dev` itself never re-deployed dev.
Fix: `promote.sh` now runs `deploy-dev.sh` as a pre-deploy step so dev is
guaranteed to match `github/dev` HEAD before any promotion chain.

---

## Timeline (all times KST)

| Time  | Event |
|-------|-------|
| 01:54 | Dev backend last rebuilt → image `sha256:367884fc…` anchored at pre-morning SHA |
| 11:10 | `f8ea6126 fix: anti-toss-loop reward shaping` merged to `github/dev` |
| 16:37 | `91c7233d fix(ws): restore training:status broadcast after parallel fan-out (BE-6 hotfix)` |
| 16:38 | `7b5b4d6d Merge yoon/backend-engineer: BE-6 hotfix` + `77b871dd net-collision + bot-variance` |
| 16:40 | PM reports dev UI not reflecting WS broadcast fix → drift discovered |
| 16:51 | qa + prod rebuilt via `promote.sh` chain (both picked up the four commits — qa/prod were never stale) |
| 17:09 | `63e29b58 fix(deploy): promote.sh dev-to-qa also rebuilds dev backend` merged |
| 18:07 | `913fca5f fix(engine): rally-timeout safety valve` merged — later caused a second, separate missed-rebuild incident (see *Recurrence*) |

---

## Root Cause

`promote.sh dev-to-qa` historically had a single responsibility: merge
`github/dev` → `github/qa` and run `deploy-qa.sh` on the qa host. That design
made two implicit assumptions:

1. A merge into `dev` always triggers its own dev rebuild.
2. Between merges and the next promote, dev image == `github/dev` HEAD.

Neither was enforced anywhere. Engineers merging via GitHub UI (web merge,
squash merge, etc.) never touched the dev host. `deploy-frontend.sh dev`
rebuilt only the FE bundle on `yoonbian-2`, not the dev backend container on
`192.168.0.250`. The window between a dev merge and the next promote could
(and did) stretch past 15 hours without anyone noticing, because the dev
`/api/health` endpoint continued to return `200 OK` — healthy, just stale.

---

## Impact

- **Missed verification:** PM + QA attempted to exercise BE-6 WS broadcast and
  `anti-toss-loop` reward fix on dev. Both appeared to not work — because
  neither was actually running.
- **~20 min investigation lag:** team initially chased FE-side issues before
  `docker inspect` on the dev backend surfaced the stale image timestamp.
- **No data loss.** Training had been stopped; no in-flight experiments.
- **qa + prod were NOT affected** — verified via in-container grep for
  `WS_broadcast`, `anti_toss`, `net_collision`, `bot_variance` markers in all
  three env containers after the 16:51 promote chain.

---

## Fix

**Commit `63e29b58 fix(deploy): promote.sh dev-to-qa also rebuilds dev backend`**

`promote.sh` now injects `deploy-dev.sh` as a `PRE_DEPLOY_SCRIPT` step before
the dev→qa merge. This guarantees the dev image matches `github/dev` HEAD at
the moment of promotion, eliminating the silent-drift window.

Additionally, `DEPLOYMENT-STATUS.md` was rewritten from scratch with current
runtime state, an incident timeline, and post-incident operational rules.

---

## Recurrence (rally-timeout variant, same day)

Later the same day (~18:07 KST), commit `913fca5f` (rally-timeout safety
valve) was merged to dev. The subsequent `deploy-frontend.sh` run rebuilt FE
bundles but did NOT rebuild the backend image. Container `engine.py` had
`RALLY` match count = 0 even though the source had 14 matches. Detected when
PM reported "무한 랠리 또 발생." Fixed via `docker compose up -d --build
--force-recreate backend` on all three envs.

This second occurrence confirms the fix in `63e29b58` is necessary but **not
sufficient** — it closes the promote-chain path only. A direct `dev` merge
followed by `deploy-frontend.sh` (skipping promote) still leaves backend
stale. See *Prevention* below.

---

## Prevention

### Already done

- [x] `promote.sh` now triggers `deploy-dev.sh` as a pre-deploy step (commit
  `63e29b58`). Prevents drift in promote-chain paths.
- [x] `DEPLOYMENT-STATUS.md` § Post-Incident Operational Rules requires
  `docker inspect <container> --format '{{.Image}}'` verification after any
  merge into `dev`, `qa`, or `prod`.
- [x] `VERSIONS.yml` now carries `backend.image` sha256 digests per env
  (commit `b8f45681`), making drift detectable via diff.

### Pending (this housekeeping sprint)

- [ ] `scripts/deploy-frontend.sh` must NOT imply "backend is current." Add
  an explicit warning or rename it, and make a parallel `deploy-backend.sh`
  path so merges hit both without relying on operator memory.
- [ ] `scripts/deploy-frontend.sh` should auto-advance the env branch ref
  after a successful deploy so `github/{env}` always reflects what's running
  — detection path for future drift (Task #28).
- [ ] Add a cron or hook that compares `docker inspect <container>.Image`
  against `github/{env}` HEAD hourly and alerts on mismatch.

---

## Lessons

1. **"Healthy" ≠ "current."** A `200 OK` health endpoint proves the container
   is alive, not that its code matches the branch tip. Version checks must
   be semantic (git SHA or image digest), not just HTTP status.
2. **Every deploy script must be explicit about what it deploys.** The name
   `deploy-frontend.sh` implied FE-only was the intended scope; in practice
   users assumed it delivered "the latest dev state." Name and behavior must
   match.
3. **Silent drift is the worst-case drift.** The incident was only caught by
   manual UI verification. Monitoring must surface drift before a human does.
4. **When a system has two failure modes for the same symptom (promote path
   vs direct-merge path), one fix is rarely enough.** Close both.

---

## References

- Fix commit: [63e29b58](https://github.com/shyoon-devops/pikachu-volleyball-rl/commit/63e29b58)
- Image digest audit: [b8f45681 chore(versions): fill backend image digests for v0.2.4](https://github.com/shyoon-devops/pikachu-volleyball-rl/commit/b8f45681)
- Post-incident operational rules: `docs/DEPLOYMENT-STATUS.md` § Post-Incident Operational Rules
- Promote.sh source: `scripts/promote.sh`
- Dev deploy source: `scripts/deploy-dev.sh`, `scripts/deploy-frontend.sh`

# Deployment Status

> Last verified: **2026-04-12 17:10 +09:00** — curl probes + `docker inspect` + in-container grep evidence.
>
> **v0.2.3 deployed to all three environments.** Tag `v0.2.3` reachable from `github/main`; env tags `v0.2.3-{dev,qa,prod}` all pushed.
>
> Source of truth: `docs/VERSIONS.yml`. Ground rule: **any port change requires a PM-side doc update BEFORE the deploy**. See [WORKFLOW.md § Port Change Policy](WORKFLOW.md#port-change-policy).

---

## 1. Verified Runtime State (2026-04-12 17:10)

### Backend (GPU server, 192.168.0.250)
| Port | Status | Container start | Image digest (first 12) | Hotfix verification | Role |
|------|--------|-----------------|-------------------------|---------------------|------|
| `:8001` | **UP healthy** | 2026-04-12 17:03 KST | `6c4794c7a744` | BE-6 broadcast ✓, anti-toss ✓, net-collision ✓, bot-variance ✓ | **dev** |
| `:8002` | **UP healthy** | 2026-04-12 16:51 KST | `e0ba6de822f6` | BE-6 broadcast ✓, anti-toss ✓, net-collision ✓, bot-variance ✓ | **qa** |
| `:8003` | **UP healthy** | 2026-04-12 16:51 KST | `926b3f1358a9` | BE-6 broadcast ✓, anti-toss ✓, net-collision ✓, bot-variance ✓ | **prod** |

Verification method: `docker exec pikachu-rl-<env>-backend-1 grep 'manager.broadcast' /app/backend/app/ws/handlers.py` (returns `await manager.broadcast(message)` on line 99 in all three) + `grep 'stalled_out' /app/backend/rl/env.py` (19 hits in all three).

### Frontend (yoonbian-2, 192.168.0.248)
| Port | Status | Bundle hash | Role |
|------|--------|-------------|------|
| `:3000` | **UP HTTP 200** | `assets/index-JHqpaRFn.js` | **dev** |
| `:3001` | **UP HTTP 200** | `assets/index-JHqpaRFn.js` | **qa** |
| `:3002` | **UP HTTP 200** | `assets/index-JHqpaRFn.js` | **prod** |

All three serve the same v0.2.3 bundle. Per-env API/WS upstream differs in nginx config (`frontend/nginx-{dev,qa,prod}.conf`), not in the bundle itself.

### MongoDB
| Port | Role | Status |
|------|------|--------|
| `:27018` | dev | UP (healthy, via docker) |
| `:27019` | qa | UP (healthy, via docker) |
| `:27020` | prod | UP (healthy, via docker) |

---

## 2. Incident — Dev backend 15h stale (2026-04-12 16:40–17:03 KST)

**Symptom:** PM inspected http://192.168.0.248:3000 after v0.2.3 promote chain and found that BE-6 WS broadcast hotfix + f8ea6126 anti-toss-loop fix were not taking effect on dev, despite both commits being on `github/dev` for hours.

**Root cause:** `pikachu-rl-dev-backend-1` was running image `sha256:367884fc…` created 2026-04-12 01:54 KST — **~15 hours old**, built before both hotfix commits:
- `f8ea6126` anti-toss-loop fix (11:10 KST)
- `91c7233d` BE-6 WS broadcast fix (16:37 KST)
- `77b871dd` net-collision + bot-variance merge (16:38 KST)

`scripts/promote.sh dev-to-qa` rebuilds only the **target** env (qa) via `deploy-qa.sh`. It never touched dev. So every time a hotfix merged into `github/dev`, the dev backend kept serving the previously-built image until someone manually ran `deploy-dev.sh`.

**Remediation applied (PM, 17:03 KST):**
```
docker compose -f docker-compose.dev.yml up -d --build backend
```
Dev backend now running `sha256:6c4794c7…` with both hotfixes verified present.

**Remediation applied (DevOps, 17:10 KST — permanent fix in `scripts/promote.sh`):**
`dev-to-qa` promotion now runs `deploy-dev.sh` **before** the qa deploy (`PRE_DEPLOY_SCRIPT` block). Guarantees dev image == `github/dev` HEAD before a second environment sees the same commit. `qa-to-prod` is unchanged (qa is always rebuilt by its own prior promotion).

**qa/prod containers during the window:** both were rebuilt at 16:51 KST as part of the v0.2.3 promote chain — **after** all three hotfix commits. `docker inspect` + in-container grep confirms they already had the full fix set. No qa/prod rebuild required as part of this incident remediation.

---

## 3. Release History

| Version | Tag target | Tagged | Deployed | env tags |
|---------|------------|--------|----------|----------|
| v0.1.0 | `fd7b1301` | 2026-04-11 | prod (pre-refactor) | `v0.1.0-prod` |
| v0.2.0 | `d8fc62e3` | 2026-04-11 | qa only | — |
| v0.2.1 | `482df2d1` | 2026-04-12 | dev, qa | `v0.2.1-dev` @ `d5fce91e`, `v0.2.1-qa` @ `573f597d` |
| v0.2.2 | `2582886b` | 2026-04-12 16:03 | **never deployed** (superseded) | — |
| **v0.2.3** | **`737a088f`** | **2026-04-12 17:00** | **dev, qa, prod ✓** | **`v0.2.3-dev` @ `737a088f`, `v0.2.3-qa` @ `56f42412`, `v0.2.3-prod` @ `73e6b552`** |

**v0.2.3 includes:**
- v0.2.2 Sprint 2 batch (BE-5/6/7, FE-6/7/8/9, D6-D10, gorisanson faithful physics port)
- BE-6 WS training:status broadcast hotfix (`91c7233d`)
- Net-collision vx reversal guards (`bf6397cc`)
- Bot stochastic variance knobs (`6af36c0c`, `7b11b3d4`)
- Anti-toss-loop reward shaping (`f8ea6126`)
- v0.2.3 release docs (`98762931`, `732efb6f`)

`github/main` HEAD: `73e6b552 chore: promote qa to main`. `v0.2.3` tag is reachable from main: `git merge-base --is-ancestor 737a088f github/main` → 0 (yes).

---

## 4. Branch State (git facts, 2026-04-12 17:10)

```
dev    737a088f  docs: lock v0.2.3 tag target SHA to c3d067b7                ← v0.2.3-dev
qa     56f42412  chore: promote dev to qa                                     ← v0.2.3-qa
main   73e6b552  chore: promote qa to main                                    ← v0.2.3-prod
```

All three env branches contain `f8ea6126`, `91c7233d`, `7b5b4d6d`, `77b871dd`, `f4fa1447`. Verified via `git merge-base --is-ancestor`.

---

## 5. Operational Rules (post-incident)

1. **Never promote without refreshing source.** `promote.sh dev-to-qa` now runs `deploy-dev.sh` first. Do not rely on "someone will rebuild dev eventually" — the dev image can silently drift from `github/dev` HEAD for hours.
2. **After a merge into dev**, always verify the dev backend image is fresh: `docker inspect pikachu-rl-dev-backend-1 --format '{{.Created}}'` should be newer than the merge commit's timestamp. If not, run `bash scripts/deploy-dev.sh`.
3. **Deploy scripts DO rebuild + restart.** `deploy-dev.sh`, `deploy-qa.sh`, `deploy-prod.sh` all use `docker compose up --build -d --remove-orphans`, which rebuilds the image and recreates the container. The incident was not a deploy-script bug; it was an **orchestration gap** where no script was being invoked on dev after merges.
4. **Post-deploy verification for any hotfix:** `docker exec pikachu-rl-<env>-backend-1 grep <marker> /app/backend/...` to confirm the fix is in the running image, not just in git. `/api/health` `status=ok` is insufficient — it stays green on stale images too.

---

## 6. Open Issues

| Issue | Title | State | Note |
|-------|-------|-------|------|
| #37 | deploy: v0.2.1 prod 승격 | can be closed | Superseded by v0.2.3 prod deploy |
| #38 | ops: 3개 환경 실제 배포 상태 전수 보고 | can be closed | This doc is the report |

---

## 7. What this replaces

Previous revision claimed "v0.2.3 runtime deploy pending" and listed qa `:8002` as DOWN. Both were accurate at 16:40 KST; neither holds at 17:10 KST. Curl + `docker inspect` + in-container grep evidence above supersedes everything earlier in this file's history.

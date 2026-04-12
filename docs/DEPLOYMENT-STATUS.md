# Deployment Status

> Last verified: **2026-04-12 16:40 +09:00** — this file is rewritten from scratch based on **actual curl probes** of the running environments. Previous revisions contained fabricated ports and versions. Source of truth going forward: `docs/VERSIONS.yml`.
>
> **v0.2.3 tag cut at dev HEAD `77b871dd` on 2026-04-12 16:40 +09:00** — v0.2.2 (`2582886b`) was tagged but never deployed; v0.2.3 supersedes it with 3 QA blocker hotfixes (BE-6 WS broadcast, net-collision vx, bot variance). Runtime deploy pending. Once DevOps executes dev→qa→prod, every environment below moves from v0.2.1 (or pre-BE-3) to v0.2.3.
>
> Ground rule: **any port change requires a PM-side doc update BEFORE the deploy**. See [WORKFLOW.md § Port Change Policy](WORKFLOW.md#port-change-policy).

---

## 1. Verified Runtime State (curl evidence, 2026-04-12)

### Backend (GPU server, 192.168.0.250)
| Port | Status | `/api/health` shape | `/api/health/live` | OpenAPI `info.version` | Inferred role |
|------|--------|---------------------|--------------------|------------------------|----------------|
| `:8000` | DOWN | — | — | — | (documented prod port, **not in use**) |
| `:8001` | **UP** | Detailed — `mongo/disk/training/queues` checks | `{"status":"live"}` ✅ BE-3 present | `"0.1.0"` (hardcoded) | **dev** |
| `:8002` | **DOWN** | — | — | — | (documented qa port — currently not running) |
| `:8003` | **UP** | Minimal — `{"status":"ok"}` only | `404 Not Found` ❌ (pre-BE-3) | `"0.1.0"` (hardcoded) | **prod** (per PM observation) |

### Frontend (yoonbian-2, 192.168.0.248)
| Port | Status | HTML size | Bundle hash | Inferred role |
|------|--------|-----------|-------------|----------------|
| `:3000` | **UP** | 910 B | `assets/index-CAYlGd5L.js` | **dev** |
| `:3001` | **UP** | 910 B | `assets/index-CAYlGd5L.js` | **qa** |
| `:3002` | **UP** | 910 B | `assets/index-CAYlGd5L.js` | **prod** |
| `:5173` | **DOWN** | — | — | (documented prod port, **not in use**) |

**Critical finding — three frontends serve a byte-identical bundle:** `diff` between `:3000`, `:3001`, `:3002` returns zero output, and all reference the same `index-CAYlGd5L.js`. DevOps has not confirmed whether this is intended (single dist served on 3 ports with only nginx API/WS upstream differing) or accidental (env-specific builds overwritten). Tracking in #38.

### MongoDB
Not curl-probeable from this host. PM observation: **prod MongoDB actually on `:27020` (not `:27017` as documented)**. Awaiting DevOps confirmation (#38) for dev/qa/prod MongoDB ports.

### Critical inconsistency
- `prod` backend `:8003` is running **pre-BE-3 / pre-BUG-2 code** — `/api/health` returns the hardcoded `{"status":"ok"}` that BUG-2 was filed against. Prod has **NOT** been promoted to v0.2.1. Any claim that "v0.2.1 shipped to prod" is false until :8003 shows BE-3's `/health/live` + `/health/ready` split.
- All three frontends serve the same bundle. Whatever is on prod is also what dev/qa users see. No env-specific FE deployment is occurring.
- OpenAPI `info.version` is hardcoded `"0.1.0"` on every backend. It cannot be used to determine deployed version.

---

## 2. Environment Overview (verified + unknown)

| Env | Backend port | Backend build | Frontend port | Frontend bundle | MongoDB port | Version tag in place | Notes |
|-----|--------------|---------------|---------------|-----------------|--------------|---------------------|-------|
| dev | `:8001` ✅ | **UNKNOWN commit** (BE-3 present) | `:3000` ✅ | `index-CAYlGd5L.js` | **UNKNOWN** | none (git branch `dev` @ `482df2d1` tagged `v0.2.1`) | training state: stopped |
| qa | **DOWN** ❌ | n/a | `:3001` ✅ | `index-CAYlGd5L.js` | **UNKNOWN** | git branch `qa` @ `1baa3e3b` | Backend not running — #38 DevOps 확인 |
| prod | `:8003` ✅ | **pre-BE-3** (NOT v0.2.1) | `:3002` ✅ | `index-CAYlGd5L.js` | `:27020` (PM report, unverified) | git branch `prod` @ `41f4fdb` + git branch `main` @ `fdc41de`, `v0.1.0` tag | Running OLD code |

Commit hashes and build times are **UNKNOWN** until DevOps reports in #38. Do not infer from git branch HEAD — the image in production may lag the branch.

---

## 3. Release History (verifiable facts only)

| Version | Tag created | Tag target | GitHub Release | Deployed to prod? | main merged? | Release note |
|---------|-------------|------------|----------------|-------------------|--------------|--------------|
| v0.1.0 | 2026-04-11 | prod HEAD at the time | ✅ | Yes (running on `:8003` — inferred from feature set) | Yes — main @ `fdc41de` | [releases/v0.1.0.md](releases/v0.1.0.md) |
| v0.2.0 | 2026-04-11 | `d8fc62e` (release commit) | ✅ | **No** — prod still on pre-BE-3 code | No | [releases/v0.2.0-qa.md](releases/v0.2.0-qa.md) |
| v0.2.1 | 2026-04-12 | `482df2d1` on github/dev | ✅ | **No** — prod `:8003` lacks BE-3 `/health/live` | No | [releases/v0.2.1.md](releases/v0.2.1.md) |
| v0.2.2 | **2026-04-12 16:03** | `2582886b` on github/dev (post product-manager merge) | ✅ | **No** — superseded by v0.2.3 before any deploy | No | [releases/v0.2.2.md](releases/v0.2.2.md) (superseded) |
| v0.2.3 | **2026-04-12 16:40** | `77b871dd` on github/dev (v0.2.2 + 3 hotfixes) | pending | **No** — DevOps deploy pending | No | [releases/v0.2.3.md](releases/v0.2.3.md) |

Env-specific tags present: `v0.1.0-prod` (41f4fdb1), `v0.2.1-dev` (482df2d1), `v0.2.1-qa` (1baa3e3b). `v0.2.3-{dev,qa,prod}` to be created by DevOps after each environment deploy (per WORKFLOW.md § Release Creation Procedure). **No `v0.2.2-*` env tags will be created** — v0.2.2 was never deployed.

**Correction to earlier documents:** Previous `DEPLOYMENT-STATUS.md` claimed "v0.2.0 running on prod" or "main merged with v0.2.0 tag" at various points. Curl evidence shows prod has only v0.1.0-era code. That claim was wrong.

---

## 4. Pending Actions (ordered)

1. **DevOps v0.2.3 deploy GO** — 태그 `v0.2.3` (target `77b871dd`) 를 dev→qa→prod 전 환경 배포. env tag `v0.2.3-{dev,qa,prod}` 각 배포 시점에 생성 필수. Smoke test 통과 후 다음 환경 진행. **v0.2.2 는 건너뜀** (tagged but never deployed).
2. **DevOps #38** — provide commit hashes, build times, MongoDB ports, QA-backend-down reason within 30 minutes of file time
3. **PM** — 각 환경 배포 완료 보고 수신 후 30분 내 이 파일 Section 1 + VERSIONS.yml 의 commit/image/deployed_at 채움 (WORKFLOW.md § Post-Deploy Doc Update)
4. **#37 prod promotion** — v0.2.3 로 번들 승격 (prod 가 v0.1.0 → v0.2.3 jump). Precondition: qa smoke test + 16-bug regression + BE-6 broadcast 재검증 + net-collision regression suite GREEN
5. **DevOps** — restart qa backend (:8002) 복구 선행 (#38) → v0.2.3 qa 검증 블로커
6. **DevOps** — frontend 번들 정책 확인: `v0.2.3` 빌드가 3 환경에 **별도** rsync 되는지 검증 (현재 3 포트 byte-identical)
7. **PM (prod 승격 후)** — prod → main 머지 + `v0.2.3` 태그 main reachable 확인 + `git push github main --tags`

---

## 5. Open Issues Snapshot (Sprint 1/2, 2026-04-12)

| Issue | Title | State | Labels | Note |
|-------|-------|-------|--------|------|
| #37 | deploy: v0.2.1 prod 승격 | OPEN | release | blocked on preconditions + prod-drift |
| #38 | ops: 3개 환경 실제 배포 상태 전수 보고 | OPEN | release | PM 블로커 — DevOps 응답 대기 |
| #35 | DO-3 MongoDB Automated Backup | OPEN | enhancement, sprint-2 | Sprint 2 |
| #34 | QA-3 FastAPI TestClient Integration Suite | OPEN | enhancement, sprint-2 | Sprint 2 |
| #33 | BE-5 Backend Test Coverage ≥ 80% | OPEN | enhancement, sprint-2 | Sprint 2 |
| #30 | FE-2 MetricsChart Smoothing + Zoom | OPEN | enhancement, sprint-2 | Sprint 2 |
| #4  | test: 프론트엔드 테스트 커버리지 보강 | OPEN | sprint-2 | Sprint 2 |

All other Sprint 1 issues (#3, #9, #10, #11, #12, #13–#19, #20, #21, #22, #23, #24, #25, #26, #27, #31, #32, #36) are CLOSED.

---

## 6. Branch State (git facts, not deploy facts)

```
dev    2582886b  chore: merge product-manager — v0.2.2 release docs               ← v0.2.2 tag here
qa     1baa3e3b  chore: promote dev to qa                                          ← v0.2.1-qa (re-promoted), awaiting dev→qa for v0.2.2
prod   41f4fdb1  fix: resolve conflict markers in dev branch frontend files       ← v0.1.0 근방, v0.1.0-prod env tag
main   fdc41de   prod mirror                                                      ← v0.1.0 태그 on main HEAD
```

Git branch ≠ running build. The running prod backend is v0.1.0-era code per `/api/health` shape, which matches the git `prod` branch content.

---

## 7. What PM got wrong in prior revisions (inventory)

- Documented ports `:8000 / :5173 / :27017` for prod — all wrong.
- Documented qa backend `:8002` as active — currently DOWN.
- Claimed v0.2.0 prod deploy in comments — never happened per curl.
- Claimed "main merged with v0.1.0 tag" stayed in sync with prod — true at tag time but prod has drifted (different branches now).
- README's architecture/ports table propagated the same wrong ports.
- OpenAPI `info.version` was assumed to reflect deploy; it is hardcoded `0.1.0` in source.

This file now treats every field not directly observed via curl as **UNKNOWN**. DevOps must supply the rest.

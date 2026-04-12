# Deployment Status

> Last verified: **2026-04-12** — this file is rewritten from scratch based on **actual curl probes** of the running environments. Previous revisions contained fabricated ports and versions. Source of truth going forward: `docs/VERSIONS.yml`.
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

| Version | Tag created | Tag target | Deployed to prod? | main merged? | Release note |
|---------|-------------|------------|-------------------|--------------|--------------|
| v0.1.0 | 2026-04-11 | prod HEAD at the time | Yes (running on `:8003` as of this writing — inferred from feature set) | Yes — main @ `fdc41de` | Initial structure |
| v0.2.0 | 2026-04-11 | `d8fc62e` (release commit) | **No** — prod still on pre-BE-3 code | No | [releases/v0.2.0-qa.md](releases/v0.2.0-qa.md) |
| v0.2.1 | 2026-04-12 | `482df2d1` on github/dev | **No** — prod `:8003` lacks BE-3 `/health/live` | No | CHANGELOG [0.2.1] section |

**Correction to earlier documents:** Previous `DEPLOYMENT-STATUS.md` claimed "v0.2.0 running on prod" or "main merged with v0.2.0 tag" at various points. Curl evidence shows prod has only v0.1.0-era code. That claim was wrong.

---

## 4. Pending Actions (ordered)

1. **DevOps #38** — provide commit hashes, build times, MongoDB ports, QA-backend-down reason within 30 minutes of file time
2. **PM** — on receiving #38 response, rewrite this file Section 1 + VERSIONS.yml with filled-in values; remove all UNKNOWN markers
3. **#37 prod promotion** — still blocked on precondition (b) FE 중복 Start 버튼 + (c) smoke test; further blocked now that prod is confirmed to be on pre-BE-3 code (means this is a real v0.1.0 → v0.2.1 promotion, not a patch)
4. **DevOps** — restart qa backend (:8002 or new port) so QA can verify v0.2.1
5. **DevOps** — confirm frontend deploy policy (single dist on 3 ports vs. 3 builds) and either (a) document it in WORKFLOW, or (b) fix so each env gets its own build

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
dev    482df2d1  feat(api): TTL cache + unified pagination envelope (BE-2)        ← v0.2.1 tag here
qa     1baa3e3b  chore: promote dev to qa                                          ← BE-2/BE-3 재승격
prod   41f4fdb1  fix: resolve conflict markers in dev branch frontend files       ← v0.1.0 근방
main   fdc41de   prod mirror                                                      ← v0.1.0 태그
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

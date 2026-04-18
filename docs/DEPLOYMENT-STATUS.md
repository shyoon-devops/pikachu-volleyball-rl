# Deployment Status

> Last verified: **2026-04-12 23:55 +09:00** — v0.2.5 post-deploy closure (env tags + main advance). Source of truth: `docs/VERSIONS.yml`.
>
> **v0.2.5 tag anchored at runtime source `cd1e6a39`** (P0 match-end freeze hotfix merged on top of Phase 2 `6f4a057f`). dev HEAD 는 `09a3f99d` — v0.2.5 release docs + PR #42 revert + CHANGELOG cleanup 3 commit 이 cd1e6a39 위에 쌓여 있음. env 태그 `v0.2.5-{dev,qa,prod}` 모두 `cd1e6a39` 지목. 3 환경 byte-identical bundle `index-CFGidFNF.js`. main advance `cd1e6a39` 완료 — v0.2.5 main reachable ✅.
>
> Ground rule: **any port change requires a PM-side doc update BEFORE the deploy**. See [WORKFLOW.md § Port Change Policy](WORKFLOW.md#port-change-policy).

---

## 1. Verified Runtime State (curl probe + DevOps images, 2026-04-12 23:55)

### Backend (GPU server, 192.168.0.250)
| Port | Status | Version (runtime) | `/api/health/live` | Uptime | Image digest | Role |
|------|--------|-------------------|--------------------|--------|--------------|------|
| `:8001` | **UP** | v0.2.5 (`cd1e6a39`) | `{"status":"live"}` ✅ | ~14min | `sha256:d577fb9a…` | **dev** (PR #42 revert → BE rebuild 완료) |
| `:8002` | **UP** | v0.2.5 (`cd1e6a39`) | `{"status":"live"}` ✅ | ~35min | `sha256:304a259d…` | **qa** |
| `:8003` | **UP** | v0.2.5 (`cd1e6a39`) | `{"status":"live"}` ✅ | ~35min | `sha256:10e7b3b3…` | **prod** |

Runtime 신 코드 검증 (PM curl + DevOps 보고):
- P0 `post_score_freeze_frames` tick BEFORE match-over guard (engine.py:219-220) — 15pt 고착 해소
- `/api/training/status` 에 `experiment_id` / `bot_level` / `started_at` 필드 응답 확인 (3 env)
- `punch_effect_radius` (6 matches) + `is_diving` (engine.py:48, 350) — Phase 2 FX 유지
- `/api/training/metrics/timeseries` cap 10000 + `log_interval=256` (callbacks.py:88)
- Bot L1-L5 aggression/net_bias 활성

### Frontend (yoonbian-2, 192.168.0.248)
| Port | Status | Bundle | Role |
|------|--------|--------|------|
| `:3000` | **UP** | `assets/index-CFGidFNF.js` | **dev** |
| `:3001` | **UP** | `assets/index-CFGidFNF.js` | **qa** |
| `:3002` | **UP** | `assets/index-CFGidFNF.js` | **prod** |

3 환경 byte-identical bundle (P0 hotfix 는 BE-only 이므로 FE delta = 0 from Phase 2 번들).

### MongoDB
dev `:27018` / qa `:27019` / prod `:27020` — 미검증 (wire protocol 접근 필요).

---

## 2. Environment Overview

| Env | Backend port | Backend commit | Frontend port | Frontend bundle | Branch HEAD | env tag → SHA | Notes |
|-----|--------------|----------------|---------------|-----------------|-------------|---------------|-------|
| dev | `:8001` ✅ | `cd1e6a39` | `:3000` ✅ | `index-CFGidFNF.js` | `09a3f99d` | `v0.2.5-dev` → `cd1e6a39` | runtime = cd1e6a39, v0.2.5 docs + PR #42 revert + CHANGELOG cleanup 3 commit on top |
| qa  | `:8002` ✅ | `cd1e6a39` | `:3001` ✅ | `index-CFGidFNF.js` | `cd1e6a39` | `v0.2.5-qa` → `cd1e6a39` | branch = runtime (auto-advanced by deploy-frontend.sh) |
| prod | `:8003` ✅ | `cd1e6a39` | `:3002` ✅ | `index-CFGidFNF.js` | `cd1e6a39` | `v0.2.5-prod` → `cd1e6a39` | branch = runtime |
| main | n/a | n/a | n/a | n/a | `cd1e6a39` | (v0.2.5 reachable ✅) | fast-forward by PM `git push github cd1e6a39:main` |

---

## 3. Release History

| Version | Tag created | Tag target | GitHub Release | Deployed to prod? | main reachable? | Release note |
|---------|-------------|------------|----------------|-------------------|-----------------|--------------|
| v0.1.0 | 2026-04-11 | prod HEAD at the time | ✅ | Yes | Yes — main @ `fdc41de` | [releases/v0.1.0.md](releases/v0.1.0.md) |
| v0.2.0 | 2026-04-11 | `d8fc62e` | ✅ | No — prod still on pre-BE-3 code | No | [releases/v0.2.0-qa.md](releases/v0.2.0-qa.md) |
| v0.2.1 | 2026-04-12 | `482df2d1` on github/dev | ✅ | No — superseded | No | [releases/v0.2.1.md](releases/v0.2.1.md) |
| v0.2.2 | 2026-04-12 16:03 | `2582886b` on github/dev | ✅ | No — superseded by v0.2.3 before any deploy | No | [releases/v0.2.2.md](releases/v0.2.2.md) (superseded) |
| v0.2.3 | 2026-04-12 16:40 | `737a088f` on github/dev | ✅ | **Yes** — 3 envs | No — superseded | [releases/v0.2.3.md](releases/v0.2.3.md) |
| v0.2.4 | 2026-04-12 18:20 | `dabd84a1` (runtime) · `d4a89231` (doc_head) | ✅ | **Yes** — 3 envs `index-DqBsWzf5` | Yes (via cd1e6a39 descendant) | [releases/v0.2.4.md](releases/v0.2.4.md) |
| v0.2.5 | **2026-04-12 22:45** | `cd1e6a39` (runtime) · `09a3f99d` (doc_head) | ✅ | **Yes** — 3 envs byte-identical bundle `index-CFGidFNF.js` | **Yes** — main @ `cd1e6a39` | [releases/v0.2.5.md](releases/v0.2.5.md) |

Env tags present: `v0.1.0-prod`, `v0.2.1-{dev,qa}`, `v0.2.3-{dev,qa,prod}`, `v0.2.4-{dev,qa,prod}` (→ `dabd84a1`), `v0.2.5-{dev,qa,prod}` (→ `cd1e6a39`).

---

## 4. Pending Actions (ordered)

1. **PM → DevOps** — v0.2.5 배포 완전 종료 커뮤니케이션 (현재 DevOps 429 rate-limited). v0.2.6 candidate 작업 재개 여부 판단 대기.
2. **DevOps** — image rebuild 안정화 후 (현재 완료) `scripts/deploy-frontend.sh` 의 auto-advance step 과 실제 backend 재빌드가 **동시에** 돌아가도록 통합 지점 검토. 이번 세션에서 두 번 드러난 드리프트 (branch ref만 advance + image 구버전 잔존) 재발 방지.
3. **Trainer 브랜치** — PM 결정: 재머지 시도 금지. PR #42 는 GitHub state `MERGED` 이지만 내용은 `ffe1ae6a` revert 로 전부 되돌려짐. 새 trainer 기능은 별도 브랜치 + 별도 PR 로 재작성 필요.
4. **Post-v0.2.5 cleanup**
   - `docs/releases/v0.2.5-draft-post-deploy.md` scratch 삭제 (이미 VERSIONS.yml + DEPLOYMENT-STATUS.md 에 반영 완료)
   - Issue #46 / #47 / #37 / #38 close (v0.2.5 이 각 블로커 해소)

---

## 5. Open Issues Snapshot

| Issue | Title | State | Labels | Note |
|-------|-------|-------|--------|------|
| #46 | deploy: v0.2.3 | OPEN | release | v0.2.4 로 대체 close 예정 |
| #47 | deploy: v0.2.4 3-env rollout | OPEN | release | 배포 완료 — close 예정 |
| #37 | deploy: v0.2.1 prod 승격 | OPEN | release | v0.2.4 가 v0.1.0→v0.2.4 jump 로 해소 — close 예정 |
| #38 | ops: 3개 환경 실제 배포 상태 전수 보고 | OPEN | release | VERSIONS.yml image SHA 채운 후 close |
| #35 | DO-3 MongoDB Automated Backup | OPEN | enhancement, sprint-2 | Sprint 2 |
| #34 | QA-3 FastAPI TestClient Integration Suite | OPEN | enhancement, sprint-2 | Sprint 2 |
| #33 | BE-5 Backend Test Coverage ≥ 80% | OPEN | enhancement, sprint-2 | Sprint 2 |
| #30 | FE-2 MetricsChart Smoothing + Zoom | OPEN | enhancement, sprint-2 | Sprint 2 |
| #4  | test: 프론트엔드 테스트 커버리지 보강 | OPEN | sprint-2 | Sprint 2 |

---

## 6. Branch State (git facts — post v0.2.5 closure)

```
dev    09a3f99d  docs(changelog): remove PR #42 trainer from [Unreleased] — reverted   ← runtime cd1e6a39 + v0.2.5 docs + PR #42 revert + cleanup
qa     cd1e6a39  merge: P0 hotfix — match-end freeze tick                              ← runtime SHA
prod   cd1e6a39  merge: P0 hotfix — match-end freeze tick                              ← runtime SHA
main   cd1e6a39  merge: P0 hotfix — match-end freeze tick                              ← PM push cd1e6a39:main (018a2be1 → cd1e6a39)
```

v0.2.5 annotated tag → `cd1e6a39` (실제 컨테이너 빌드 SHA). 3 환경별 태그 (`v0.2.5-{dev,qa,prod}`) 도 모두 `cd1e6a39` 지목. 3 환경 bundle `index-CFGidFNF.js` byte-identical. main reachable ✅.

---

## 7. v0.2.5 Verification Checklist (PM smoke test — executed 2026-04-12 23:55)

- [x] 3 환경 `/api/health/live` → `{"status":"live"}` (dev uptime 14min, qa/prod uptime 35min)
- [x] 3 환경 `/api/training/status` 에 `state`/`bot_level`/`experiment_id`/`started_at` 응답
- [x] qa `/api/training/status` 에 `current_step=895000 / current_episode=466 / bot_level=5` — 전체 훈련 사이클 기록 보존
- [x] 3 환경 FE bundle `assets/index-CFGidFNF.js` byte-identical (curl HEAD)
- [x] v0.2.5 annotated tag → `cd1e6a39` runtime SHA
- [x] `v0.2.5-{dev,qa,prod}` env 태그 모두 `cd1e6a39` 지목
- [x] main HEAD = `cd1e6a39` (`git tag --contains v0.2.5 | grep main` ✅)
- [x] `dev` HEAD `09a3f99d` = v0.2.5 runtime + docs delta (PR #42 revert 포함)
- [x] PR #42 revert `ffe1ae6a` 반영 — trainer.py syntax error 완전 제거

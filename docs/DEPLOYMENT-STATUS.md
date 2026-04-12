# Deployment Status

> Last verified: **2026-04-12 18:25 +09:00** — v0.2.4 post-deploy doc update. Source of truth: `docs/VERSIONS.yml`.
>
> **v0.2.4 tag cut at dev HEAD `921b0efb` on 2026-04-12 18:20 +09:00** — v0.2.4 는 v0.2.3 위 누적된 4 CRITICAL hotfix + 6 UX/정합성 개선 번들. DevOps 는 3 환경에 byte-identical bundle `index-DqBsWzf5` 로 단일 배포 완료 (backend force-recreate, uptime 2분 검증). env tag `v0.2.4-{dev,qa,prod}` 부착 완료.
>
> Ground rule: **any port change requires a PM-side doc update BEFORE the deploy**. See [WORKFLOW.md § Port Change Policy](WORKFLOW.md#port-change-policy).

---

## 1. Verified Runtime State (DevOps report, 2026-04-12 18:15)

### Backend (GPU server, 192.168.0.250)
| Port | Status | Version (runtime) | `/api/health/live` | `/api/health/ready` | Role |
|------|--------|-------------------|--------------------|---------------------|------|
| `:8001` | **UP** | v0.2.4 (`dabd84a1`) | `{"status":"live"}` ✅ | ✅ | **dev** |
| `:8002` | **UP** | v0.2.4 (`dabd84a1`) | `{"status":"live"}` ✅ | ✅ | **qa** (복구됨 — 이전 v0.2.3 deploy window 에서 재기동) |
| `:8003` | **UP** | v0.2.4 (`dabd84a1`) | `{"status":"live"}` ✅ | ✅ | **prod** (v0.1.0-era → v0.2.4 jump) |

Runtime 신 코드 검증 (DevOps 보고):
- `/api/training/metrics/timeseries` 엔드포인트 응답 확인 (`{step, value, timestamp}` shape)
- `ball.is_power_hit` 필드가 `training:frame` WS payload 에 포함
- `RALLY_MAX_FRAMES=600` rally-timeout safety valve 활성

### Frontend (yoonbian-2, 192.168.0.248)
| Port | Status | Bundle | Role |
|------|--------|--------|------|
| `:3000` | **UP** | `assets/index-DqBsWzf5.js` | **dev** |
| `:3001` | **UP** | `assets/index-DqBsWzf5.js` | **qa** |
| `:3002` | **UP** | `assets/index-DqBsWzf5.js` | **prod** |

3 환경 byte-identical bundle (이번 번들은 의도적 단일 dist — DevOps `scripts/deploy-frontend.sh` 가 3 환경에 동일 rsync, nginx upstream 만 per-env API/WS 프록시).

### MongoDB
PM 문서상 dev `:27018` / qa `:27019` / prod `:27020` — DevOps 미검증. 후속 housekeeping 에서 확인.

---

## 2. Environment Overview

| Env | Backend port | Backend commit | Frontend port | Frontend bundle | Version tag | env tag | Notes |
|-----|--------------|----------------|---------------|-----------------|-------------|---------|-------|
| dev | `:8001` ✅ | `dabd84a1` | `:3000` ✅ | `index-DqBsWzf5.js` | `v0.2.4` @ `921b0efb` | `v0.2.4-dev` | 정상 |
| qa  | `:8002` ✅ | `dabd84a1` | `:3001` ✅ | `index-DqBsWzf5.js` | branch @ `5c758d8e` (lags) | `v0.2.4-qa` | Branch HEAD 런타임보다 뒤처짐 (image-based promote) |
| prod | `:8003` ✅ | `dabd84a1` | `:3002` ✅ | `index-DqBsWzf5.js` | branch @ `41f4fdb1` (v0.1.0-era) | `v0.2.4-prod` | Branch 는 여전히 v0.1.0-era — **advance + main 머지 필요** |

---

## 3. Release History

| Version | Tag created | Tag target | GitHub Release | Deployed to prod? | main merged? | Release note |
|---------|-------------|------------|----------------|-------------------|--------------|--------------|
| v0.1.0 | 2026-04-11 | prod HEAD at the time | ✅ | Yes | Yes — main @ `fdc41de` | [releases/v0.1.0.md](releases/v0.1.0.md) |
| v0.2.0 | 2026-04-11 | `d8fc62e` | ✅ | No — prod still on pre-BE-3 code | No | [releases/v0.2.0-qa.md](releases/v0.2.0-qa.md) |
| v0.2.1 | 2026-04-12 | `482df2d1` on github/dev | ✅ | No — superseded | No | [releases/v0.2.1.md](releases/v0.2.1.md) |
| v0.2.2 | 2026-04-12 16:03 | `2582886b` on github/dev | ✅ | No — superseded by v0.2.3 before any deploy | No | [releases/v0.2.2.md](releases/v0.2.2.md) (superseded) |
| v0.2.3 | 2026-04-12 16:40 | `737a088f` on github/dev | ✅ | **Yes** — 3 envs | No — superseded | [releases/v0.2.3.md](releases/v0.2.3.md) |
| v0.2.4 | **2026-04-12 18:20** | `921b0efb` on github/dev (dabd84a1 runtime + docs expansion) | ✅ | **Yes** — 3 envs byte-identical bundle `index-DqBsWzf5` | pending (#17) | [releases/v0.2.4.md](releases/v0.2.4.md) |

Env tags present: `v0.1.0-prod`, `v0.2.1-dev`, `v0.2.1-qa`, `v0.2.3-{dev,qa,prod}`, `v0.2.4-{dev,qa,prod}` (모두 2026-04-12 18:20 dev HEAD 에 부착).

---

## 4. Pending Actions (ordered)

1. **PM — prod branch advance + main 머지** (#17)
   - `github/prod` 브랜치를 dev HEAD `921b0efb` 로 advance (현재 `41f4fdb1` v0.1.0-era 이므로 사실상 강제 동기화 필요)
   - `prod → main` `--no-ff` 머지 (v0.2.0/0.2.1/0.2.2/0.2.3/0.2.4 scope 모두 최초 반영)
   - `git tag --contains v0.2.4 | grep main` 으로 reachable 확인
   - `git push github main --tags`
2. **DevOps** — `github/qa` 브랜치를 런타임 코드(`dabd84a1`) 로 fast-forward 하는 housekeeping PR (런타임은 이미 dev HEAD image)
3. **DevOps** — `docs/incidents/20260412-dev-backend-stale.md` 인시던트 기록 발행 (`promote.sh` backend restart 누락 → 수정 `63e29b58`)
4. **DevOps** — image SHA / build digest 를 VERSIONS.yml 각 env 의 `backend.image` 에 채움 (30분 SLA)

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

## 6. Branch State (git facts)

```
dev    921b0efb  docs: expand v0.2.4 scope                                          ← v0.2.4 tag here
qa     5c758d8e  chore: promote dev to qa (pre-power-hit)                           ← lags runtime
prod   41f4fdb1  fix: resolve conflict markers in dev branch frontend files         ← v0.1.0-era, MUST advance
main   71b4cb1c  prod mirror (stale)                                                ← v0.1.0 tag here, pending v0.2.4 merge
```

**Branch ≠ runtime**: qa 와 prod 의 실제 컨테이너는 모두 dev HEAD `dabd84a1` 로 빌드된 이미지를 돌리고 있음. 3 환경 bundle 도 byte-identical. 다만 git 브랜치 기록이 뒤처져 있어 `git tag --contains v0.2.4` 가 main 에서 아직 빈 결과를 반환함.

---

## 7. v0.2.4 Verification Checklist (PM smoke test — executed 2026-04-12)

- [x] 3 환경 `/api/health/live` → `{"status":"live"}`
- [x] `/api/training/status` 에 `bot_level`/`experiment_id`/`started_at` 포함
- [x] 훈련 중 새로고침 → Stop 버튼 노출 유지 (hotfix #1 bd6cea5a)
- [x] Stop 클릭 → step/episode 카운터 즉시 멈춤 + badge "stopped" (hotfix #3 ee1b48ae)
- [x] Pause → Resume 1 cycle (hotfix #3)
- [x] 새로고침 → 그래프 + 최근경기 패널 seed 복원 (hotfix #2 06519a42)
- [x] L1~L5 버튼 선택 표시 + Start 시 silent reset 없음 (hotfix #8 Option A)
- [x] rally 600 frames 초과 시 자동 종료 + 다음 게임 (hotfix #4 913fca5f)
- [x] 차트 새로고침 전후 동일 step 에서 동일 Y (hotfix #5 + /timeseries)
- [x] Hyper-ball trail 렌더 (hotfix #7 3b4303df/33f6b868)

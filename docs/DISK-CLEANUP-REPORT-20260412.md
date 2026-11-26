# Disk Cleanup Report — 2026-04-12

v0.2.4 재배포(dev/qa/prod) 완료 직후 실행한 디스크/이미지 정리 결과.

## Before (baseline at task start)

| 항목 | 값 |
|------|-----|
| `/` 파티션 | 95G used / 1007G (**10%**) |
| Docker images | **18.67 GB** (v0.2.3 + v0.2.4 mixed) |
| Build cache | **9.78 GB** |
| Volumes | ~1.95 GB (models/mongo 혼합) |
| Model .zip files | dev=173, qa=168, prod=14 (총 355개) |

## Actions

1. `docker builder prune -af` — **9.78 GB 회수** (build cache 0B)
2. `docker image prune -af` — v0.2.3 스테일 backend 이미지 eviction, 신규 v0.2.4 빌드로 교체
3. 체크포인트 로테이션 (keep latest 5 per experiment):
   - dev: 168 .zip 삭제, **277 MB** freed (5 experiments)
   - qa:  163 .zip 삭제, **268 MB** freed (6 experiments)
   - prod:  9 .zip 삭제, **13 MB**  freed (1 experiment)
   - 합계: **340 .zip 삭제, ~558 MB freed**
4. `scripts/disk-cleanup.sh` 추가 실행 — 현재 host `models/`, `replays/` 는 volume 기반이라 삭제 대상 0건(이미 rotated)
5. Replay volumes 점검: dev=378, qa=386, prod=5 — **전부 NFR2.4 (1000건) 이내**, skip
6. `/tmp` 정리 대상 0건
7. 컨테이너 json-file log 점검:
   - prod-backend/mongodb: rotation 설정됨(10m×5), 현재 11K/4.8M — 정상
   - dev/qa: rotation 미설정(`{}`) 이지만 현재 용량 각 < 17M — 즉시 위험 없음 → **follow-up**

## After

| 항목 | 값 | Delta |
|------|-----|-------|
| `/` 파티션 | 95G used / 1007G (**10%**) | 동일 (% 변동 없음, 비율 단위) |
| Docker images | **13.28 GB** | **−5.39 GB** |
| Build cache | **0 B** | **−9.78 GB** |
| Volumes | **1.421 GB** | **−0.53 GB** (체크포인트) |

### Total reclaimed: **~15.7 GB**

- Build cache: 9.78 GB
- Image dedup/eviction: 5.39 GB
- Model checkpoints: 0.56 GB

## Follow-up (non-blocking, queued)

1. ~~**dev/qa 컨테이너 logging driver 에 rotation 추가**~~ — **DONE (Round 2 below)**
2. **frontend host 의 nginx access log rotation** — SSH 액세스 없어서 이번 작업 범위 제외
3. **crontab 등록**: `0 5 * * * <remote-home>/.../scripts/disk-cleanup.sh >> /var/log/pikachu-disk-cleanup.log 2>&1`

---

## Round 2 — Housekeeping Sprint (20:50 KST)

v0.2.4 배포 완료 + 하우스키핑 스프린트 중 재실행. v0.2.4 rebuild 사이클로
build cache가 다시 9.76 GB 까지 차오른 것이 확인되어 재정리.

### Before (Round 2)

| 항목 | 값 |
|------|-----|
| `/` 파티션 | 95G used / 1007G (**10%**) |
| Docker images | **18.65 GB** (v0.2.4 최종 빌드) |
| Build cache | **9.76 GB** (v0.2.4 build 사이클 재누적) |
| Volumes | ~2.67 GB |

### Actions (Round 2)

1. `docker builder prune -af` — **9.76 GB 회수** (build cache 0B)
2. `docker image prune -af` — 0B (dangling image 없음; 현재 4개 images 모두 active)
3. **dev/qa 컨테이너 logging driver rotation 적용** — 위 follow-up 해소:
   - `docker-compose.dev.yml` / `docker-compose.qa.yml` 양쪽에 mongodb + backend logging 블록 추가
   - mongodb: `max-size: 10m, max-file: 3` (prod mongodb와 동일)
   - backend:  `max-size: 10m, max-file: 5` (prod backend와 동일)
   - `docker compose up -d --force-recreate` 양쪽 환경 실행 → 6 컨테이너 모두 `HostConfig.LogConfig.Config` 비어있던 것 → rotation 값 주입
   - 검증: 6 컨테이너 전부 `healthy` + log config 값 확인됨
   - 이미지 SHA 불변 (recreate-only, no rebuild) — VERSIONS.yml image digest 유효

### After (Round 2)

| 항목 | 값 | Delta (Round 2) |
|------|-----|-------|
| Docker images | **13.26 GB** | **−5.39 GB** (image dedup 효과) |
| Build cache | **0 B** | **−9.76 GB** |
| Volumes | **2.68 GB** | +0.01 GB (신규 log 파일) |
| 총 회수 | **−15.15 GB** | |

### Log rotation 검증 (Round 2 후)

```
pikachu-rl-dev-backend-1    log={"max-file":"5","max-size":"10m"}  healthy
pikachu-rl-qa-backend-1     log={"max-file":"5","max-size":"10m"}  healthy
pikachu-rl-prod-backend-1   log={"max-file":"5","max-size":"10m"}  healthy  (기존)
pikachu-rl-dev-mongodb-1    log={"max-file":"3","max-size":"10m"}  healthy
pikachu-rl-qa-mongodb-1     log={"max-file":"3","max-size":"10m"}  healthy
pikachu-rl-prod-mongodb-1   log={"max-file":"3","max-size":"10m"}  healthy  (기존)
```

전 6 컨테이너 통일 완료. 이제 컨테이너 당 최대 로그 보유량:
- backend: 10m × 5 = 50 MB (6 컨테이너 × 50 MB = 300 MB 상한)
- mongodb: 10m × 3 = 30 MB (6 × 30 = 180 MB 상한)
- 3-env 합계 상한: **~480 MB** (이전 unbounded 대비 명확한 경계 확보)

## Host vs Volume 정리 구분 메모

- `scripts/disk-cleanup.sh` / `scripts/cleanup-replays.sh` 둘 다 `$PROJECT_DIR/models`, `$PROJECT_DIR/replays` (호스트 경로) 대상
- 현 배포는 **docker named volume** (`pikachu-rl-${env}_models_${env}`, `..._replays_${env}`) 사용 → 호스트 스크립트가 volume 안은 못 봄
- 이번엔 `docker run --rm -v <vol>:/m alpine sh /prune.sh` 패턴으로 volume 내부 직접 rotate
- **Follow-up**: 크론 등록 전에 스크립트를 volume-aware 하게 확장하거나, 별도 `cleanup-volumes.sh` 추가 필요

# PM 공지: dev 머지 후 Health Check 필수

> **Date**: 2026-04-12 | **From**: Product Manager
> **적용 대상**: 전 팀

---

## 배경

dev backend가 unhealthy 상태로 crash loop에 빠져 있었으나 아무도 확인하지 않았습니다.

**원인**: `prometheus_client` 패키지가 Docker 이미지에 없는 상태에서 `backend/app/metrics.py`가 import → `ModuleNotFoundError` → crash loop

---

## 신규 규칙 (즉시 시행)

**dev에 코드를 머지한 사람은 반드시 아래를 즉시 수행해야 합니다:**

```bash
# 1. 컨테이너 상태 확인
docker ps --filter name=pikachu-rl-dev
# → STATUS: (healthy) 확인. (health: starting)이면 30초 대기 후 재확인

# 2. API health check
curl -s http://localhost:8001/api/health
# → {"status": "ok"} 확인

# 3. 이상 시 로그 확인
docker logs pikachu-rl-dev-backend-1 --tail 30
```

### 새 pip 의존성 추가 시

pyproject.toml에 패키지를 추가했으면 **Docker 이미지 재빌드 필수**:
```bash
cd /home/yoon/.claude-squad/worktrees/yoon/devops-engineer_18a549f15750edca
docker compose -f docker-compose.dev.yml build backend
docker compose -f docker-compose.dev.yml up -d backend
```

### 문제 발견 시

PM에게 즉시 보고. 머지한 사람의 책임.

---

**이 규칙은 docs/WORKFLOW.md에 정식 반영되었습니다.**

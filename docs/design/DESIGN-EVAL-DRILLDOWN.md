# Evaluation — Two-Level Drill-Down Spec

> **SUPERSEDED BY `docs/DESIGN-RUNS-MERGED.md`** (2026-04-18). The standalone `/evaluation` surface is folded into the unified `/runs` nav with an `Evaluation` sub-tab. Kept for reference; §2b (checkpoint table) + §2c (eval runner panel) are still reused by the `Evaluation` sub-tab.

Mirror history drill-down: **Training runs → Checkpoints of one run → Run evaluation**. Replaces current flat checkpoint list. Depends on `DESIGN-TRAINING-TITLE.md` + `DESIGN-HISTORY-DRILLDOWN.md`.

## 0. Routes

- `/evaluation` — L1: training run list (eval lens).
- `/evaluation/{title}` — L2: checkpoints + eval runner.
- History run header `평가하기` button deep-links to L2.

## 1. L1 — Training run list (eval variant)

Reuses history-L1 component with columns retuned for eval intent:

| Col | Content |
|-----|---------|
| Title | primary, click target |
| Started | `YYYY-MM-DD HH:mm KST` mono muted |
| Checkpoints | count (`12`); `0` greys row + tooltip `체크포인트 없음` |
| Last eval | relative (`3시간 전`) + Elo Δ badge (`Δ +18`) or `—` |
| Best Elo | `1382` semibold; muted when never evaluated |
| Status | Running / Finished / Stopped chip |

Header search + status multi-select identical to history-L1 (URL `?q=&status=`).

## 2. L2 — Checkpoint list + eval runner

Three regions: run-info header → checkpoint table → eval runner panel.

**2a. Run-info header (single-line desktop)** — breadcrumb `← All Trainings · {title} · exp:<uuid8> · n_envs · bot L{n}` + status chip + run-picker dropdown. h1 = title 22 px.

**2b. Checkpoint table** — cols: single-select radio (eval target) / Step / Saved at (KST) / Size / Evals count (hover shows Elo spark) / Best Elo / Filename (mono 11 px ellipsis). Default sort `Step desc`, re-sortable, URL-persisted. Row click = radio select, row highlight `--color-accent-dim` + 2 px accent left-bar. Multi-select checkboxes for bulk delete live in a **separate column**, gated by Delete Mode — see `DESIGN-BULK-DELETE.md`.

**2c. Eval runner panel (sticky bottom)** — label `선택된 체크포인트: step 200,000` (or `체크포인트를 선택하세요`), `bot_level` select (L1–L5, persisted URL + localStorage per `DESIGN-TRAINING-TITLE.md §8`), `n_games` input (default 20, range 1–200), `평가 실행` primary button (disabled until checkpoint selected / in-flight eval). In-flight shows inline progress `7 / 20 games`; post-run toast `평가 완료: Elo 1382 (Δ +18)`.

## 3. Empty states

- L1 no runs → `학습 내역이 없습니다. 학습을 먼저 시작하세요.` + CTA `학습 시작`.
- L2 no checkpoints → `이 학습의 체크포인트가 아직 없습니다. 학습이 진행되면 자동 저장됩니다.` (Running → 3-dot loader).
- L2 all deleted → `모든 체크포인트가 삭제되었습니다.`

## 4. Backend endpoints (required)

- `GET /api/training/runs?view=eval` — adds `checkpoint_count`, `last_eval_at`, `best_elo`.
- `GET /api/models?title=<title>` → `[{step, saved_at, size_bytes, filename, eval_count, best_elo}]`, step desc server-side.
- `POST /api/evaluation/run` — body `{experiment_id, step, bot_level, n_games}`, progress via existing WS `eval:progress`.
- `DELETE /api/models` — body `{experiment_id, steps: number[]}` (bulk delete).
- Authoritative key everywhere = `experiment_id`; title resolved to UUID server-side.

## 5. Responsive

- ≥1024 px: as above.
- 768–1023 px: L2 table drops `Filename` (shown on row expand); eval panel collapses `bot_level + n_games` to one row.
- <768 px: L1 → card stack (same pattern as history). L2 → card list (Step as primary 16 px, Best Elo + Saved at under). Eval panel = fixed bottom sheet 80 px with full-width `평가 실행`. Bulk-delete checkboxes toggle on only in Delete Mode.

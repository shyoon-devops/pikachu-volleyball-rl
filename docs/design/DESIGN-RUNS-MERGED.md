# Training Runs — Unified Nav & Sub-Tab Spec

Collapse the two separate top-level entries (`History`, `Evaluation`) into a single **Training Runs** surface. A training run is the durable unit of work — game history and evaluations are two views of the *same* run — so it should live in one place, not two. This supersedes `DESIGN-HISTORY-DRILLDOWN.md` and `DESIGN-EVAL-DRILLDOWN.md` for the L1 list and adds sub-tabs on the detail page.

## 1. Top nav

Before: `Dashboard | Training | History | Evaluation | Replay | Settings`
After:  `Dashboard | Training | Training Runs | Replay | Settings`

- Active link visual unchanged (existing accent underline).
- `Training Runs` copy: bold weight; trailing numeric badge shows `Running` runs count when > 0 (e.g. `Training Runs · 1`) with `--color-warning` chip, pulse 1.2 s.
- `Training` remains the *start-a-new-run* launcher; `Training Runs` is where everything you've started lives.

## 2. Route surface

- `/runs` — L1 list (merged).
- `/runs/{title}` — L2 detail with sub-tabs (`?tab=overview|games|eval`).
- `/runs/{title}` with no `tab=` → default `overview`.
- Legacy routes `/history`, `/history/{title}`, `/evaluation`, `/evaluation/{title}` → **301 redirect**:
  - `/history` → `/runs`
  - `/history/{title}` → `/runs/{title}?tab=games`
  - `/evaluation` → `/runs`
  - `/evaluation/{title}` → `/runs/{title}?tab=eval`
  - Query params preserved where meaningful (e.g. `?env=3` survives on `games` redirect).

## 3. L1 — Unified runs list (`/runs`)

Reuses history-L1 table with columns merged from both prior specs. Desktop (≥1024 px): Title (click target, search-highlight) · Started (KST mono muted) · Status chip · Step range · Games (count + 20 px sparkline) · Win rate (`%` + 40 px bar) · Checkpoints (count, `0` muted) · Last eval (relative + Elo Δ badge) · Best Elo.

- Row click → `/runs/{title}` on default `overview` tab.
- Width < 1440 px → `Games` + `Checkpoints` collapse to dual-badge cell `N games / M ckpt`.
- Header filters: `제목 검색` (200 ms debounce, substring match + highlight) · `Status` multi-select · date range. URL `?q=&status=running,finished&sort=recent`.
- Empty: `학습 내역이 없습니다. 새 학습을 시작하면 여기에 나타납니다.` + CTA `학습 시작` → `/training`.

## 4. L2 — Run detail with sub-tabs (`/runs/{title}`)

### 4a. Page header (above tab bar, shared across all sub-tabs)

- Breadcrumb: `← Training Runs · {title}` (mono 12 px, first segment linked).
- h1 title (28 px semibold) + status chip + copy-title icon + `⋯` overflow menu (Stop / Delete / Export).
- Meta row: `exp:<uuid8> · started KST · duration · n_envs · bot L{n}` (mono 11 px muted).
- Run-picker dropdown (type-ahead) at far right — switches to another run without going back to L1.

### 4b. Sub-tab bar

- Horizontal tab strip directly under header. 3 tabs: `Overview` · `Games` · `Evaluation`.
- Active tab: 2 px `--color-accent` bottom border, text `--color-text-primary`, 13 px semibold.
- Inactive: `--color-text-secondary`, hover `--color-text-primary` + `--color-border-strong` underline (120 ms ease).
- Tab click updates URL `?tab=…` **without full route change** (so scroll / header state preserved); back-button-friendly via `history.pushState`.
- Keyboard: `1/2/3` number keys jump tabs when detail page focused; `←/→` while tab strip focused.
- `aria-role="tablist"` / per-tab `role="tab"` / panels `role="tabpanel"` + `aria-labelledby`.

### 4c. `Overview` (default)

Run info summary card (started / duration / status / n_envs / bot L / exp_id / total timesteps / current step) + wrapped hyperparam chip row (`lr`, `γ`, `clip`, `ent`, `n_steps`, `gae λ`, `n_epochs` + `More ▸`) + live mini-progress bar & reward sparkline when Running + quick-stats row (Games · Win rate · Avg rally · Checkpoints · Best Elo, 18 px semibold). No `평가 실행` here.

### 4d. `Games`

Reuses unified game list (per former `DESIGN-HISTORY-DRILLDOWN.md §2b`) minus the Title column. Env + date filters + sort survive under URL namespace `games.` (`?tab=games&games.env=3&games.sort=recent`); per-env mini win-rate badge row above table.

### 4e. `Evaluation`

Full content from former `DESIGN-EVAL-DRILLDOWN.md §2b + §2c`: checkpoint table (single-select eval-target radio, step-desc default, bulk-delete checkboxes gated by Delete Mode per `DESIGN-BULK-DELETE.md`) + sticky bottom eval runner panel (`bot_level`, `n_games`, `평가 실행`). URL namespace `eval.` (`?tab=eval&eval.step=200000&eval.lvl=3`). `평가 실행` lives here, nowhere else.

## 5. Empty states per sub-tab

- Overview: if status Running and no telemetry yet → `지표 수집 중…` with 3-dot loader.
- Games tab: `이 학습에는 아직 기록된 게임이 없습니다.` (+ `첫 게임은 곧 기록됩니다…` when Running).
- Evaluation tab: `이 학습의 체크포인트가 아직 없습니다. 학습이 진행되면 자동 저장됩니다.` / after bulk delete all → `모든 체크포인트가 삭제되었습니다.`

## 6. Responsive

- ≥1024 px: L1 7-col table (or 8 with dual-badge cluster); L2 header single-line; tab strip inline.
- 768–1023 px: L1 drops `Step range` + `Avg rally` (hover reveals); L2 header meta wraps to second line; tab strip stays inline.
- <768 px: L1 → card stack (Title + status chip / started · steps / Games + WR bar / Checkpoints + Best Elo). L2 header collapses meta under h1 (22 px); tab strip becomes **horizontal scroll snap** with edge fade (3 tabs fit on most phones but preserves room for future tabs); sub-tab content follows existing per-spec mobile rules (games = stacked rows; eval = card list + bottom-sheet runner).

## 7. Run Evaluation button — single home

- Only surfaces on `Evaluation` sub-tab (§4e), exactly once.
- All other surfaces (Dashboard, Overview tab, L1 list, L2 header `⋯` menu) instead link to the Evaluation tab via `navigate('/runs/{title}?tab=eval')` — keeps intent discoverable without duplicating the primary action. Prevents the accidental-start pattern of "Run Evaluation" buttons floating on random pages.

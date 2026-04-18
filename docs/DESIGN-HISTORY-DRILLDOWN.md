# History — Two-Level Drill-Down Spec

> **SUPERSEDED BY `docs/DESIGN-RUNS-MERGED.md`** (2026-04-18). The standalone `/history` surface is folded into the unified `/runs` nav with a `Games` sub-tab. Kept for reference; §2b (unified game list) is still reused by the `Games` sub-tab.

Restructure the History surface from a flat game list into **Training run list → per-training game list**. Depends on the Training Title spec (`docs/DESIGN-TRAINING-TITLE.md`).

## 0. Routes

- `/history` — level-1: list of training runs.
- `/history/{title}` — level-2: games of that run. `title` is URL-encoded; if two runs ever collide (shouldn't post-uniqueness), resolve by most recent then show a disambiguation banner.
- Lateral move to other runs without going back: header dropdown (see §2).
- Deep links from Recent Games dashboard jump straight to level-2.

## 1. Level-1 — Training run list

Choice: **table on desktop, card stack on mobile**. Table gives clean column comparison for power users; cards suit narrow widths. Single component emits both via CSS grid breakpoint.

Row (table) / card fields:

| Col | Content | Style |
|-----|---------|-------|
| Title | primary, 14 px semibold `--color-text-primary`; click target | left-aligned |
| Started | `YYYY-MM-DD HH:mm KST`, 11 px mono muted | right-aligned |
| Status | `Running` / `Finished` / `Stopped` chip | 24 px chip |
| Step range | `0 – 200,000` mono 11 px | tabular-nums |
| Games | count + sparkline (20 px tall, last 50 games win/loss) | end-aligned |
| Win rate | `62.4%` 13 px semibold; bar 40 px under (`--color-success` fill) | right-aligned |
| Avg rally | `8.3` mono 11 px | right-aligned |

- Row hover: `--color-bg-hover`, accent left-border 2 px slides in (120 ms ease). Entire row clickable.
- Active run status chip: `--color-warning` bg pulse 1.2 s + `Running` text.
- Stopped / crashed runs: `--color-danger` chip `Stopped`.
- Sort headers: Started desc default, clickable to re-sort; persisted in URL `?sort=winrate.desc`.

Empty state: centered illustration + `학습 내역이 없습니다. 새 학습을 시작하면 여기에 나타납니다.` + primary CTA `학습 시작`.

## 2. Level-2 — Run detail (games of one training)

Top region = **run info header**, bottom region = **existing unified game list** (reused, now pre-filtered to this run).

### 2a. Header

- Breadcrumb row: `All Trainings › {title}` (mono 12 px; first segment a link, accent colour). Beside breadcrumb: compact run-picker dropdown (chevron icon, mono 12 px) — keyboard-accessible, type-ahead; lets user switch to another run without going back.
- Title block: h1 28 px semibold, right of it a status chip + copy-title icon.
- Meta row: `started_at (KST) · duration · n_envs · bot L{n} · experiment:<uuid8>`; mono 11 px muted, separators `·`.
- Hyperparams summary: horizontal chip row — `lr 3e-4`, `γ 0.99`, `clip 0.2`, `ent 0.01`, `steps 2,048` (collapsed `More ▸` reveals the rest). Chips reuse `--color-bg-elevated` + 11 px mono.
- Live metrics mini-bar (only if status = Running): current step / total + thin progress fill.

### 2b. Game list

- Existing unified-list component is reused **minus** the Title column (redundant within this scope).
- Env filter chip bar stays; sort persists in URL `?env=3&sort=recent`.
- Per-env mini win-rate badges collapse into one row above the table.

### 2c. Empty

- Run exists but 0 games yet → `이 학습에는 아직 기록된 게임이 없습니다.` (14 px muted, centered card). If status = Running, append secondary line `첫 게임은 곧 기록됩니다…` with 3-dot loader.

## 3. Navigation

- Level-1 → Level-2: on row click, View transitions (`ViewTransition` API where supported; CSS fallback) fade out list 120 ms, fade in detail 180 ms. Back uses browser back — header breadcrumb `All Trainings` is also the anchor. No horizontal slide (avoids layout shift).
- Respect `prefers-reduced-motion` → cut transitions to 0 ms.
- Back preserves level-1 scroll position + filters (stored in `sessionStorage.history.listState`).

## 4. Empty states (both levels)

- Level-1 empty: covered in §1.
- Level-2 empty (run has 0 games): covered in §2c.
- Level-1 search returns 0: `'{query}' 검색 결과가 없습니다.` with `검색 지우기` link.
- Level-2 env filter returns 0: `선택된 Env에서 기록된 게임이 없습니다.` with `전체 Env 보기` link.

## 5. Search / filter

- Level-1 header: left = search input (36 px, placeholder `제목 검색…`, debounce 200 ms, substring match, highlights matched chars in Title cell); right = status multi-select (`Running`/`Finished`/`Stopped`) + date range. All reflect in URL `?q=baseline&status=running,finished`.
- Level-2 header: inherits level-1's existing env/date filters, removes title-related ones (scope collapsed to one run).

## 6. Responsive

- ≥1024 px: level-1 = 7-column table, 56 px row height.
- 768 – 1023 px: drop `Avg rally` column; win-rate bar hidden behind hover.
- <768 px: **card stack**. Each card = full-width, 12 px padding, radius 10 px, surface `--color-bg-card`. Card layout:
  - Row 1: Title (16 px semibold) + status chip right-aligned.
  - Row 2: started_at (mono 11 px) · step range.
  - Row 3: Games + Win rate bar full-width.
  - Tap target = entire card. Sparkline hidden on mobile.
- Level-2 reuses existing responsive rules from unified list; header compacts (hyperparam chips wrap to second row, run-picker dropdown becomes full-width).

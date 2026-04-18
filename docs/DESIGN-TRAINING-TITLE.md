# Training Title — UX & Propagation Spec

Introduce a user-authored **Title** field as the human-friendly identifier for a training run. Internal `experiment_id` (UUID) stays as the stable backend ID; Title is the user-facing overlay.

## 0. Contract

- Title is **required** to start training. Empty, whitespace-only, or duplicate titles → submit disabled.
- Server-side truth: `training_run.title` stored alongside `experiment_id`. Lookup uses UUID; display uses title.
- Uniqueness scope: per-user (for now: global across the single-user dev setup).
- Max length 60; charset: any Unicode printable + space, but **file-safe slug** (`[a-z0-9-_]`, fallback) derived server-side for filenames.

## 1. HyperparamForm — Title input (top of form)

- Position: **above** the Basic group, full-row (no 2-col split). Visually heavier than other fields.
- Control: `<input type="text" maxlength="60">`, 36 px tall, mono 13 px, `--color-bg-input`, 1 px `--color-border`, radius 6 px, 12 px h-padding.
- Label: `Title` (mono 12 px, semibold, `--color-text-primary`) + red `*` (`--color-danger`).
- Placeholder: `예: run-baseline-20260418`.
- Hint line: `이 학습을 구분할 이름. 모델 파일명/평가 기록에도 사용됩니다.` (11 px `--color-text-secondary`).
- Live counter right-aligned below input: `12 / 60` (mono 11 px, `--color-text-muted`; turns `--color-danger` at 60).
- Debounced (300 ms) uniqueness check → `GET /api/training/titles?q=<value>` (separate BE ticket). Pending = spinner badge; conflict = red ring + inline message.
- Validation messages (inline, 11 px, `--color-danger`):
  - empty/whitespace → `제목 필수`
  - length > 60 → `최대 60자`
  - duplicate → `이미 존재하는 제목` + faint hint of prior run's date
- Submit (`Start Training`) button `disabled` while title invalid OR any other field invalid.

## 2. Recent Games — Title column

- Insert between `Date` and `Env`: `Title` column, min-width 140 px desktop, truncates with ellipsis at cell edge.
- Cell = anchor to training detail route; hover reveals full title as `title` attr tooltip.
- Mobile (<768 px): Title becomes the primary line; Date + bot level collapse under it (stacked cell layout).

## 3. History unified list — Title column + filter

- Add `Title` column (same styling as Recent Games cell).
- Filter bar: new **Title** combobox between existing Env and Date filters. Autocomplete against `/api/training/titles`. Supports substring match. URL persistence: `?title=run-baseline`.
- Empty-state text updated: `'my-run-2' 조건과 일치하는 학습이 없습니다.`

## 4. Training detail view — prominent title

- Page header: h1 title (24 px semibold, `--color-text-primary`) + sub-row `experiment · <uuid-first-8> · 2026-04-18 12:34 KST` (mono 11 px, `--color-text-muted`).
- Breadcrumb: `History › {title}`.
- Copy icon on hover (ghost button right of title) copies the title string.

## 5. Evaluation records — linked title

- Each evaluation row/card now shows source training as chip: `학습: my-run-1` — 24 px chip, `--color-bg-elevated` bg, mono 11 px, click-through to training detail.
- Evaluation creation dialog: `training_id` select becomes title-first label (`my-run-1 (exp:a3f9…)`).
- Eval stored shape adds `training_title` (denormalised snapshot so later title renames don't break history; primary FK stays `experiment_id`).

## 6. Model filename prefix

- New convention: `{slug}__{exp8}__{step}.zip` — e.g. `run-baseline-20260418__a3f9bc21__200000.zip`.
- `slug` = server-side sanitise: lowercase → replace `[^a-z0-9]+` with `-`, trim leading/trailing `-`, truncate to 40 chars. Empty slug → fallback `run`.
- `exp8` = first 8 chars of `experiment_id` UUID — guarantees collision-safety even for identical slugs across users.
- Backward compat: pre-existing `{exp}_{step}.zip` files still resolvable via DB join on `experiment_id`; migration job renames lazily on next checkpoint.

## 7. Evaluation history — KST timestamp column

- New column `평가 시간` between `Title` and `Elo`: `YYYY-MM-DD HH:mm KST` (mono 11 px), right-aligned numeric.
- Sortable desc by default. Tooltip on hover shows ISO + relative (`3시간 전`).
- Mobile: column shrinks to `MM-DD HH:mm` form.

## 8. Evaluation refresh — bot_level retention

- Bug: refresh resets `bot_level` selector to L1. Root cause: no persistence.
- Spec: persist selected `bot_level` in `localStorage.eval.botLevel` + URL query `?lvl=3`. URL wins if both present (deep-linkable).
- Other filters (opponent type, date range) get the same treatment in one pass.
- Restore order on mount: URL → localStorage → default L1.

## Responsive + a11y summary

- All new inputs have visible focus ring (2 px `--color-accent` offset 1 px) and `aria-describedby` pointing at hint/error.
- Column additions reflow: desktop adds columns, mobile stacks cells (CSS grid `display: block` on `<td>` at <768 px).
- Title input announces `aria-invalid` + `aria-errormessage` on validation fail. Counter uses `aria-live="polite"`.

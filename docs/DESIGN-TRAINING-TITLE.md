# Training Title — UX & Propagation Spec

Introduce a user-authored **Title** field as the human-friendly identifier for a training run. Internal `experiment_id` (UUID) stays as the stable backend ID; Title is the user-facing overlay.

## 0. Contract

- Title is **optional** at submit. Empty/whitespace-only → server (preferred) or FE auto-generates a unique title before persisting.
- Auto-generated format (primary): `run-{adj}-{noun}-{4hex}` — e.g. `run-bold-falcon-a3f2`. Adj/noun pools ≥50 each, lowercase ASCII.
- Auto-generated format (fallback, when word pool unavailable): `run-{YYYYMMDDHHmm}-{4hex}` — e.g. `run-202604181834-7c19`.
- Uniqueness is still enforced: on collision, regenerate (max 5 retries, then append extra `-{4hex}`).
- Duplicate user-typed titles remain a hard block (see §1).
- Server-side truth: `training_run.title` stored alongside `experiment_id`. Lookup uses UUID; display uses title.
- Uniqueness scope: per-user (for now: global across the single-user dev setup).
- Max length 60; charset: any Unicode printable + space, but **file-safe slug** (`[a-z0-9-_]`, fallback) derived server-side for filenames.
- Generation owner: **BE** (so the authoritative ID lives server-side); BE echoes final title in `training:start` response. FE does **not** pre-fill the input on empty — that would mask the intent.

## 1. HyperparamForm — Title input (top of form)

- Position: **above** the Basic group, full-row (no 2-col split). Visually heavier than other fields.
- Control: `<input type="text" maxlength="60">`, 36 px tall, mono 13 px, `--color-bg-input`, 1 px `--color-border`, radius 6 px, 12 px h-padding.
- Label: `Title` (mono 12 px, semibold, `--color-text-primary`). **No `*`** — field is optional.
- Placeholder stays: `예: my-run-baseline` (hint that user can set their own).
- Hint line: `비워두면 자동으로 이름이 생성됩니다. 원하는 이름이 있다면 직접 입력.` (11 px `--color-text-secondary`).
- Live counter right-aligned below input: `12 / 60` (mono 11 px, `--color-text-muted`; turns `--color-danger` at 60). Hidden while input is empty.
- Debounced (300 ms) uniqueness check runs **only when input is non-empty** → `GET /api/training/titles?q=<value>`. Pending = spinner badge; conflict = red ring + inline message.
- Validation messages (inline, 11 px, `--color-danger`), applied **only to user-typed values**:
  - whitespace-only typed → treated as empty (auto-gen path, no error)
  - length > 60 → `최대 60자`
  - duplicate (user-typed) → `이미 존재하는 제목` + faint hint of prior run's date (hard block)
- Submit (`Start Training`) button disabled **only** when an explicitly-typed title is invalid (too long / duplicate) or any other field invalid. Empty input → enabled.
- Post-submit UX: once BE echoes the final title in `training:start` response, toast `학습 시작: {title}` so user sees the auto-generated name (or confirms their own). Detail view uses the final title from that point on.

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

# Batch Tabs — Parallel Env Viewer Spec

Show `n_envs` (default 8, range 1–16) concurrent training envs; user picks one to stream on the game canvas.

## 1. Layout

- **Placement**: directly beneath `GameCanvas` (canvas aspect 432/304). Full-width block, same horizontal bounds as canvas container. Not a sidebar — maintains the arcade-framed focal point.
- **Wrap layout** (revised): `display: flex; flex-wrap: wrap; justify-content: flex-start`. No horizontal scroll. Rows grow downward as `n_envs` increases.
- **Max tabs per row**: 4 desktop (≥1024 px) → 3 tablet (≥768 px) → 2 mobile (<768 px). Achieved via `flex-basis: calc((100% - (cols - 1) * gap) / cols)` per breakpoint.
- **Row height (single row)**: 56 px desktop, 48 px tablet, 40 px mobile. Multi-row keeps same per-chip height; row gap 8 px.
- **Gap between tabs (column)**: 8 px desktop, 6 px mobile. Outer padding 12 px horizontal / 10 px vertical.
- **Container**: same card surface as dashboard (`--color-bg-card`, `--color-border`, 12 px radius). No `max-height` / no scroll — card grows with content.

## 2. Tab visual

Each tab is a 2-row chip (`min-width: 72 px`, fixed — chip never shrinks below this even inside flex):

- Row 1: `ENV 0` … `ENV 7` (mono 11px, `--color-text-secondary`, letter-spacing 0.08em).
- Row 2: live score. **Width-stable rules**: `font-variant-numeric: tabular-nums`, `white-space: nowrap`, `overflow: hidden`, `text-overflow: ellipsis`. Digits don't re-layout when scores tick 9→10 etc. Updates from WS `training:env_state` @ ≤10 Hz.
- **Score format**: `NN : NN`, two-digit max per side (baseline cap `15:15` — game end at 15). If a side ever exceeds 99 (shouldn't happen), ellipsis clips; fallback compact form `99+:99+` for theoretical overruns.
- Right-edge status dot (8×8, 4 px margin):
  - in-progress → `--color-warning` (#fbbf24), soft pulse 1.2 s
  - win (just scored point) → `--color-success` flash 400 ms then return to warning
  - game end / lose → `--color-danger`, static
- **Active tab** (currently mirrored on canvas): 2 px `--color-accent` (#ffd700) bottom bar + `--color-accent-dim` background + `--color-text-primary` row 1.
- **Inactive**: `--color-bg-elevated` background, `--color-border` 1 px.

## 3. Interaction

- Hover (inactive): background → `--color-bg-hover`, border → `--color-border-strong`, 120 ms ease.
- Click: canvas crossfades (opacity 180 ms) and new env frame stream subscribes. No layout shift.
- Keyboard: `←` / `→` cycle previous/next; `1`–`8` jump to `ENV 0`–`ENV 7`. Focus ring 2 px `--color-accent` offset 2 px.
- ARIA: `role="tablist"`, each tab `role="tab"` + `aria-selected`, canvas has `role="tabpanel"` + `aria-labelledby`.

## 4. Color system

- Reuses existing tokens — **no new palette**. Warning/Success/Danger for state dot; Pikachu-yellow accent for active; chart-purple (`#a855f7`) reserved as "recently switched-to" subtle halo (600 ms fade) so user tracks their own click.
- Dark-theme only (project baseline). Contrast: score text ≥ 7:1 on card.

## 5. Responsive (wrap grid)

- ≥1024 px (desktop): **4 per row**. 8 envs → 2 rows; 16 envs → 4 rows. Chip flex-basis `calc((100% - 3*8px) / 4)`.
- ≥768 px (tablet): **3 per row**. 8 envs → 3 rows (last row has 2 left-aligned); chip basis `calc((100% - 2*8px) / 3)`.
- <768 px (mobile, incl. 375 px): **2 per row**, chip basis `calc((100% - 6px) / 2)`, min-width honored at 72 px (wraps sooner if container narrower). Row gap 6 px.
- **Alignment**: `justify-content: flex-start` so trailing partial row is left-aligned (no stretched-odd-chip artifact). `align-items: stretch` keeps all rows equal height.
- **No scroll, no snap**: vertical growth only. Active tab never needs auto-scroll — always visible.

## 6. History page extensions

- Add `env_id` column to unified Recent Games list: 28 px chip (same ENV token styling but muted — `--color-bg-elevated` + `--color-text-secondary`).
- Filter: existing filter bar gets an `Env` dropdown — options `All` + `ENV 0..N-1` (N from training run metadata). Persist choice in URL query `?env=3`.
- Group-by-env toggle (stretch): folds list into 8 collapsible sections, each with mini win-rate.

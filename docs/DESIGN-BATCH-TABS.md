# Batch Tabs — Parallel Env Viewer Spec

Show `n_envs` (default 8, range 1–16) concurrent training envs; user picks one to stream on the game canvas.

## 1. Layout

- **Placement**: directly beneath `GameCanvas` (canvas aspect 432/304). Full-width row, same horizontal bounds as canvas container. Not a sidebar — maintains the arcade-framed focal point.
- **Strip height**: 56 px desktop, 48 px tablet, 40 px mobile.
- **Gap between tabs**: 8 px desktop, 6 px mobile. Outer padding 12 px horizontal / 8 px vertical.
- **Dynamic count**: CSS grid `repeat(var(--n-envs), minmax(0, 1fr))` ≤ 8 envs; ≥ 9 switch to horizontal scroll strip with snap (see §5).
- **Container**: same card surface as dashboard (`--color-bg-card`, `--color-border`, 12 px radius).

## 2. Tab visual

Each tab is a 2-row chip (`min-width: 72 px`):

- Row 1: `ENV 0` … `ENV 7` (mono 11px, `--color-text-secondary`, letter-spacing 0.08em).
- Row 2: live score `12 : 8` (mono 14px semibold, `--color-text-primary`). Updates from WS `training:env_state` @ ≤10 Hz.
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

## 5. Responsive

- ≥1024 px: 8 tabs fit evenly across ~520 px canvas width. 16 envs would be 32 px per tab = too narrow → overflow-x scroll with snap and right-edge fade mask.
- 768 px: 8 tabs still fit (tab min-width drops to 60 px, hide row 1 letters, keep numeric `0..7`).
- ≤375 px mobile: horizontal scroll strip, 56 px per tab, snap-mandatory, edge-fade; active tab auto-scrolls into view on ← / → or programmatic switch.

## 6. History page extensions

- Add `env_id` column to unified Recent Games list: 28 px chip (same ENV token styling but muted — `--color-bg-elevated` + `--color-text-secondary`).
- Filter: existing filter bar gets an `Env` dropdown — options `All` + `ENV 0..N-1` (N from training run metadata). Persist choice in URL query `?env=3`.
- Group-by-env toggle (stretch): folds list into 8 collapsible sections, each with mini win-rate.

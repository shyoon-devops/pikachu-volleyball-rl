# UpdatingOverlay — PPO Gradient Phase Spec

Transient overlay for the 2–5 s freeze between PPO rollout end and next rollout start. Existing tokens only — **no new colours, fonts, or surfaces**.

## 1. Visual

- Backdrop: `rgba(15, 17, 23, 0.55)` (= `--color-bg-primary` @ 55%) + `backdrop-filter: blur(6px)`.
- Container: centered, 24 px padding, `--color-bg-card` surface, 1 px `--color-border`, radius 12 px, max-width 320 px.
- Primary text: `Updating policy` (16 px semibold, `--color-text-primary`).
- Subtext: `PPO gradient update in progress` (12 px mono, `--color-text-secondary`, 4 px top margin).
- Indicator: 10 × 10 px `--color-accent` pulsing dot beside the title (reuses existing `.dot-pulse` utility — lighter than a spinner and already in the vocabulary).

## 2. Timing

- Detect `now - last_frame_timestamp > 1500 ms` while `training.status === 'running'`. Fade-in 200 ms / fade-out 300 ms (`--ease-out-expo`). Minimum visible 400 ms — if frames resume inside that window, delay fade-out so the overlay can't flash. `prefers-reduced-motion` → cut fades to 0 ms; keep the 400 ms floor.

## 3. Placement + interactivity

- Scope: **GameCanvas only** — absolute over the canvas container, not the whole Dashboard.
- Recent Games, Metrics charts, Training controls, League widget stay fully interactive (Stop / Pause still reachable).
- ARIA `role="status"` + `aria-live="polite"`; announces title once per show, not per frame. Clicks pass through to a no-op (gradient step is not user-cancellable).

## 4. Responsive + dark theme

- Desktop/tablet: container max-width 320 px; mobile (<768 px): `min(80vw, 280px)`, padding 16 px, subtext may wrap 2 lines.
- Dark theme is baseline; inherits `--color-bg-card` if/when light theme lands — no per-theme override.

## 5. Edge cases

- Training `paused`/`stopped` → never shown (guard before heuristic).
- Gap <200 ms → debounce the show trigger so a single slow frame can't flicker.
- Gap >8 s → swap subtext to `This is taking longer than usual…` (same tokens); never escalate to error.
- WS disconnect during show → hide overlay, let the existing connection-lost banner own the state (no stacked blockers).
- `training:league_update` broadcasts are ignored — they don't pause rendering.

## 6. i18n

Strings in the existing locale map. Keys: `training.updating.title` = `"Updating policy"` (en) · `training.updating.subtitle` = `"PPO gradient update in progress"` · `training.updating.slow_hint` = `"This is taking longer than usual…"`. KR/JP stubbed only; English-only acceptable for Sprint 1.

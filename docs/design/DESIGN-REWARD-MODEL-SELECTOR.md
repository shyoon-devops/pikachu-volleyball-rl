# Reward Model Selector — HyperparamForm Spec (v2.x Sprint 2)

UX for the new `reward_model: 'shaped_v1' | 'sparse_v1' | 'learned_shaped_v1'` field defined in `docs/adr/0015-reward-simplification.md`. Existing tokens only — **no new colours, fonts, or surfaces**. Code-free; design only.

## 1. Selector UI

Placement: top of the **Basic** group in `HyperparamForm`, immediately under the Title input and above `total_timesteps`. Reward model is a regime switch (changes what the agent optimises), so it sits before the knobs that tune it. Group label: `Reward model` (mono 12 px, `--color-text-primary`).

Control: **segmented control** (3 cells, full row width, 36 px tall, `--color-bg-card` track, 1 px `--color-border`, radius 6 px). Active cell `--color-bg-input` + 2 px inset `--color-accent` underline. Chosen over a `<select>` because the trade-off matters at choice time and all 3 must be readable at a glance; chosen over a vertical radio group because three short labels fit horizontally and the form is already dense.

## 2. Option copy + tooltip (EN default)

| Option | Cell label | Badge | Tooltip (focus + hover, ≤2 lines) |
|---|---|---|---|
| `shaped_v1` | `Shaped (v1)` | `Recommended` (`--color-accent` chip, 10 px mono) | "9 hand-tuned reward terms. Stable baseline; matches v1.0.0 behaviour." |
| `sparse_v1` | `Sparse` | — | "Win/lose + per-point only. Cleaner objective; **expect slow, unstable early training**." |
| `learned_shaped_v1` | `Learned shaped` | `Experimental` (`--color-warning` chip + ⚠ glyph, 10 px mono) | "Sparse + IRL-learned shaping (Ng-Harada-Russell invariant). Requires demonstrator data." |

Tooltip surface: existing tooltip primitive, `--color-bg-card`, max-width 260 px, 11 px sans, 8 px padding.

## 3. Default + Disabled state

Initial value `shaped_v1` (preserves v1 behaviour). Form-wide disabled pattern (whole HyperparamForm) reused while `training.status === 'running' | 'paused'` — no per-field override here. **Algorithm × reward_model gating**: ADR 0015 fixes no cross-constraint with future SAC, so all 3 × all algorithms are permitted. Rationale: keep the matrix orthogonal until AI explicitly forbids a pair; FE gating without backend gating drifts.

## 4. Recent Games / History / /runs exposure

`RunRecord` rows (Recent Games widget + `/runs` L1 table) gain a **reward-model badge** in the Title cell, right of the title text, 8 px gap. Compact label + token:

- `shaped` → `--color-text-muted` chip on `--color-bg-input` (neutral)
- `sparse` → `--color-text-secondary` chip on `--color-bg-input` (neutral, italic to differentiate)
- `learned` → `--color-warning` chip on `--color-bg-input` (warning; matches Experimental badge)

Chip: 9 px mono uppercase, 2 px v-padding, 6 px h-padding, radius 4 px. In `/runs/{title}` overview sub-tab and the drill-down modal: full label (`Shaped (v1)` / `Sparse` / `Learned shaped`) inline in the metadata block, no chip styling — chips are list-density only.

## 5. i18n

Locale keys (EN default; KR/JP stub-only this sprint):

`training.reward_model.label` · `training.reward_model.options.shaped_v1.label` · `training.reward_model.options.shaped_v1.tooltip` · `training.reward_model.options.sparse_v1.label` · `training.reward_model.options.sparse_v1.tooltip` · `training.reward_model.options.learned_shaped_v1.label` · `training.reward_model.options.learned_shaped_v1.tooltip` · `training.reward_model.recommended_badge` · `training.reward_model.experimental_badge`.

Badge text comes through the locale map — never hard-coded — so KR/JP can swap copy without touching the component.

## 6. Designer review gate

FE implementer (Sprint 2 task) **must reference this file in the PR description**, list the 3 enum values verbatim, and screenshot the segmented control + each tooltip + the badge in `/runs`. Missing screenshot, copy drift, or token substitution (e.g. introducing a new colour for `learned_shaped_v1`) is grounds for revert. Sprint 1's `UpdatingOverlay` shipped with a custom indicator that bypassed designer review — **that is the failure mode this gate exists to prevent**. Designer sign-off is recorded as a PR review approval before merge.

## 7. Accessibility

Segmented control: `role="radiogroup"` + `aria-labelledby` pointing to the `Reward model` label; each cell `role="radio"` + `aria-checked`. Keyboard: ←/→ moves selection, Space/Enter confirms, Tab exits the group. Tooltip surfaces on **focus and hover** (not hover-only) and is referenced via `aria-describedby` so SR users hear the trade-off. The `Experimental` badge carries `aria-label="experimental"` (the ⚠ glyph is `aria-hidden`); the `Recommended` badge carries `aria-label="recommended"`. List badges (§4) reuse the same `aria-label` pattern. `prefers-reduced-motion` → no underline transition, snap state.

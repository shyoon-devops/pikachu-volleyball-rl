# HyperparamForm — Expanded Spec

Expose previously hidden PPO knobs so users can configure experiments directly. Existing 5 fields (`learning_rate`, `n_steps`, `batch_size`, `gamma`, `clip_range`) stay intact.

## 1. New fields

| Field | Default | Range | Step | Hint (KO, ≤1 line) |
|-------|--------:|-------|------|--------------------|
| `total_timesteps` | 2,000,000 | 100,000 – 10,000,000 | 100,000 | 학습 길이 (timestep 수). 클수록 오래, 잘 학습됨 |
| `n_envs` | 8 | 1 – 32 | 1 | 동시에 학습 중인 게임 수 (많을수록 빠르지만 CPU 부담) |
| `n_epochs` | 10 | 1 – 30 | 1 | rollout마다 반복 학습 횟수 (너무 크면 과적합) |
| `ent_coef` | 0.01 | 0.0 – 0.05 | 0.001 | 탐험 강도 (entropy bonus). 높이면 다양한 행동 시도 |
| `gae_lambda` | 0.95 | 0.9 – 1.0 | 0.01 | GAE 평활화 (분산-편향 tradeoff) |

## 2. Layout

Two collapsible groups, expand-on-demand. Basic opens by default.

- **Basic** — `total_timesteps`, `n_envs`, `learning_rate`, `n_steps`, `batch_size`, `bot_level`.
- **Advanced** ▸ (collapsed) — `n_epochs`, `gamma`, `clip_range`, `ent_coef`, `gae_lambda`.

Grid: 2 columns desktop (≥768 px), 1 column mobile. Row gap 12 px, column gap 16 px. Group header = h4 mono 12 px + chevron (rotates 0 → 90 deg on expand, 200 ms ease). Card surface `--color-bg-card`, border `--color-border`, radius 12 px, padding 16 px.

## 3. Field visual

Stacked label + control:

- Label row: `name` (mono 12 px, `--color-text-primary`) · faint meta `(default: 8)` (mono 11 px, `--color-text-muted`, 8 px left margin).
- Below label: `hint` (sans 11 px, `--color-text-secondary`, line-height 1.4). Truncates with ellipsis on mobile < 375 px; full text on focus/hover (`title` attr for tooltip).
- Control: number input 36 px tall, mono 13 px, `--color-bg-input`, 1 px `--color-border`, radius 6 px, 8 px h-padding. Focus ring 2 px `--color-accent` offset 1 px.
- For sliders (`total_timesteps`, `ent_coef`): 32 px track + numeric readout chip on right (mono 12 px, tabular-nums). Slider thumb `--color-accent` 14 px.

## 4. Validation

- `onBlur` + `onChange`: clamp visually via red 1 px border (`--color-danger-border`) when out of range; inline warning below field (`Range: 1–32`, 11 px `--color-danger`). Submit button disabled while any field invalid.
- Non-integer entry in int field → auto-round on blur + toast note.
- Range source: shared const module `HYPERPARAM_SCHEMA` (ties FE form and BE validation).

## 5. Responsive + a11y

- ≥1024 px: 2-col grid, hints always visible.
- 768 – 1023 px: 2-col, hint truncates to 1 line.
- <768 px: 1-col stack, Basic/Advanced groups each full width, hint wraps up to 2 lines.
- Each group `role="group"` + `aria-labelledby`; chevron button `aria-expanded`. Slider fields use native `<input type="range">` with `aria-valuetext` (human-readable: `"2M steps"`).
- Reduced-motion respects `prefers-reduced-motion` — chevron snap, no 200 ms ease.

## 6. Defaults surfacing

Subtle `Reset to defaults` link (text button, `--color-text-secondary`, hover `--color-accent`) at bottom-right of each group — resets only that group's fields to `DEFAULTS` map. Full form reset available on footer.

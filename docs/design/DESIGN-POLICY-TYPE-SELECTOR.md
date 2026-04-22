# Policy Type Selector — HyperparamForm Spec (v2.x Sprint 3)

UX for the new `policy_type: 'mlp_v1' | 'lstm_v1' | 'gru_v1' | 'transformer_v1'` field defined in `docs/adr/0016-lstm-recurrent-policy.md`. Existing tokens only — **no new colours, fonts, or surfaces**. Sibling spec to `DESIGN-REWARD-MODEL-SELECTOR.md`; reuses that pattern verbatim for consistency. Code-free; design only.

## 1. Selector UI

Placement: top of the **Basic** group in `HyperparamForm`, immediately **below the `reward_model` selector** and above `total_timesteps`. Both regime switches sit together so users see "what is optimised × what optimises it" as one decision block. Group label: `Policy type` (mono 12 px, `--color-text-primary`).

Control: **segmented control**, 4 cells, full row width, 36 px tall, `--color-bg-card` track, 1 px `--color-border`, radius 6 px. Active cell `--color-bg-input` + 2 px inset `--color-accent` underline. Identical primitive to `reward_model` — same height, padding, radius, and active treatment so the two stack visually as one regime block. On <768 px the 4-cell row wraps to 2×2 (cell labels stay short enough not to truncate).

## 2. Option copy + state (EN default)

| Option | Cell label | Badge | State | Tooltip (focus + hover, ≤2 lines) |
|---|---|---|---|---|
| `mlp_v1` | `MLP (v1)` | `Recommended` (`--color-accent` chip, 10 px mono) | enabled, default | "Stateless feed-forward policy. Matches v1 / v2 baseline; fastest to train." |
| `lstm_v1` | `LSTM` | — | enabled (Sprint 3) | "Sequence model for rally dynamics. ~3× training cost; better on long rallies." |
| `gru_v1` | `GRU` | `Coming soon` (`--color-border` chip on `--color-bg-card`, 10 px mono, `--color-text-muted`) | **disabled** | "Lighter recurrent variant. Reserved — not yet trainable." |
| `transformer_v1` | `Transformer` | `Coming soon` (same as GRU) | **disabled** | "Attention head over rally history. Reserved — not yet trainable." |

Disabled cells: 50 % opacity, `cursor: not-allowed`, no hover lift, no active underline; tooltip still surfaces on focus + hover.

## 3. Algorithm × policy_type × reward_model matrix

ADR 0016 §8 fixes no cross-field constraint: every `(algorithm, policy_type, reward_model)` triple is permitted at the schema layer. FE **must not** pre-emptively gate combinations — runtime `NotImplementedError` from the trainer is the single source of truth (matches the `reward_model` decision in `DESIGN-REWARD-MODEL-SELECTOR.md` §3). The two reserved policy values (`gru_v1`, `transformer_v1`) are surfaced as `disabled` in the selector — the only client-side restriction.

## 4. Recent Games / History / /runs exposure

`RunRecord` rows (Recent Games widget + `/runs` L1 table) gain a **policy chip** in the Title cell, placed **immediately right of the `reward_model` chip**, 4 px gap, same chip primitive (9 px mono uppercase, 2 px v-padding, 6 px h-padding, radius 4 px, `--color-bg-input` background). Labels:

- `mlp` → `--color-text-muted` (neutral; baseline)
- `lstm` → `--color-accent` text (accent; signals new regime, not a warning)

Reserved values (`gru_v1`/`transformer_v1`) are never persisted on a real run — trainer rejects them at start — so no chip rendering is defined. If one ever appears (data drift), render `--color-danger` text + tooltip "unsupported policy" rather than silently falling back to MLP styling.

## 5. Drilldown modal

`/runs/{title}` overview sub-tab and the run drill-down modal show the **full label** (`MLP (v1)` / `LSTM`) inline in the metadata block, no chip styling — chips are list-density only. Place on the same metadata row as `reward_model` full label, 16 px gap, mono 12 px `--color-text-secondary`, label prefix `Policy:`.

## 6. i18n

Locale keys (EN default; KR/JP stub-only this sprint):

`training.policy_type.label` · `training.policy_type.options.mlp_v1.label` · `training.policy_type.options.mlp_v1.tooltip` · `training.policy_type.options.lstm_v1.label` · `training.policy_type.options.lstm_v1.tooltip` · `training.policy_type.options.gru_v1.label` · `training.policy_type.options.gru_v1.tooltip` · `training.policy_type.options.transformer_v1.label` · `training.policy_type.options.transformer_v1.tooltip` · `training.policy_type.recommended_badge` · `training.policy_type.comingsoon_badge`.

Badge text comes through the locale map — never hard-coded.

## 7. Designer review gate

FE implementer (Sprint 3 task) **must reference this file in the PR description**, list the 4 enum values verbatim (incl. the 2 reserved), and attach 3 screenshots: (a) the selector with all 4 cells visible + 2 disabled, (b) one tooltip on focus (any cell), (c) `/runs` row showing reward_model + policy chips side-by-side. Missing screenshot, copy drift, token substitution, or a chip rendered for a reserved value is grounds for revert. Same gate model as Sprint 2 reward selector; precedent for a new visual without designer sign-off remains the Sprint 1 `UpdatingOverlay` indicator regression. Designer approval recorded as a PR review approval before merge.

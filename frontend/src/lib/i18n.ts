/**
 * Minimal locale map (v2.x Sprint 2, ADR 0015 reward selector).
 *
 * The project had no i18n framework before this commit — hard-coded
 * English strings live throughout. The reward-model spec
 * (DESIGN-REWARD-MODEL-SELECTOR.md §5) requires option labels +
 * tooltips to resolve through a locale map so KR/JP copy can swap
 * without touching components. This module is the smallest thing
 * that satisfies that contract while staying cheap to expand.
 *
 * Lookup rule: `t(key, locale?)` returns the requested locale's
 * string, falling back to `en` when the key is missing from that
 * locale. An empty string in a non-`en` locale is treated as an
 * explicit stub (fall back to `en`).
 *
 * Conventions:
 *   - Keys are dot-delimited scopes: `training.reward_model.label`.
 *   - EN is always the source of truth; KR/JP mirror the shape.
 *   - Add a key in all locales at once — missing keys warn in dev.
 */

type Locale = 'en' | 'ko' | 'ja'

type StringMap = Record<string, string>

const EN: StringMap = {
  'training.reward_model.label': 'Reward model',
  'training.reward_model.options.shaped_v1.label': 'Shaped (v1)',
  'training.reward_model.options.shaped_v1.tooltip':
    '9 hand-tuned reward terms. Stable baseline; matches v1.0.0 behaviour.',
  'training.reward_model.options.sparse_v1.label': 'Sparse',
  'training.reward_model.options.sparse_v1.tooltip':
    'Win/lose + per-point only. Cleaner objective; expect slow, unstable early training.',
  'training.reward_model.options.learned_shaped_v1.label': 'Learned shaped',
  'training.reward_model.options.learned_shaped_v1.tooltip':
    'Sparse + IRL-learned shaping (Ng-Harada-Russell invariant). Requires demonstrator data.',
  'training.reward_model.recommended_badge': 'Recommended',
  'training.reward_model.experimental_badge': 'Experimental',
  /** Compact chip labels for the Recent Games / /runs list
   *  (DESIGN-REWARD-MODEL-SELECTOR.md §4). Lowercase mono. */
  'training.reward_model.chip.shaped_v1': 'shaped',
  'training.reward_model.chip.sparse_v1': 'sparse',
  'training.reward_model.chip.learned_shaped_v1': 'learned',
  // ── Policy-type selector (v2.x Sprint 3,
  // DESIGN-POLICY-TYPE-SELECTOR.md §6). Mirrors reward_model
  // keyspace; GRU + Transformer are reserved this sprint and
  // surface a "Coming soon" badge.
  'training.policy_type.label': 'Policy type',
  'training.policy_type.options.mlp_v1.label': 'MLP (v1)',
  'training.policy_type.options.mlp_v1.tooltip':
    'Stateless feed-forward policy. Matches v1 / v2 baseline; fastest to train.',
  'training.policy_type.options.lstm_v1.label': 'LSTM',
  'training.policy_type.options.lstm_v1.tooltip':
    'Sequence model for rally dynamics. ~3× training cost; better on long rallies.',
  'training.policy_type.options.gru_v1.label': 'GRU',
  'training.policy_type.options.gru_v1.tooltip':
    'Lighter recurrent variant. Reserved — not yet trainable.',
  'training.policy_type.options.transformer_v1.label': 'Transformer',
  'training.policy_type.options.transformer_v1.tooltip':
    'Attention head over rally history. Reserved — not yet trainable.',
  'training.policy_type.recommended_badge': 'Recommended',
  'training.policy_type.comingsoon_badge': 'Coming soon',
  /** Compact chip labels for the list surfaces
   *  (DESIGN-POLICY-TYPE-SELECTOR.md §4). Reserved values never
   *  render a chip on real data; keys exist only as the
   *  data-drift fallback the spec requires. */
  'training.policy_type.chip.mlp_v1': 'mlp',
  'training.policy_type.chip.lstm_v1': 'lstm',
  'training.policy_type.chip.gru_v1': 'gru',
  'training.policy_type.chip.transformer_v1': 'transformer',
}

/**
 * KR + JP stubs (empty strings) so the locale map's shape stays
 * in sync with EN. Translation ships in a follow-up sprint;
 * `t()` falls back to EN for any empty or missing entry.
 */
const KO: StringMap = Object.fromEntries(
  Object.keys(EN).map(k => [k, '']),
)
const JA: StringMap = Object.fromEntries(
  Object.keys(EN).map(k => [k, '']),
)

const LOCALES: Record<Locale, StringMap> = { en: EN, ko: KO, ja: JA }

/** Active UI locale. Hard-coded to `en` today — when a real locale
 *  picker lands, swap this for a reactive source. */
export const activeLocale: Locale = 'en'

export function t(key: string, locale: Locale = activeLocale): string {
  const primary = LOCALES[locale]?.[key]
  if (primary && primary.length > 0) return primary
  const fallback = LOCALES.en[key]
  if (fallback === undefined) {
    // eslint-disable-next-line no-console
    console.warn(`[i18n] missing key: ${key}`)
    return key
  }
  return fallback
}

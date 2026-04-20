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

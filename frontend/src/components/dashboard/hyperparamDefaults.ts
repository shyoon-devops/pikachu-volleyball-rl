import type { Hyperparams } from '../../lib/types'
import { DEFAULT_HYPERPARAMS_EXTENDED } from '../../lib/hyperparams'

/**
 * Default PPO hyperparameters used by the training start form.
 * Re-exported from `lib/hyperparams.ts` so HyperparamForm.tsx stays
 * a pure component file (react-refresh/only-export-components) and
 * the schema module owns the single source of truth for defaults.
 *
 * Values match BE (`WsTrainingStartPayload` on commit cc4daaf3).
 */
export const DEFAULT_HYPERPARAMS: Hyperparams = {
  ...DEFAULT_HYPERPARAMS_EXTENDED,
}

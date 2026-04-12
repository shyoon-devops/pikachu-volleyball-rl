import type { Hyperparams } from '../../lib/types'

/**
 * Default PPO hyperparameters used by the training start form.
 * Lives in its own module so HyperparamForm.tsx stays a pure
 * component file (react-refresh/only-export-components).
 */
export const DEFAULT_HYPERPARAMS: Hyperparams = {
  learning_rate: 3e-4,
  n_steps: 2048,
  batch_size: 64,
  gamma: 0.99,
  clip_range: 0.2,
}

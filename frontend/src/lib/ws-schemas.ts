/**
 * Runtime validation for inbound WebSocket payloads (A6, 2026-04-19).
 *
 * Each schema validates the snake_case wire shape BE broadcasts and
 * transforms it into the camelCase domain type the FE consumes — one
 * step instead of `snakeToCamel<T>()` followed by an unchecked cast.
 * Handlers in `useTrainingState` use `safeParse` + log-and-skip on
 * failure: a malformed payload no longer reaches React state and so
 * cannot crash render.
 *
 * Scope (per A6 audit):
 *   - `training:metrics`   — primary risk: NaN propagation into chart
 *                             + step counter via `Math.max(prev, NaN)`
 *   - `training:status`    — primary risk: invalid `state` string
 *                             silently breaks every CTA-disabled gate
 *   - `training:env_frame` — primary risk: missing `env_id` crashes
 *                             the BatchTabBar map lookup; `frame` is
 *                             passed through and consumed by the
 *                             null-safe canvas path downstream
 *
 * Skipped on purpose:
 *   - `training:frame` — large nested GameState; the canvas already
 *                        renders defensively. Cost > benefit at this
 *                        validation layer.
 *   - `game:result`    — handler patches `timestamp` and table cells
 *                        consume scalar fields directly; the existing
 *                        null-safety covers the same surface a schema
 *                        would.
 *   - `replay:data`    — large frame array; not a useTrainingState
 *                        consumer.
 *   - client→server topics — BE is the validator there.
 */

import { z } from 'zod'
import type { EnvFramePayload, TrainingMetrics, TrainingStatus } from './types'

/**
 * `training:metrics` — every field is required server-side. We accept
 * the snake_case wire payload and emit the camelCase domain type.
 */
export const trainingMetricsSchema = z
  .object({
    step: z.number(),
    episode: z.number(),
    mean_reward: z.number(),
    win_rate: z.number(),
    policy_loss: z.number(),
    value_loss: z.number(),
  })
  .transform(
    (raw): TrainingMetrics => ({
      step: raw.step,
      episode: raw.episode,
      meanReward: raw.mean_reward,
      winRate: raw.win_rate,
      policyLoss: raw.policy_loss,
      valueLoss: raw.value_loss,
    }),
  )

/**
 * `training:status` — partial broadcast (BE sends only the changed
 * fields on transitions). `state` is enum-checked so an unknown value
 * is rejected rather than silently breaking the running/stopped gates.
 */
export const trainingStatusSchema = z
  .object({
    state: z.enum(['running', 'stopped', 'paused']).optional(),
    current_step: z.number().optional(),
    current_episode: z.number().optional(),
    bot_level: z.number().optional(),
    experiment_id: z.string().nullable().optional(),
    title: z.string().nullable().optional(),
  })
  .transform(
    (raw): Partial<TrainingStatus> => ({
      ...(raw.state !== undefined && { state: raw.state }),
      ...(raw.current_step !== undefined && { currentStep: raw.current_step }),
      ...(raw.current_episode !== undefined && { currentEpisode: raw.current_episode }),
      ...(raw.bot_level !== undefined && { botLevel: raw.bot_level }),
      ...(raw.experiment_id !== undefined && { experimentId: raw.experiment_id }),
      ...(raw.title !== undefined && { title: raw.title }),
    }),
  )

/**
 * `training:env_frame` — the chip-rendering scalars (envId, score,
 * stateName, step) are validated. `frame` is passed through as the
 * raw GameState payload because validating the full nested shape
 * would duplicate the engine model with little added safety; the
 * canvas already renders defensively against missing fields.
 */
export const envFramePayloadSchema = z
  .object({
    env_id: z.number().int().min(0),
    frame: z.unknown(),
    score: z.tuple([z.number(), z.number()]),
    state_name: z.string(),
    step: z.number(),
  })
  .transform(
    (raw): EnvFramePayload => ({
      envId: raw.env_id,
      // The frame is consumed by GameCanvas, which performs snake→camel
      // internally on the nested shape via the `snakeToCamel` helper
      // wrapped at the call site (handleEnvFrame). The cast is the same
      // unchecked one we had pre-A6 for this nested object only.
      frame: raw.frame as EnvFramePayload['frame'],
      score: raw.score,
      stateName: raw.state_name,
      step: raw.step,
    }),
  )

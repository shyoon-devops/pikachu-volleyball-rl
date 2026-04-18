import { useState, useEffect, useMemo, useRef } from 'react'
import { Link } from 'react-router-dom'
import { GameCanvas } from '../game/GameCanvas'
import { GameOverlay } from '../game/GameOverlay'
import { BatchTabBar } from '../game/BatchTabBar'
import { ErrorBoundary } from '../ErrorBoundary'
import { MetricsChart } from './MetricsChart'
import { TrainingControls } from './TrainingControls'
import { HyperparamForm } from './HyperparamForm'
import type { TitleValidationState } from './TitleInput'
import { DEFAULT_HYPERPARAMS } from './hyperparamDefaults'
import { DashboardSkeleton } from './DashboardSkeleton'
import { useTrainingState } from '../../hooks/useTrainingState'
import type { Hyperparams } from '../../lib/types'
import {
  formatBotLevel,
  formatRallyCount,
  formatAvgRallyLength,
  formatExperimentIdShort,
  formatEnvId,
  formatEpisode,
} from '../../lib/formatGame'
import { formatKstDateTime } from '../../lib/formatTime'
import {
  HYPERPARAM_SCHEMA,
  HYPERPARAM_WIRE_POSITION,
  validateHyperparam,
  type HyperparamKey,
} from '../../lib/hyperparams'
import './Dashboard.css'

/**
 * Baseline env count before WS data arrives or when the user hasn't
 * yet started a training run. Spec supports 1..16; 8 matches BE's
 * training run default and the HyperparamForm's baseline for n_envs.
 *
 * Effective count is `max(baseline, params.n_envs, observed+1)` —
 * see `effectiveNEnvs` below. The derivation lives FE-side because
 * `/api/training/status` doesn't expose `n_envs` today;
 * [BE-WAITING] adding `"n_envs": self.manager._n_envs` to
 * `backend/app/services/training_service.py::status()` would let us
 * drop the observed-map derivation. For now the observed path
 * catches any count the user configured, including values above the
 * form default (n_envs=16 when the user bumps it).
 */
const DEFAULT_N_ENVS = 8
const MAX_N_ENVS = 16
/** Matches the 180ms canvas crossfade per Designer spec §3. */
const CANVAS_FADE_MS = 180

export function Dashboard() {
  const { connectionState, reconnectAttempt, status, metrics, latestFrame, recentGames, envFrames, send } = useTrainingState()

  // Hyperparams live at the Dashboard so the single Start button in
  // <TrainingControls /> can submit them. Do NOT re-introduce a second
  // Start button inside <HyperparamForm /> — we intentionally collapsed
  // the two into one CTA.
  //
  // bot_level is intentionally NOT held here (Option A, 2026-04-12): it
  // lives exclusively on ``status.botLevel`` — the L1–L5 buttons in
  // <TrainingControls /> mutate it via training:set_level, and the BE
  // dispatcher carries it over into training:start when the payload
  // omits ``bot_level`` (schemas.py:92, handlers.py:131-135).
  const [params, setParams] = useState<Hyperparams>(DEFAULT_HYPERPARAMS)

  /**
   * Title for the next training run (FC-R6G, Designer spec c77baa0b
   * as revised by 1bc882ab). Empty is valid — BE auto-generates.
   * Submit is gated on the form's debounced duplicate check — a
   * user-typed duplicate or over-length title blocks; empty and
   * "checking" states are both submit-enabled.
   */
  const [title, setTitle] = useState('')
  const [titleValidation, setTitleValidation] = useState<TitleValidationState>({ kind: 'ok' })

  /**
   * Track the prior status.title so we can toast when BE echoes a
   * new value (either our input or an auto-generated name). Echo
   * lands on the `training:status` broadcast right after
   * `training:start` is accepted.
   */
  const lastBroadcastTitleRef = useRef<string | null | undefined>(undefined)

  /**
   * Currently-selected env for the batch tab bar + canvas mirror.
   * Default 0. Selection is ephemeral (not persisted) — the next
   * Start/refresh lands on ENV 0 again, matching Designer §3 intent.
   */
  const [activeEnvId, setActiveEnvId] = useState(0)
  /** Triggers the 180ms canvas fade after a chip click. */
  const [canvasFading, setCanvasFading] = useState(false)
  const fadeTimerRef = useRef<ReturnType<typeof setTimeout> | null>(null)

  /**
   * Prefer the live per-env frame when BE is broadcasting them
   * (`training:env_frame`, commit 65dd7336). Falls back to the legacy
   * single-frame broadcast (`training:frame`) for the standalone demo
   * game, so runs without parallel envs still light up the canvas.
   */
  const displayFrame = useMemo(() => {
    const envFrame = envFrames[activeEnvId]
    if (envFrame?.frame) return envFrame.frame
    return latestFrame
  }, [envFrames, activeEnvId, latestFrame])

  /**
   * Effective env count = max of:
   *   - baseline (DEFAULT_N_ENVS)
   *   - user's configured form value (params.n_envs)
   *   - observed envFrames max id + 1 (catches runs where user
   *     bumped n_envs beyond the form default, or where BE
   *     dispatches more envs than the status payload suggests)
   *
   * Clamped to MAX_N_ENVS (spec ceiling, 16). Without this FC-R6B
   * derivation a run with n_envs=16 rendered only the first 8 chips
   * because the old code hardcoded the baseline.
   */
  const effectiveNEnvs = useMemo(() => {
    // FC-R6C defensive: `envFrames` is always `{}` out of the hook
    // but a future refactor could nullify it accidentally.
    // `Object.keys(undefined)` throws — the only render-error trigger
    // a user could plausibly hit on refresh before WS data lands.
    const source = envFrames ?? {}
    const observed = Object.keys(source)
      .map(Number)
      .filter(n => Number.isFinite(n) && n >= 0)
      .reduce((max, id) => Math.max(max, id + 1), 0)
    const rawRequested = Number(params?.n_envs)
    const requested = Number.isFinite(rawRequested) ? rawRequested : DEFAULT_N_ENVS
    return Math.max(1, Math.min(MAX_N_ENVS, Math.max(DEFAULT_N_ENVS, requested, observed)))
  }, [envFrames, params])

  const score1 = displayFrame?.score1 ?? 0
  const score2 = displayFrame?.score2 ?? 0
  const isStopped = status.state === 'stopped'

  /** Kick the 180ms crossfade on active-env change. */
  const handleEnvSelect = (envId: number) => {
    if (envId === activeEnvId) return
    setActiveEnvId(envId)
    setCanvasFading(true)
    if (fadeTimerRef.current) clearTimeout(fadeTimerRef.current)
    fadeTimerRef.current = setTimeout(
      () => setCanvasFading(false),
      CANVAS_FADE_MS,
    )
  }

  useEffect(() => {
    return () => {
      if (fadeTimerRef.current) clearTimeout(fadeTimerRef.current)
    }
  }, [])

  // Show skeleton only on the very first connect attempt while we have no
  // data at all. After anything arrives (frame / metrics / recent games)
  // we keep the real UI up — even through reconnects — so the layout
  // doesn't flash back to skeletons mid-session. A persistent
  // disconnect should surface the reconnect banner, not a skeleton.
  const hasAnyData =
    latestFrame !== null || metrics.length > 0 || recentGames.length > 0
  const isInitialLoading = connectionState === 'connecting' && !hasAnyData
  if (isInitialLoading) {
    return <DashboardSkeleton />
  }

  /**
   * Build the `training:start` payload. BE
   * (`WsTrainingStartPayload`, cc4daaf3) accepts 5 fields at the
   * TOP LEVEL (total_timesteps / n_envs / n_epochs / ent_coef /
   * gae_lambda) and the rest inside the free-form `hyperparams`
   * blob. `HYPERPARAM_WIRE_POSITION` (lib/hyperparams.ts) is the
   * single source of truth for that split — moving a field to the
   * other shape is a one-line table edit, no submit-path change.
   *
   * Option A (2026-04-12) still holds: `bot_level` is NOT sent from
   * here — the BE dispatcher carries `status.bot_level` forward.
   */
  const formInvalid = useMemo(
    () =>
      // FC-R6C defensive: coerce explicitly through `Number()` so a
      // stale-state `params` object missing a freshly-added key
      // (e.g. NaN → invalid) surfaces cleanly via the form's error
      // UI instead of crashing the render.
      HYPERPARAM_SCHEMA.some(
        f => !validateHyperparam(f.key, Number(params?.[f.key as HyperparamKey])).valid,
      ),
    [params],
  )

  /**
   * Title blocks submit ONLY on hard-invalid states (too-long or
   * duplicate of a user-typed value). Empty title and in-flight
   * "checking" states are submit-enabled — see Designer spec §1
   * (1bc882ab revision: BE auto-generates on empty).
   */
  const titleBlocksSubmit =
    titleValidation.kind === 'tooLong' || titleValidation.kind === 'duplicate'

  const handleStart = () => {
    if (formInvalid || titleBlocksSubmit) return
    const hyperparamsBlob: Record<string, number> = {}
    const topLevel: Record<string, number> = {}
    for (const f of HYPERPARAM_SCHEMA) {
      const value = params[f.key as HyperparamKey]
      if (HYPERPARAM_WIRE_POSITION[f.key] === 'top-level') {
        topLevel[f.key] = value
      } else {
        hyperparamsBlob[f.key] = value
      }
    }
    // FC-R6G: send title verbatim. Empty string → BE auto-generates
    // (spec §0 rev 1bc882ab). Trim first so a user who hit space bar
    // gets the auto-gen path. We keep the un-trimmed display value in
    // the form state so the cursor position doesn't jump mid-type.
    const wireTitle = title.trim()
    send('training:start', {
      ...topLevel,
      hyperparams: hyperparamsBlob,
      title: wireTitle,
    })
  }

  /**
   * Toast when BE echoes the final title on the `training:status`
   * broadcast after Start. The echo carries either the user's input
   * (validated + accepted) or an auto-generated `run-{adj}-{noun}-
   * {4hex}` — either way the user learns what their run is named.
   *
   * Matching via the `lastBroadcastTitleRef`: record undefined on
   * first observation to skip the initial REST-hydration path (no
   * toast on page load), then fire on any id transition to a new
   * non-empty title.
   */
  useEffect(() => {
    const incoming = status.title ?? null
    const prev = lastBroadcastTitleRef.current
    if (prev === undefined) {
      lastBroadcastTitleRef.current = incoming
      return
    }
    if (incoming && incoming !== prev) {
      lastBroadcastTitleRef.current = incoming
      // eslint-disable-next-line no-console
      console.info(`[training] 학습 시작: ${incoming}`)
      // Full toast UX lives in a separate component; surfacing via
      // console for now keeps R6G scoped to data flow. The
      // DESIGN-HYPERPARAM-TOAST follow-up owns visible notification.
    } else if (incoming !== prev) {
      lastBroadcastTitleRef.current = incoming
    }
  }, [status.title])

  return (
    <div className="dashboard">
      <section className="dashboard-left" aria-labelledby="dashboard-game-heading">
        <h2 id="dashboard-game-heading" className="sr-only">Game &amp; Controls</h2>
        <TrainingControls
          status={status}
          connectionState={connectionState}
          reconnectAttempt={reconnectAttempt}
          send={send}
          onStart={handleStart}
        />

        {/*
          Local ErrorBoundary (FC-R6C, 2026-04-18): a refresh
          before any WS frame lands occasionally threw inside the
          canvas + batch-tab subtree ("Something unexpected..."
          message users reported). Global ErrorBoundary blanked
          the whole page; this local one contains any render
          failure so the controls + metrics + recent-games
          surfaces stay usable. The user can hit "Try again" on
          the boundary to remount just the canvas.
        */}
        <ErrorBoundary>
          <div
            className={`dashboard-game-wrapper${canvasFading ? ' batch-canvas-fading' : ''}`}
            role="tabpanel"
            aria-labelledby={`batch-tab-${activeEnvId}`}
            aria-label={`Live game canvas — Env ${activeEnvId}`}
          >
            <GameCanvas gameState={displayFrame} />
            <GameOverlay score1={score1} score2={score2} />
            {!displayFrame && status.state === 'running' && (
              <div className="dashboard-game-waiting" role="status" aria-live="polite">
                Waiting for game frames...
              </div>
            )}
          </div>

          <BatchTabBar
            envFrames={envFrames ?? {}}
            nEnvs={effectiveNEnvs}
            activeEnvId={activeEnvId}
            onSelect={handleEnvSelect}
          />
        </ErrorBoundary>

        {isStopped && (
          <HyperparamForm
            params={params}
            onParamsChange={setParams}
            disabled={connectionState !== 'connected'}
            title={title}
            onTitleChange={setTitle}
            onTitleValidationChange={setTitleValidation}
          />
        )}
      </section>

      <section className="dashboard-right" aria-labelledby="dashboard-metrics-heading">
        <h2 id="dashboard-metrics-heading" className="sr-only">Training Metrics</h2>
        <MetricsChart data={metrics} dataKey="meanReward" color="#22c55e" label="Reward" currentStep={status.currentStep} />
        <MetricsChart data={metrics} dataKey="winRate" color="#3b82f6" label="Win Rate" currentStep={status.currentStep} />
        <MetricsChart data={metrics} dataKey="policyLoss" color="#ef4444" label="Policy Loss" currentStep={status.currentStep} />
        <MetricsChart data={metrics} dataKey="valueLoss" color="#f97316" label="Value Loss" currentStep={status.currentStep} />
      </section>

      <section className="dashboard-bottom" aria-labelledby="recent-games-heading">
        <div className="card">
          <h3 className="card-title" id="recent-games-heading">Recent Games</h3>
          {recentGames.length === 0 ? (
            <p className="recent-games-empty empty-state">No games yet.</p>
          ) : (
            <div className="recent-games table-scroll">
              <table className="recent-games-table" aria-labelledby="recent-games-heading">
                <thead>
                  <tr>
                    {/*
                      `#` rank column dropped (R2-empirical, 2026-04-18):
                      user reported the Time column's leading digit looked
                      gray even after `.text-muted` was removed from the
                      cell. Playwright inspection against dev bundle
                      UoTn_2Rz confirmed the Time cell actually renders at
                      primary color (rgb 26, 29, 41) — the "gray first
                      digit" was the `#` column's muted digit sitting 24px
                      to the left of "2026" in the same monospace font,
                      reading as a single token across the cell boundary.
                      Evidence screenshot in
                      docs/fe-evidence/r2-rank-illusion-dev-UoTn_2Rz.png.
                      The `#` column was also redundant with the row's
                      top-to-bottom ordering — dropping it kills the
                      adjacency at its source without loss of information.
                    */}
                    {([
                      ['Time'],
                      // FC-R6G (2026-04-18): GameRecord.title (BE T1,
                      // commit a7351e57) carries the human training
                      // label. Legacy rows render "—".
                      ['Title'],
                      ['Env'],
                      // FC-R6D (2026-04-18): em-dash values are
                      // BE-WAITING — the field isn't on
                      // GameRecord yet. Surface a tooltip so users
                      // understand the column isn't broken.
                      ['Episode', 'Pending BE support — field not yet saved per game'],
                      ['Bot Level'],
                      ['Score'],
                      ['Winner'],
                      ['Frames'],
                      ['Rallies'],
                      ['Avg Rally'],
                      ['Experiment'],
                    ] as Array<[string, string?]>).map(([h, tip]) => (
                      <th key={h} scope="col" title={tip}>{h}</th>
                    ))}
                  </tr>
                </thead>
                <tbody>
                  {recentGames.slice(0, 20).map((g) => (
                    <tr key={g.id}>
                      <td>{formatKstDateTime(g.timestamp)}</td>
                      <td
                        className="recent-games-title-cell"
                        title={g.title ?? undefined}
                      >
                        {g.title && g.title.trim() !== '' ? (
                          // R6H spec §0: Recent Games rows deep-link
                          // to the level-2 drill-down for their run.
                          <Link
                            to={`/history/${encodeURIComponent(g.title)}`}
                            className="recent-games-title-link"
                          >
                            {g.title}
                          </Link>
                        ) : (
                          '—'
                        )}
                      </td>
                      <td>
                        <span
                          className={`env-chip${g.envId === undefined ? ' env-chip--empty' : ''}`}
                          aria-label={
                            g.envId === undefined
                              ? 'No env id recorded'
                              : `Env ${g.envId}`
                          }
                          data-env-id={g.envId ?? ''}
                        >
                          {formatEnvId(g.envId)}
                        </span>
                      </td>
                      <td className="text-muted">{formatEpisode(g.episode)}</td>
                      <td>{formatBotLevel(g.botLevel)}</td>
                      <td className="score-cell">
                        <span className="score-p1">{g.score1}</span>
                        {' : '}
                        <span className="score-p2">{g.score2}</span>
                      </td>
                      <td className={g.winner === 1 ? 'winner-agent' : 'winner-bot'}>
                        {g.winner === 1 ? 'RL Agent' : 'Bot'}
                      </td>
                      <td className="text-muted">{g.durationFrames}</td>
                      <td className="text-muted">{formatRallyCount(g.rallyCount)}</td>
                      <td className="text-muted">
                        {formatAvgRallyLength(g.durationFrames, g.rallyCount)}
                      </td>
                      <td className="text-muted text-mono" title={g.experimentId ?? undefined}>
                        {formatExperimentIdShort(g.experimentId)}
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
        </div>
      </section>
    </div>
  )
}

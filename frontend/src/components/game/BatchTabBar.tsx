import { useCallback, useEffect, useMemo, useRef, useState } from 'react'
import type { EnvFramesMap } from '../../hooks/useTrainingState'
import './BatchTabBar.css'

/**
 * Batch tab bar (Designer spec `docs/DESIGN-BATCH-TABS.md`, commit
 * 90c8ac79). Renders one chip per parallel env, lets the user switch
 * which env the `GameCanvas` mirrors, and surfaces per-env live score
 * + engine-state dot so training is observable at a glance without
 * cycling through tabs.
 *
 * Visual model (§2):
 *   - 2-row chip: "ENV N" label + "P1 : P2" score
 *   - 8×8 status dot on the right edge:
 *       live / round                  → warning pulse (yellow)
 *       recent score (≤400ms after
 *       a score change)               → success flash (green)
 *       gameEnd                       → danger (red)
 *   - Active tab: accent-dim fill + 2px accent bottom bar
 *
 * Interaction (§3):
 *   - Click chip → fires `onSelect(envId)`; GameCanvas opacity-fades
 *     via its own crossfade class in the parent.
 *   - ← / → cycles, 1–8 jumps to ENV 0–7. Shortcuts ignored inside
 *     form controls (input/select/textarea) and when a modifier key
 *     (alt/ctrl/meta) is held.
 *   - `aria-selected` on each tab; container is `role="tablist"`.
 *
 * Responsive (§5):
 *   - ≥9 envs → container falls back to snap-scroll (handled in CSS
 *     via the `data-overflow="scroll"` attribute).
 */

/** Maximum supported envs per spec §1 (range 1-16). */
const MAX_ENVS = 16
/** Window (ms) during which a fresh score change flashes the success dot. */
const SCORE_FLASH_MS = 400
/** Extra slack beyond SCORE_FLASH_MS for the React re-render timer. */
const FLASH_RERENDER_SLACK_MS = 50

/**
 * Read the `--batch-cols` custom property off the closest batch-tab
 * container so keyboard row jumps (↑ / ↓) stay aligned with the CSS
 * wrap grid — the CSS already sets the value at each breakpoint
 * (desktop 4 / tablet 3 / mobile 2, see BatchTabBar.css).
 *
 * Returns 0 when the property isn't parseable; callers should
 * default to a sensible fallback (4).
 */
function readColsFromCSS(el: HTMLElement | null): number {
  if (!el) return 0
  const bar = el.closest('.batch-tab-bar') as HTMLElement | null
  if (!bar) return 0
  const raw = getComputedStyle(bar).getPropertyValue('--batch-cols').trim()
  const n = Number.parseInt(raw, 10)
  return Number.isFinite(n) && n > 0 ? n : 0
}

export interface BatchTabBarProps {
  /** Live per-env snapshots, keyed on `env_id`. */
  envFrames: EnvFramesMap
  /** Number of parallel envs; defaults to 8 (the project baseline). */
  nEnvs?: number
  /** Currently-selected env id (mirrored on the canvas). */
  activeEnvId: number
  /** Fires when the user clicks a chip or uses a keyboard shortcut. */
  onSelect: (envId: number) => void
}

type DotState = 'warning' | 'success' | 'danger'

function resolveDotState(
  stateName: string | undefined,
  hasRecentScore: boolean,
): DotState {
  if (hasRecentScore) return 'success'
  if (stateName === 'gameEnd') return 'danger'
  return 'warning'
}

export function BatchTabBar({
  envFrames,
  nEnvs = 8,
  activeEnvId,
  onSelect,
}: BatchTabBarProps) {
  // Clamp requested count into the spec's supported range so a rogue
  // BE config can't blow up the render.
  const clampedN = Math.max(1, Math.min(MAX_ENVS, nEnvs))
  const envIds = useMemo(
    () => Array.from({ length: clampedN }, (_, i) => i),
    [clampedN],
  )

  /**
   * Track the last-seen score per env so we can flash the "just
   * scored" success dot for SCORE_FLASH_MS. The refs carry the
   * authoritative value AND a millisecond timestamp; the
   * `flashingTick` state below is a nudge to force a re-render when
   * the flash should expire.
   */
  const lastScoreRef = useRef<Record<number, string>>({})
  const scoreChangedAtRef = useRef<Record<number, number>>({})
  // Incrementing counter just to force a re-render after the flash
  // window closes — Date.now() ticking forward won't re-run the
  // resolveDotState memo on its own.
  const [, setFlashTick] = useState(0)

  // Update the lastScore refs whenever a new envFrames reference lands.
  // This runs during render (it only touches refs). First observation
  // of an env sets the baseline WITHOUT triggering the flash — the
  // flash only fires on a genuine score *change*, not on the first
  // frame we see. Without that guard every initial render would light
  // up the success dot for 400ms, masking the actual state dot.
  envIds.forEach(id => {
    const frame = envFrames[id]
    if (!frame) return
    const sig = `${frame.score[0]}-${frame.score[1]}`
    const prev = lastScoreRef.current[id]
    if (prev === sig) return
    const isFirstObservation = prev === undefined
    lastScoreRef.current[id] = sig
    if (!isFirstObservation) {
      scoreChangedAtRef.current[id] = Date.now()
    }
  })

  // Schedule a re-render after the flash window so the success dot
  // falls back to warning. Effect re-runs on every envFrames change.
  useEffect(() => {
    const id = setTimeout(
      () => setFlashTick(t => t + 1),
      SCORE_FLASH_MS + FLASH_RERENDER_SLACK_MS,
    )
    return () => clearTimeout(id)
  }, [envFrames])

  const isFlashing = useCallback((id: number): boolean => {
    const changedAt = scoreChangedAtRef.current[id]
    if (!changedAt) return false
    return Date.now() - changedAt < SCORE_FLASH_MS
  }, [])

  /**
   * Keyboard: ←/→ cycles within the row-flow order; ↑/↓ jumps up or
   * down a row in the wrap grid (FC-R6A user report, 2026-04-18).
   * Digits 1..8 jump to ENV 0..7 absolutely.
   *
   * Row math uses the container's computed `--batch-cols` CSS
   * custom property — the same value the CSS reads for
   * `flex-basis`, so keyboard navigation matches the visual grid
   * exactly across breakpoints (4 / 3 / 2 desktop/tablet/mobile).
   * Fallback to 4 if the property is unset (e.g. during SSR / tests
   * without full stylesheet evaluation).
   *
   * Wrap behaviour:
   *   - ArrowLeft / ArrowRight: modulo cycle, no row jump.
   *   - ArrowUp: subtract one row's worth of envs. If the target
   *     would fall outside [0, N-1], wrap to the equivalent column
   *     on the last row (so pressing ↑ at the top lands on the
   *     bottom row, same column).
   *   - ArrowDown: symmetric — add one row, wrap to the first row
   *     on overflow.
   *
   * Tablist doesn't contain vertical nav per strict WAI-ARIA, but
   * since our tabs ARE arranged in a grid the user expects 2D nav;
   * surfacing it doesn't break screen-reader tab cycling (Tab still
   * exits the bar per roving tabindex).
   */
  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      const tag = (e.target as HTMLElement | null)?.tagName
      if (tag === 'INPUT' || tag === 'SELECT' || tag === 'TEXTAREA') return
      if (e.altKey || e.ctrlKey || e.metaKey) return

      if (e.code === 'ArrowLeft') {
        e.preventDefault()
        onSelect((activeEnvId - 1 + clampedN) % clampedN)
        return
      }
      if (e.code === 'ArrowRight') {
        e.preventDefault()
        onSelect((activeEnvId + 1) % clampedN)
        return
      }
      if (e.code === 'ArrowUp' || e.code === 'ArrowDown') {
        e.preventDefault()
        const cols = readColsFromCSS(tabRefs.current[activeEnvId]) || 4
        const delta = e.code === 'ArrowUp' ? -cols : cols
        const raw = activeEnvId + delta
        // Wrap to the equivalent column on the opposite row edge.
        // `((raw % N) + N) % N` handles negatives; combined with the
        // column-preserving step, ↑ at top row lands on bottom row's
        // same col, ↓ at bottom row lands on top row's same col.
        const next = ((raw % clampedN) + clampedN) % clampedN
        onSelect(next)
        return
      }
      const digitMatch = e.code.match(/^Digit([1-8])$/)
      if (digitMatch) {
        const target = Number(digitMatch[1]) - 1
        if (target < clampedN) {
          e.preventDefault()
          onSelect(target)
        }
      }
    }
    window.addEventListener('keydown', onKey)
    return () => window.removeEventListener('keydown', onKey)
  }, [activeEnvId, clampedN, onSelect])

  /**
   * Roving tabindex / follow-focus pattern (FC-R1 user report,
   * 2026-04-18). Without this, `:focus-visible` stays pinned on the
   * last-clicked tab while `activeEnvId` moves via arrow keys — both
   * the clicked tab (focus outline) AND the active tab (bottom bar +
   * accent-dim fill) render with the same Pikachu-yellow accent, so
   * the user sees the highlight "stuck" on the click target.
   *
   * Fix: whenever `activeEnvId` changes — via ANY path (click,
   * arrow, digit) — programmatically move focus to the active tab's
   * button. Focus ring then rides along with the active class, and
   * only ONE tab wears accent colour at a time.
   *
   * `tabIndex={isActive ? 0 : -1}` on each button keeps the tablist
   * as a single Tab stop (pressing Tab exits the bar; arrows navigate
   * within), per the WAI-ARIA tablist authoring pattern.
   *
   * Guard: skip the focus move when the tablist doesn't contain the
   * current focus (e.g. the user navigated away / hasn't interacted
   * yet). Otherwise clicking a score elsewhere on the page would
   * fight us for focus.
   */
  const tabRefs = useRef<Array<HTMLButtonElement | null>>([])
  useEffect(() => {
    const el = tabRefs.current[activeEnvId]
    if (!el) return
    const container = el.closest('.batch-tab-bar')
    const active = document.activeElement
    if (!container?.contains(active)) return
    el.focus({ preventScroll: false })
  }, [activeEnvId])

  return (
    <div
      className="batch-tab-bar"
      role="tablist"
      aria-label="Parallel training environments"
      data-env-count={clampedN}
      // FC-R4 (Designer spec v2, commit 19848eb8): layout switched
      // from CSS grid + snap-scroll to `flex-wrap` so rows grow
      // downward instead of scrolling horizontally. `data-overflow`
      // dropped — the container no longer has two variants.
      style={{ '--n-envs': clampedN } as React.CSSProperties}
    >
      {envIds.map(id => {
        const frame = envFrames[id]
        const score = frame?.score ?? [0, 0]
        const dotState = resolveDotState(frame?.stateName, isFlashing(id))
        const isActive = id === activeEnvId
        return (
          <button
            key={id}
            ref={el => { tabRefs.current[id] = el }}
            type="button"
            role="tab"
            aria-selected={isActive}
            aria-label={`Env ${id}, score ${score[0]} to ${score[1]}`}
            className={`batch-tab${isActive ? ' batch-tab--active' : ''}`}
            onClick={() => onSelect(id)}
            // Roving tabindex: only the active tab is in the tab
            // order, per the WAI-ARIA tablist pattern. Keeps Tab a
            // single in/out action for the whole bar while arrows
            // navigate within.
            tabIndex={isActive ? 0 : -1}
            data-env-id={id}
          >
            <span className="batch-tab-label">ENV {id}</span>
            <span className="batch-tab-score" aria-hidden="true">
              <span className="score-p1">{score[0]}</span>
              {' : '}
              <span className="score-p2">{score[1]}</span>
            </span>
            <span
              className={`batch-tab-dot batch-tab-dot--${dotState}`}
              aria-hidden="true"
            />
          </button>
        )
      })}
    </div>
  )
}

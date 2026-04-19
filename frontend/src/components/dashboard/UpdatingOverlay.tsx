import { useEffect, useRef, useState } from 'react'
import './UpdatingOverlay.css'

/**
 * UpdatingOverlay — renders the transient "Updating policy"
 * screen during the PPO gradient-update freeze between rollouts
 * (Designer spec f02a9785, docs/design/UPDATING-OVERLAY.md).
 *
 * Presentation layer only — the show/hide + long-gap signal live
 * on `useTrainingState().updatingPolicy`. This component owns:
 *
 *   * Spec §2 timing — 200 ms fade-in / 300 ms fade-out, 400 ms
 *     minimum visible so a transient frame delay can't flicker
 *     the overlay on and off within one animation cycle.
 *   * Subtitle swap (spec §5) — the alternate
 *     "This is taking longer than usual…" string is driven from
 *     the `longGap` prop (hook flips it after 8 s of silence).
 *   * `role="status"` + `aria-live="polite"` (spec §3). The title
 *     is announced once per show, not once per frame — React
 *     handles this implicitly because the title text doesn't
 *     change within a single mount.
 *   * `prefers-reduced-motion` honoured via the CSS side
 *     (transition duration collapses to 0 ms); the 400 ms visible
 *     floor applies either way.
 */
const FADE_OUT_MS = 300
const MIN_VISIBLE_MS = 400

/**
 * `source` steers the subtitle copy (Fix-A FE):
 *   - `'event'` → "Gradient update in progress (step N)" when the
 *     BE `training:update_start` broadcast is authoritative. `step`
 *     is rendered when provided; omitted when null.
 *   - `'heuristic'` → "Awaiting frames (server busy)" when the FE
 *     inferred the freeze from 3 s of frame silence.
 *   - `null` → only valid when `show=false`; copy reverts to the
 *     event wording (the subtitle text doesn't render while
 *     hidden).
 */
export function UpdatingOverlay({
  show,
  longGap,
  source,
  step,
}: {
  show: boolean
  longGap?: boolean
  source?: 'event' | 'heuristic' | null
  step?: number | null
}) {
  const [mounted, setMounted] = useState(show)
  const [visible, setVisible] = useState(show)
  // Timestamp of the most recent show transition (false → true).
  // Used to enforce the 400 ms minimum-visible window.
  const shownAtRef = useRef<number>(0)
  const pendingHideRef = useRef<ReturnType<typeof setTimeout> | null>(null)
  const unmountTimerRef = useRef<ReturnType<typeof setTimeout> | null>(null)

  useEffect(() => {
    if (show) {
      // Cancel any pending hide — rollout resumed mid-fade-out and
      // then stalled again. We keep the overlay up.
      if (pendingHideRef.current) {
        clearTimeout(pendingHideRef.current)
        pendingHideRef.current = null
      }
      if (unmountTimerRef.current) {
        clearTimeout(unmountTimerRef.current)
        unmountTimerRef.current = null
      }
      setMounted(true)
      // A 0-tick defer ensures the element paints at opacity=0
      // first so the class-driven CSS transition to opacity=1 has
      // a starting frame. setTimeout-0 works with both real + fake
      // timer schedulers; requestAnimationFrame interacts poorly
      // with vitest's fake clock.
      const settle = setTimeout(() => {
        shownAtRef.current = Date.now()
        setVisible(true)
      }, 0)
      return () => clearTimeout(settle)
    }

    // show → false. Enforce the 400 ms minimum-visible rule:
    // never start the fade-out before MIN_VISIBLE_MS has elapsed
    // since the last show.
    const since = Date.now() - shownAtRef.current
    const startHideDelay = Math.max(0, MIN_VISIBLE_MS - since)

    const startHide = () => {
      pendingHideRef.current = null
      setVisible(false)
      unmountTimerRef.current = setTimeout(() => {
        setMounted(false)
        unmountTimerRef.current = null
      }, FADE_OUT_MS)
    }

    if (startHideDelay === 0) {
      startHide()
    } else {
      pendingHideRef.current = setTimeout(startHide, startHideDelay)
    }

    return () => {
      if (pendingHideRef.current) {
        clearTimeout(pendingHideRef.current)
        pendingHideRef.current = null
      }
      if (unmountTimerRef.current) {
        clearTimeout(unmountTimerRef.current)
        unmountTimerRef.current = null
      }
    }
  }, [show])

  if (!mounted) return null

  return (
    <div
      className={`updating-overlay${visible ? ' updating-overlay--visible' : ''}`}
      role="status"
      aria-live="polite"
      aria-label="Updating training policy"
    >
      <div className="updating-overlay-card">
        <div className="updating-overlay-heading">
          <span className="updating-overlay-dot dot-pulse" aria-hidden="true" />
          <p className="updating-overlay-title">Updating policy</p>
        </div>
        <p className="updating-overlay-subtitle">
          {resolveSubtitle({ longGap, source, step })}
        </p>
      </div>
    </div>
  )
}

/**
 * Picks the subtitle string for the current overlay state (Fix-A
 * FE). Separate function so the tests can pin the copy matrix
 * without re-walking the render tree for each case.
 *
 * Priority:
 *   1. long-gap escalation (spec §5) wins regardless of source
 *   2. BE event path emits the step number when one is provided
 *   3. heuristic fallback wording otherwise
 */
function resolveSubtitle({
  longGap,
  source,
  step,
}: {
  longGap?: boolean
  source?: 'event' | 'heuristic' | null
  step?: number | null
}): string {
  if (longGap) return 'This is taking longer than usual…'
  if (source === 'heuristic') return 'Awaiting frames (server busy)'
  if (typeof step === 'number') {
    return `Gradient update in progress (step ${step.toLocaleString()})`
  }
  return 'Gradient update in progress'
}

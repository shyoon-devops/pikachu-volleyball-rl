import { useState, useMemo, useCallback, useRef, useEffect } from 'react'
import {
  LineChart,
  Line,
  XAxis,
  YAxis,
  CartesianGrid,
  Tooltip,
  ResponsiveContainer,
  ReferenceArea,
} from 'recharts'
import type { TrainingMetrics } from '../../lib/types'
import './MetricsChart.css'

// Short, compositor-friendly tween so continuously streamed metrics never
// feel like a series of jumps. Too long → the line lags behind real data;
// too short → no perceivable smoothing.
const ANIMATION_DURATION_MS = 250

interface MetricsChartProps {
  data: TrainingMetrics[]
  dataKey: keyof TrainingMetrics
  xKey?: keyof TrainingMetrics
  color: string
  label: string
  /**
   * Authoritative live training step from `status.currentStep`. Used
   * only for the "N data points over M steps" cadence label — the
   * chart itself plots `xKey` (= data[i].step). We pass it through so
   * the label reflects the *current* step, not the step of the most
   * recent sampled point, which lags by up to `MetricsCallback.
   * log_interval` (=100) frames. Without this the label would read
   * "10 points over 900 steps" while the header counter shows 1000,
   * which looks like a bug rather than expected sampling cadence.
   */
  currentStep?: number
}

function ema(data: number[], alpha: number): number[] {
  if (data.length === 0 || alpha <= 0) return data
  const result: number[] = [data[0]]
  for (let i = 1; i < data.length; i++) {
    result.push(alpha * result[i - 1] + (1 - alpha) * data[i])
  }
  return result
}

function usePrefersReducedMotion(): boolean {
  const [reduced, setReduced] = useState<boolean>(() => {
    if (typeof window === 'undefined' || !window.matchMedia) return false
    return window.matchMedia('(prefers-reduced-motion: reduce)').matches
  })

  useEffect(() => {
    if (typeof window === 'undefined' || !window.matchMedia) return
    const mq = window.matchMedia('(prefers-reduced-motion: reduce)')
    const onChange = (e: MediaQueryListEvent) => setReduced(e.matches)
    mq.addEventListener('change', onChange)
    return () => mq.removeEventListener('change', onChange)
  }, [])

  return reduced
}

export function MetricsChart({ data, dataKey, xKey = 'step', color, label, currentStep }: MetricsChartProps) {
  const [smoothing, setSmoothing] = useState(0)
  const [zoomLeft, setZoomLeft] = useState<number | null>(null)
  const [zoomRight, setZoomRight] = useState<number | null>(null)
  const [dragStart, setDragStart] = useState<number | null>(null)
  const [dragEnd, setDragEnd] = useState<number | null>(null)
  const isDragging = useRef(false)
  const prefersReducedMotion = usePrefersReducedMotion()
  const animationDuration = prefersReducedMotion ? 0 : ANIMATION_DURATION_MS
  const animationActive = !prefersReducedMotion

  const smoothedData = useMemo(() => {
    if (smoothing <= 0 || data.length === 0) return data

    const raw = data.map(d => d[dataKey] as number)
    const smoothed = ema(raw, smoothing)

    return data.map((d, i) => ({
      ...d,
      [`${String(dataKey)}Smoothed`]: smoothed[i],
    }))
  }, [data, dataKey, smoothing])

  const visibleData = useMemo(() => {
    if (zoomLeft === null || zoomRight === null) return smoothedData
    return smoothedData.filter(d => {
      const x = d[xKey] as number
      return x >= zoomLeft && x <= zoomRight
    })
  }, [smoothedData, xKey, zoomLeft, zoomRight])

  const handleMouseDown = useCallback((e: { activeLabel?: string | number }) => {
    if (e?.activeLabel != null) {
      const val = Number(e.activeLabel)
      setDragStart(val)
      setDragEnd(null)
      isDragging.current = true
    }
  }, [])

  const handleMouseMove = useCallback((e: { activeLabel?: string | number }) => {
    if (isDragging.current && e?.activeLabel != null) {
      setDragEnd(Number(e.activeLabel))
    }
  }, [])

  const handleMouseUp = useCallback(() => {
    if (dragStart !== null && dragEnd !== null && dragStart !== dragEnd) {
      const left = Math.min(dragStart, dragEnd)
      const right = Math.max(dragStart, dragEnd)
      setZoomLeft(left)
      setZoomRight(right)
    }
    setDragStart(null)
    setDragEnd(null)
    isDragging.current = false
  }, [dragStart, dragEnd])

  const handleZoomReset = useCallback(() => {
    setZoomLeft(null)
    setZoomRight(null)
    setDragStart(null)
    setDragEnd(null)
  }, [])

  const isZoomed = zoomLeft !== null && zoomRight !== null
  const smoothedKey = `${String(dataKey)}Smoothed`

  // Sampling-cadence label (user-reported 2026-04-12, PM Phase 2 #4):
  // step counter shows 1000 but the chart has ~10 points, making it
  // look like data is being dropped. It isn't — MetricsCallback writes
  // one snapshot every log_interval training steps (=100 at the time
  // of writing). Surface the ratio in the header so the count is
  // self-explanatory; tooltip shows the derived per-sample interval.
  //
  // `currentStep` wins over data[last].step for the denominator: the
  // authoritative step advances every frame while the chart only gets
  // a point every log_interval frames, so the denominator should track
  // the *live* step — otherwise the label would freeze between
  // sample-writes and look stuck. Falls back to the last sample's step
  // when the prop is absent so charts that don't pass it still work.
  const sampleSummary = useMemo(() => {
    if (data.length === 0) return null
    const lastSampleStep = data[data.length - 1].step
    const firstSampleStep = data[0].step
    const denominator = currentStep ?? lastSampleStep
    const intervalPerSample =
      data.length > 1
        ? Math.max(1, Math.round((lastSampleStep - firstSampleStep) / (data.length - 1)))
        : null
    return {
      count: data.length,
      currentStep: denominator,
      intervalPerSample,
    }
  }, [data, currentStep])

  return (
    <div className="metrics-chart card">
      <div className="metrics-chart-header">
        <h3 className="metrics-chart-title">{label}</h3>
        {sampleSummary && (
          <span
            className="metrics-chart-sample-summary"
            title={
              sampleSummary.intervalPerSample
                ? `~1 sample per ${sampleSummary.intervalPerSample} training steps`
                : undefined
            }
          >
            {sampleSummary.count} pts · {sampleSummary.currentStep} steps
          </span>
        )}
        <div className="metrics-chart-controls">
          {isZoomed && (
            <button
              onClick={handleZoomReset}
              className="metrics-chart-zoom-reset btn btn-ghost"
              title="Reset zoom"
            >
              Reset
            </button>
          )}
          <label className="metrics-chart-smooth-label" title="EMA smoothing factor">
            <span className="metrics-chart-smooth-text">
              Smooth {smoothing > 0 ? smoothing.toFixed(2) : 'off'}
            </span>
            <input
              type="range"
              min={0}
              max={0.99}
              step={0.01}
              value={smoothing}
              onChange={e => setSmoothing(Number(e.target.value))}
              className="metrics-chart-smooth-slider"
            />
          </label>
        </div>
      </div>
      <ResponsiveContainer width="100%" height={180}>
        <LineChart
          data={visibleData}
          margin={{ top: 4, right: 12, left: 0, bottom: 4 }}
          onMouseDown={handleMouseDown}
          onMouseMove={handleMouseMove}
          onMouseUp={handleMouseUp}
        >
          <CartesianGrid strokeDasharray="3 3" />
          {/*
            Anchor the unzoomed x-axis at step 0 so the chart's left
            edge stays put across page refreshes (F3 user report,
            2026-04-18). Recharts' default `[dataMin, dataMax]` domain
            drifts forward whenever the FE ring buffer
            (MAX_METRICS_POINTS=1000) rolls or the BE timeseries
            response trims older samples — making the chart look like
            it "jumps" between sessions even though the same
            experiment is still running. Pinning to 0 makes the x-axis
            an honest "training step since experiment start" axis.

            When the user drags to zoom we revert to `dataMin/dataMax`
            on the visible (already-filtered) slice so the zoom box
            isn't padded with empty space back to step 0.

            `type='number'` is required for `domain` to take effect —
            XAxis defaults to 'category' which ignores the prop.
          */}
          <XAxis
            dataKey={xKey}
            type="number"
            domain={isZoomed ? ['dataMin', 'dataMax'] : [0, 'dataMax']}
            allowDataOverflow={false}
            tickLine={false}
          />
          <YAxis tickLine={false} width={48} />
          <Tooltip />

          {/* Raw data line (dimmed when smoothing active) */}
          <Line
            type="monotone"
            dataKey={dataKey}
            stroke={color}
            strokeWidth={smoothing > 0 ? 1 : 2}
            strokeOpacity={smoothing > 0 ? 0.25 : 1}
            dot={false}
            isAnimationActive={animationActive}
            animationDuration={animationDuration}
            animationEasing="ease-out"
          />

          {/* Smoothed overlay */}
          {smoothing > 0 && (
            <Line
              type="monotone"
              dataKey={smoothedKey}
              stroke={color}
              strokeWidth={2}
              dot={false}
              isAnimationActive={animationActive}
              animationDuration={animationDuration}
              animationEasing="ease-out"
            />
          )}

          {/* Drag selection area */}
          {dragStart !== null && dragEnd !== null && (
            <ReferenceArea
              x1={dragStart}
              x2={dragEnd}
              strokeOpacity={0.3}
              fill={color}
              fillOpacity={0.1}
            />
          )}
        </LineChart>
      </ResponsiveContainer>
    </div>
  )
}

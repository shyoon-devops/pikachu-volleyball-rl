import { useState, useMemo, useCallback, useRef } from 'react'
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

interface MetricsChartProps {
  data: TrainingMetrics[]
  dataKey: keyof TrainingMetrics
  xKey?: keyof TrainingMetrics
  color: string
  label: string
}

function ema(data: number[], alpha: number): number[] {
  if (data.length === 0 || alpha <= 0) return data
  const result: number[] = [data[0]]
  for (let i = 1; i < data.length; i++) {
    result.push(alpha * result[i - 1] + (1 - alpha) * data[i])
  }
  return result
}

export function MetricsChart({ data, dataKey, xKey = 'step', color, label }: MetricsChartProps) {
  const [smoothing, setSmoothing] = useState(0)
  const [zoomLeft, setZoomLeft] = useState<number | null>(null)
  const [zoomRight, setZoomRight] = useState<number | null>(null)
  const [dragStart, setDragStart] = useState<number | null>(null)
  const [dragEnd, setDragEnd] = useState<number | null>(null)
  const isDragging = useRef(false)

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

  return (
    <div className="metrics-chart card">
      <div className="metrics-chart-header">
        <h3 className="metrics-chart-title">{label}</h3>
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
          <XAxis dataKey={xKey} tickLine={false} />
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
            isAnimationActive={false}
          />

          {/* Smoothed overlay */}
          {smoothing > 0 && (
            <Line
              type="monotone"
              dataKey={smoothedKey}
              stroke={color}
              strokeWidth={2}
              dot={false}
              isAnimationActive={false}
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

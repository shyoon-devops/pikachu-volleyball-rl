import { LineChart, Line, XAxis, YAxis, CartesianGrid, Tooltip, ResponsiveContainer } from 'recharts'
import type { TrainingMetrics } from '../../lib/types'
import './MetricsChart.css'

interface MetricsChartProps {
  data: TrainingMetrics[]
  dataKey: keyof TrainingMetrics
  xKey?: keyof TrainingMetrics
  color: string
  label: string
}

export function MetricsChart({ data, dataKey, xKey = 'step', color, label }: MetricsChartProps) {
  return (
    <div className="metrics-chart">
      <h3 className="metrics-chart__title">{label}</h3>
      <ResponsiveContainer width="100%" height={180}>
        <LineChart data={data} margin={{ top: 4, right: 12, left: 0, bottom: 4 }}>
          <CartesianGrid strokeDasharray="3 3" stroke="rgba(255,255,255,0.04)" />
          <XAxis
            dataKey={xKey}
            tick={{ fontSize: 10, fill: 'var(--color-text-muted)' }}
            axisLine={{ stroke: 'rgba(255,255,255,0.06)' }}
            tickLine={false}
          />
          <YAxis
            tick={{ fontSize: 10, fill: 'var(--color-text-muted)' }}
            axisLine={{ stroke: 'rgba(255,255,255,0.06)' }}
            tickLine={false}
            width={48}
          />
          <Tooltip
            contentStyle={{
              background: 'var(--color-bg-primary)',
              border: '1px solid var(--color-border-strong)',
              borderRadius: 'var(--radius-md)',
              fontSize: 12,
              fontFamily: 'var(--font-mono)',
              boxShadow: 'var(--shadow-lg)',
            }}
            labelStyle={{ color: 'var(--color-text-muted)' }}
          />
          <Line
            type="monotone"
            dataKey={dataKey}
            stroke={color}
            strokeWidth={2}
            dot={false}
            isAnimationActive={false}
          />
        </LineChart>
      </ResponsiveContainer>
    </div>
  )
}

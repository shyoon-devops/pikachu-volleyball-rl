import { LineChart, Line, XAxis, YAxis, CartesianGrid, Tooltip, ResponsiveContainer } from 'recharts'
import type { TrainingMetrics } from '../../lib/types'

interface MetricsChartProps {
  data: TrainingMetrics[]
  dataKey: keyof TrainingMetrics
  xKey?: keyof TrainingMetrics
  color: string
  label: string
}

export function MetricsChart({ data, dataKey, xKey = 'step', color, label }: MetricsChartProps) {
  return (
    <div style={{ background: '#1a1a2e', borderRadius: 8, padding: '16px 8px 8px', border: '1px solid #2a2a3e' }}>
      <h3 style={{ margin: '0 0 8px 12px', fontSize: 13, color: '#888', fontWeight: 500 }}>{label}</h3>
      <ResponsiveContainer width="100%" height={180}>
        <LineChart data={data} margin={{ top: 4, right: 12, left: 0, bottom: 4 }}>
          <CartesianGrid strokeDasharray="3 3" stroke="#2a2a3e" />
          <XAxis
            dataKey={xKey}
            tick={{ fontSize: 10, fill: '#666' }}
            axisLine={{ stroke: '#2a2a3e' }}
            tickLine={false}
          />
          <YAxis
            tick={{ fontSize: 10, fill: '#666' }}
            axisLine={{ stroke: '#2a2a3e' }}
            tickLine={false}
            width={48}
          />
          <Tooltip
            contentStyle={{ background: '#0f0f1a', border: '1px solid #3a3a5e', borderRadius: 4, fontSize: 12 }}
            labelStyle={{ color: '#888' }}
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

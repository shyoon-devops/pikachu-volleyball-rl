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
    <div className="metrics-chart card">
      <h3 className="metrics-chart-title">{label}</h3>
      <ResponsiveContainer width="100%" height={180}>
        <LineChart data={data} margin={{ top: 4, right: 12, left: 0, bottom: 4 }}>
          <CartesianGrid strokeDasharray="3 3" />
          <XAxis dataKey={xKey} tickLine={false} />
          <YAxis tickLine={false} width={48} />
          <Tooltip />
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

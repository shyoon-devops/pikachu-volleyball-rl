import { BarChart, Bar, XAxis, YAxis, CartesianGrid, Tooltip, ResponsiveContainer, Cell } from 'recharts'
import type { EvalResult } from '../../lib/types'
import './EvalChart.css'

interface EvalChartProps {
  results: EvalResult[]
  filterLevel: number | null
}

const COLORS = ['#22c55e', '#3b82f6', '#a855f7', '#f59e0b', '#ef4444']

export function EvalChart({ results, filterLevel }: EvalChartProps) {
  const filtered = filterLevel !== null
    ? results.filter(r => r.botLevel === filterLevel)
    : results

  const chartData = filtered.map(r => ({
    name: r.modelPath.split('/').pop() ?? r.modelPath,
    winRate: Math.round(r.winRate * 100),
    botLevel: r.botLevel,
  }))

  if (chartData.length === 0) {
    return (
      <div className="eval-chart eval-chart-empty card">
        No evaluation data to display.
      </div>
    )
  }

  return (
    <div className="eval-chart card">
      <h3 className="eval-chart-title">
        Win Rate by Model {filterLevel !== null && `(Level ${filterLevel})`}
      </h3>
      <ResponsiveContainer width="100%" height={280}>
        <BarChart data={chartData} margin={{ top: 4, right: 12, left: 0, bottom: 4 }}>
          <CartesianGrid strokeDasharray="3 3" />
          <XAxis
            dataKey="name"
            tickLine={false}
            angle={-30}
            textAnchor="end"
            height={60}
          />
          <YAxis
            tickLine={false}
            domain={[0, 100]}
            unit="%"
            width={48}
          />
          <Tooltip
            formatter={(value) => [`${value}%`, 'Win Rate']}
          />
          <Bar dataKey="winRate" radius={[4, 4, 0, 0]}>
            {chartData.map((entry, index) => (
              <Cell key={index} fill={COLORS[entry.botLevel - 1] ?? COLORS[0]} />
            ))}
          </Bar>
        </BarChart>
      </ResponsiveContainer>
    </div>
  )
}

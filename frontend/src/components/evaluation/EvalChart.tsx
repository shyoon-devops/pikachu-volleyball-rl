import { BarChart, Bar, XAxis, YAxis, CartesianGrid, Tooltip, ResponsiveContainer, Cell } from 'recharts'
import type { EvalResult } from '../../lib/types'
<<<<<<< HEAD
import './EvalChart.css'
=======
>>>>>>> github/yoon/designer

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
<<<<<<< HEAD
      <div className="eval-chart eval-chart-empty card">
=======
      <div style={{ background: '#1a1a2e', borderRadius: 8, padding: 24, border: '1px solid #2a2a3e', textAlign: 'center', color: '#666', fontSize: 13 }}>
>>>>>>> github/yoon/designer
        No evaluation data to display.
      </div>
    )
  }

  return (
<<<<<<< HEAD
    <div className="eval-chart card">
      <h3 className="eval-chart-title">
=======
    <div style={{ background: '#1a1a2e', borderRadius: 8, padding: '16px 8px 8px', border: '1px solid #2a2a3e' }}>
      <h3 style={{ margin: '0 0 8px 12px', fontSize: 13, color: '#888', fontWeight: 500 }}>
>>>>>>> github/yoon/designer
        Win Rate by Model {filterLevel !== null && `(Level ${filterLevel})`}
      </h3>
      <ResponsiveContainer width="100%" height={280}>
        <BarChart data={chartData} margin={{ top: 4, right: 12, left: 0, bottom: 4 }}>
<<<<<<< HEAD
          <CartesianGrid strokeDasharray="3 3" />
          <XAxis
            dataKey="name"
=======
          <CartesianGrid strokeDasharray="3 3" stroke="#2a2a3e" />
          <XAxis
            dataKey="name"
            tick={{ fontSize: 10, fill: '#666' }}
            axisLine={{ stroke: '#2a2a3e' }}
>>>>>>> github/yoon/designer
            tickLine={false}
            angle={-30}
            textAnchor="end"
            height={60}
          />
          <YAxis
<<<<<<< HEAD
=======
            tick={{ fontSize: 10, fill: '#666' }}
            axisLine={{ stroke: '#2a2a3e' }}
>>>>>>> github/yoon/designer
            tickLine={false}
            domain={[0, 100]}
            unit="%"
            width={48}
          />
          <Tooltip
<<<<<<< HEAD
=======
            contentStyle={{ background: '#0f0f1a', border: '1px solid #3a3a5e', borderRadius: 4, fontSize: 12 }}
>>>>>>> github/yoon/designer
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

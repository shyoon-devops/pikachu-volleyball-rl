import { useState } from 'react'
import type { Hyperparams } from '../../lib/types'
<<<<<<< HEAD
import './HyperparamForm.css'
=======
>>>>>>> github/yoon/designer

interface HyperparamFormProps {
  onSubmit: (params: Hyperparams, botLevel: number) => void
  disabled: boolean
}

const DEFAULTS: Hyperparams = {
  learning_rate: 3e-4,
  n_steps: 2048,
  batch_size: 64,
  gamma: 0.99,
  clip_range: 0.2,
}

<<<<<<< HEAD
=======
const fieldStyle: React.CSSProperties = {
  width: '100%',
  padding: '6px 8px',
  background: '#0f0f1a',
  border: '1px solid #3a3a5e',
  borderRadius: 4,
  color: '#e0e0e0',
  fontFamily: 'monospace',
  fontSize: 12,
}

const labelStyle: React.CSSProperties = {
  fontSize: 11,
  color: '#888',
  display: 'block',
  marginBottom: 2,
}

>>>>>>> github/yoon/designer
export function HyperparamForm({ onSubmit, disabled }: HyperparamFormProps) {
  const [params, setParams] = useState<Hyperparams>(DEFAULTS)
  const [botLevel, setBotLevel] = useState(1)

  const handleChange = (key: keyof Hyperparams, value: string) => {
    const num = Number(value)
    if (!Number.isNaN(num)) {
      setParams(prev => ({ ...prev, [key]: num }))
    }
  }

  const handleSubmit = (e: React.FormEvent) => {
    e.preventDefault()
    onSubmit(params, botLevel)
  }

  return (
<<<<<<< HEAD
    <form onSubmit={handleSubmit} className="hyperparam-form card">
      <h3 className="hyperparam-form-title">Hyperparameters</h3>

      <div className="hyperparam-form-grid">
        {(Object.keys(DEFAULTS) as Array<keyof Hyperparams>).map(key => (
          <div key={key}>
            <label className="hyperparam-form-label">{key}</label>
=======
    <form
      onSubmit={handleSubmit}
      style={{ background: '#1a1a2e', borderRadius: 8, padding: 16, border: '1px solid #2a2a3e' }}
    >
      <h3 style={{ margin: '0 0 12px', fontSize: 14, color: '#ccc' }}>Hyperparameters</h3>

      <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 8, marginBottom: 12 }}>
        {(Object.keys(DEFAULTS) as Array<keyof Hyperparams>).map(key => (
          <div key={key}>
            <label style={labelStyle}>{key}</label>
>>>>>>> github/yoon/designer
            <input
              type="number"
              step="any"
              value={params[key]}
              onChange={e => handleChange(key, e.target.value)}
<<<<<<< HEAD
              className="hyperparam-form-input"
=======
              style={fieldStyle}
>>>>>>> github/yoon/designer
              disabled={disabled}
            />
          </div>
        ))}
        <div>
<<<<<<< HEAD
          <label className="hyperparam-form-label">bot_level</label>
          <select
            value={botLevel}
            onChange={e => setBotLevel(Number(e.target.value))}
            className="hyperparam-form-select"
=======
          <label style={labelStyle}>bot_level</label>
          <select
            value={botLevel}
            onChange={e => setBotLevel(Number(e.target.value))}
            style={fieldStyle}
>>>>>>> github/yoon/designer
            disabled={disabled}
          >
            {[1, 2, 3, 4, 5].map(l => (
              <option key={l} value={l}>Level {l}</option>
            ))}
          </select>
        </div>
      </div>

<<<<<<< HEAD
      <button type="submit" disabled={disabled} className="hyperparam-form-submit">
=======
      <button
        type="submit"
        disabled={disabled}
        style={{
          width: '100%',
          padding: '8px 16px',
          border: 'none',
          borderRadius: 6,
          background: disabled ? '#2a2a3e' : '#22c55e',
          color: disabled ? '#666' : '#000',
          fontFamily: 'monospace',
          fontSize: 13,
          fontWeight: 600,
          cursor: disabled ? 'not-allowed' : 'pointer',
        }}
      >
>>>>>>> github/yoon/designer
        Start Training
      </button>
    </form>
  )
}

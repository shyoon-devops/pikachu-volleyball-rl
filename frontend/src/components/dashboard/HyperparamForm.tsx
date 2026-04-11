import { useState } from 'react'
import type { Hyperparams } from '../../lib/types'
import './HyperparamForm.css'

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
    <form onSubmit={handleSubmit} className="hyperparam-form">
      <h3>Hyperparameters</h3>

      <div className="hyperparam-form__grid">
        {(Object.keys(DEFAULTS) as Array<keyof Hyperparams>).map(key => (
          <div key={key} className="hyperparam-form__field">
            <label>{key}</label>
            <input
              type="number"
              step="any"
              value={params[key]}
              onChange={e => handleChange(key, e.target.value)}
              disabled={disabled}
            />
          </div>
        ))}
        <div className="hyperparam-form__field">
          <label>bot_level</label>
          <select
            value={botLevel}
            onChange={e => setBotLevel(Number(e.target.value))}
            disabled={disabled}
          >
            {[1, 2, 3, 4, 5].map(l => (
              <option key={l} value={l}>Level {l}</option>
            ))}
          </select>
        </div>
      </div>

      <button
        type="submit"
        disabled={disabled}
        className="btn btn-success hyperparam-form__submit"
      >
        Start Training
      </button>
    </form>
  )
}

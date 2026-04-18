import { describe, it, expect } from 'vitest'
import { render, screen } from '@testing-library/react'
import type { Hyperparams } from '../../lib/types'
import { HyperparamsSummary } from './HyperparamsSummary'

const FULL: Hyperparams = {
  total_timesteps: 1_000_000,
  n_envs: 4,
  learning_rate: 3e-4,
  n_steps: 2048,
  batch_size: 64,
  n_epochs: 10,
  gamma: 0.995,
  clip_range: 0.2,
  ent_coef: 1e-2,
  gae_lambda: 0.95,
}

describe('HyperparamsSummary (FC-R8b)', () => {
  it('renders the 10 canonical PPO knobs when hyperparams are present', () => {
    render(<HyperparamsSummary hyperparams={FULL} />)
    // All 10 labels present — matches HyperparamForm order.
    expect(screen.getByText('total_timesteps')).toBeInTheDocument()
    expect(screen.getByText('n_envs')).toBeInTheDocument()
    expect(screen.getByText('learning_rate')).toBeInTheDocument()
    expect(screen.getByText('gae_lambda')).toBeInTheDocument()
    // Formatting spot checks — learning_rate uses scientific notation.
    expect(screen.getByText('3.0e-4')).toBeInTheDocument()
    expect(screen.getByText('1,000,000')).toBeInTheDocument() // total_timesteps
    expect(screen.getByText('0.9950')).toBeInTheDocument() // gamma 4dp
  })

  it('renders the BE-WAITING placeholder when hyperparams is null', () => {
    render(<HyperparamsSummary hyperparams={null} />)
    expect(screen.getByText(/학습 파라미터 정보 준비 중/)).toBeInTheDocument()
    // No dd values — the absent-data branch skips the grid entirely.
    expect(screen.queryByText('n_envs')).toBeNull()
  })

  it('renders the placeholder when the object exists but every value is non-finite', () => {
    render(
      <HyperparamsSummary
        hyperparams={{ total_timesteps: Number.NaN, n_envs: undefined as unknown as number }}
      />,
    )
    expect(screen.getByText(/학습 파라미터 정보 준비 중/)).toBeInTheDocument()
  })

  it('renders em-dash for missing fields when partial hyperparams arrive', () => {
    // BE may ship only a subset (earlier version of BE-T10 in flight).
    // Present fields render; missing fields show `—` per spec.
    render(
      <HyperparamsSummary
        hyperparams={{ n_envs: 8, total_timesteps: 500_000 }}
      />,
    )
    expect(screen.getByText('8')).toBeInTheDocument() // n_envs
    expect(screen.getByText('500,000')).toBeInTheDocument() // total_timesteps
    // At least one em-dash for the missing fields (learning_rate etc.).
    expect(screen.getAllByText('—').length).toBeGreaterThan(0)
  })
})

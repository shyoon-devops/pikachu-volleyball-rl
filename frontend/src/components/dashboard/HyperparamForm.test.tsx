import { describe, it, expect, vi } from 'vitest'
import { render, screen, fireEvent } from '@testing-library/react'
import { HyperparamForm } from './HyperparamForm'
import { DEFAULT_HYPERPARAMS } from './hyperparamDefaults'

function renderForm(overrides: {
  disabled?: boolean
  botLevel?: number
} = {}) {
  const onParamsChange = vi.fn()
  const onBotLevelChange = vi.fn()

  render(
    <HyperparamForm
      params={DEFAULT_HYPERPARAMS}
      botLevel={overrides.botLevel ?? 1}
      onParamsChange={onParamsChange}
      onBotLevelChange={onBotLevelChange}
      disabled={overrides.disabled ?? false}
    />,
  )

  return { onParamsChange, onBotLevelChange }
}

describe('HyperparamForm', () => {
  it('renders the title', () => {
    renderForm()
    expect(screen.getByRole('heading', { name: /hyperparameters/i })).toBeInTheDocument()
  })

  it('does NOT render a Start/Submit button (duplicate-CTA regression guard)', () => {
    renderForm()
    // Zero buttons: all CTA lives in TrainingControls now. The word
    // "Start" may appear in the hint text — that's fine, it's a hint,
    // not a button.
    expect(screen.queryByRole('button')).not.toBeInTheDocument()
    expect(screen.queryByRole('button', { name: /start training/i })).not.toBeInTheDocument()
  })

  it('renders an input for each hyperparameter', () => {
    renderForm()
    expect(screen.getByLabelText('learning_rate')).toBeInTheDocument()
    expect(screen.getByLabelText('n_steps')).toBeInTheDocument()
    expect(screen.getByLabelText('batch_size')).toBeInTheDocument()
    expect(screen.getByLabelText('gamma')).toBeInTheDocument()
    expect(screen.getByLabelText('clip_range')).toBeInTheDocument()
  })

  it('emits onParamsChange when a field is edited', () => {
    const { onParamsChange } = renderForm()
    const input = screen.getByLabelText('batch_size') as HTMLInputElement
    fireEvent.change(input, { target: { value: '128' } })
    expect(onParamsChange).toHaveBeenCalledWith(
      expect.objectContaining({ batch_size: 128 }),
    )
  })


  it('emits onBotLevelChange when the select changes', () => {
    const { onBotLevelChange } = renderForm()
    const select = screen.getByLabelText('bot_level') as HTMLSelectElement
    fireEvent.change(select, { target: { value: '4' } })
    expect(onBotLevelChange).toHaveBeenCalledWith(4)
  })

  it('disables all inputs when disabled=true', () => {
    renderForm({ disabled: true })
    expect(screen.getByLabelText('learning_rate')).toBeDisabled()
    expect(screen.getByLabelText('bot_level')).toBeDisabled()
  })

  it('points the user to the Start button with a hint', () => {
    renderForm()
    // Text is broken by a <strong>, so match on a stable suffix.
    expect(screen.getByText(/above to begin training/i)).toBeInTheDocument()
  })
})

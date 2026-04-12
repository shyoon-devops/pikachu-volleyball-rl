import { describe, it, expect, vi } from 'vitest'
import { render, screen, fireEvent } from '@testing-library/react'
import { HyperparamForm } from './HyperparamForm'
import { DEFAULT_HYPERPARAMS } from './hyperparamDefaults'

function renderForm(overrides: { disabled?: boolean } = {}) {
  const onParamsChange = vi.fn()

  render(
    <HyperparamForm
      params={DEFAULT_HYPERPARAMS}
      onParamsChange={onParamsChange}
      disabled={overrides.disabled ?? false}
    />,
  )

  return { onParamsChange }
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

  it('does NOT render a bot_level control (Option A — single source is TrainingControls)', () => {
    renderForm()
    // The old duplicated dropdown was the root cause of the two-source
    // bot-level inconsistency: picking L5 on TrainingControls could be
    // silently overwritten by starting training with this form's L1
    // default. Removing it is the fix — guard against re-introduction.
    expect(screen.queryByLabelText('bot_level')).not.toBeInTheDocument()
    expect(screen.queryByRole('combobox')).not.toBeInTheDocument()
  })

  it('disables all hyperparam inputs when disabled=true', () => {
    renderForm({ disabled: true })
    expect(screen.getByLabelText('learning_rate')).toBeDisabled()
    expect(screen.getByLabelText('n_steps')).toBeDisabled()
    expect(screen.getByLabelText('batch_size')).toBeDisabled()
    expect(screen.getByLabelText('gamma')).toBeDisabled()
    expect(screen.getByLabelText('clip_range')).toBeDisabled()
  })

  it('points the user to the Start button with a hint', () => {
    renderForm()
    // Text is broken by <strong> tags, so match on stable fragments.
    expect(screen.getByText(/above to begin training/i)).toBeInTheDocument()
  })

  it('tells the user where bot level is picked (single source of truth)', () => {
    renderForm()
    // Hint must point at the L1–L5 buttons rather than a dropdown in
    // this form — so the user doesn't hunt for a missing control.
    expect(screen.getByText(/L1.?L5/)).toBeInTheDocument()
  })
})

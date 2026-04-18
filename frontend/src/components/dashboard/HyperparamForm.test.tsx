import { describe, it, expect, vi } from 'vitest'
import { render, screen, fireEvent, within } from '@testing-library/react'
import { HyperparamForm } from './HyperparamForm'
import { DEFAULT_HYPERPARAMS } from './hyperparamDefaults'

// getTrainingTitles is mocked so TitleInput's debounced dup-check
// doesn't fire real network during tests (jsdom's fetch is a stub).
vi.mock('../../lib/api', () => ({
  getTrainingTitles: vi.fn().mockResolvedValue([]),
}))

function renderForm(overrides: { disabled?: boolean; title?: string } = {}) {
  const onParamsChange = vi.fn()
  const onTitleChange = vi.fn()
  const onTitleValidationChange = vi.fn()

  render(
    <HyperparamForm
      params={DEFAULT_HYPERPARAMS}
      onParamsChange={onParamsChange}
      disabled={overrides.disabled ?? false}
      title={overrides.title ?? ''}
      onTitleChange={onTitleChange}
      onTitleValidationChange={onTitleValidationChange}
    />,
  )

  return { onParamsChange, onTitleChange, onTitleValidationChange }
}

function expandAdvanced() {
  fireEvent.click(screen.getByRole('button', { name: /Advanced/ }))
}

/**
 * Label-text matcher — FC-R5 labels are two spans: the name and a
 * "(default: X)" meta suffix. We match on the mono-styled name span
 * prefix so each test doesn't have to encode the current default
 * value inline.
 */
const byLabelPrefix = (prefix: string) =>
  screen.getByLabelText(new RegExp(`^${prefix}\\b`))

describe('HyperparamForm', () => {
  it('renders the title', () => {
    renderForm()
    expect(screen.getByRole('heading', { name: /hyperparameters/i })).toBeInTheDocument()
  })

  it('does NOT render a Start/Submit button (duplicate-CTA regression guard)', () => {
    renderForm()
    // The only buttons present are the Advanced expand/collapse chevron
    // and the per-group "Reset to defaults" links — neither is a
    // training-start CTA. Lock that in by matching names.
    expect(screen.queryByRole('button', { name: /start training/i })).not.toBeInTheDocument()
    expect(screen.queryByRole('button', { name: /^start$/i })).not.toBeInTheDocument()
  })

  it('renders every Basic-group input without expanding Advanced', () => {
    renderForm()
    // Basic: total_timesteps (slider), n_envs, learning_rate, n_steps,
    // batch_size. All are visible on first render (Basic is always open).
    expect(byLabelPrefix('total_timesteps')).toBeInTheDocument()
    expect(byLabelPrefix('n_envs')).toBeInTheDocument()
    expect(byLabelPrefix('learning_rate')).toBeInTheDocument()
    expect(byLabelPrefix('n_steps')).toBeInTheDocument()
    expect(byLabelPrefix('batch_size')).toBeInTheDocument()
  })

  it('hides Advanced-group inputs until the chevron is clicked', () => {
    renderForm()
    // Initially collapsed: advanced fields not in the DOM.
    expect(screen.queryByLabelText(/^n_epochs\b/)).not.toBeInTheDocument()
    expect(screen.queryByLabelText(/^gamma\b/)).not.toBeInTheDocument()
    expect(screen.queryByLabelText(/^ent_coef\b/)).not.toBeInTheDocument()

    expandAdvanced()

    expect(byLabelPrefix('n_epochs')).toBeInTheDocument()
    expect(byLabelPrefix('gamma')).toBeInTheDocument()
    expect(byLabelPrefix('clip_range')).toBeInTheDocument()
    expect(byLabelPrefix('ent_coef')).toBeInTheDocument()
    expect(byLabelPrefix('gae_lambda')).toBeInTheDocument()
  })

  it('emits onParamsChange when a field is edited', () => {
    const { onParamsChange } = renderForm()
    const input = byLabelPrefix('batch_size') as HTMLInputElement
    fireEvent.change(input, { target: { value: '128' } })
    expect(onParamsChange).toHaveBeenCalledWith(
      expect.objectContaining({ batch_size: 128 }),
    )
  })

  it('does NOT render a bot_level control (Option A — single source is TrainingControls)', () => {
    renderForm()
    expect(screen.queryByLabelText(/^bot_level\b/)).not.toBeInTheDocument()
    expect(screen.queryByRole('combobox')).not.toBeInTheDocument()
  })

  it('disables all hyperparam inputs when disabled=true', () => {
    renderForm({ disabled: true })
    expect(byLabelPrefix('learning_rate')).toBeDisabled()
    expect(byLabelPrefix('n_steps')).toBeDisabled()
    expect(byLabelPrefix('batch_size')).toBeDisabled()
    expect(byLabelPrefix('total_timesteps')).toBeDisabled()
    expect(byLabelPrefix('n_envs')).toBeDisabled()
  })

  it('points the user to the Start button with a hint', () => {
    renderForm()
    expect(screen.getByText(/above to begin training/i)).toBeInTheDocument()
  })

  it('tells the user where bot level is picked (single source of truth)', () => {
    renderForm()
    expect(screen.getByText(/L1.?L5/)).toBeInTheDocument()
  })

  // FC-R5 additions.
  it('shows the "(default: X)" meta next to each label', () => {
    renderForm()
    // `batch_size` default = 64 per DEFAULT_HYPERPARAMS_EXTENDED.
    const label = document.querySelector('label[for="hyperparam-batch_size"]')
    expect(label?.textContent ?? '').toMatch(/\(default:\s*64\)/)
  })

  it('renders a slider control for total_timesteps (spec §3)', () => {
    renderForm()
    const el = byLabelPrefix('total_timesteps')
    expect(el.getAttribute('type')).toBe('range')
  })

  it('renders a slider control for ent_coef after expanding Advanced', () => {
    renderForm()
    expandAdvanced()
    const el = byLabelPrefix('ent_coef')
    expect(el.getAttribute('type')).toBe('range')
  })

  it('flags out-of-range values with aria-invalid + a visible error', () => {
    const onParamsChange = vi.fn()
    render(
      <HyperparamForm
        params={{ ...DEFAULT_HYPERPARAMS, n_envs: 100 }}
        onParamsChange={onParamsChange}
        disabled={false}
        title=""
        onTitleChange={vi.fn()}
        onTitleValidationChange={vi.fn()}
      />,
    )
    const input = byLabelPrefix('n_envs')
    expect(input.getAttribute('aria-invalid')).toBe('true')
    // The error message cites the field's declared range.
    expect(screen.getByText(/Range:\s*1.+32/)).toBeInTheDocument()
  })

  it('"Reset to defaults" restores the group without touching the other group', () => {
    const onParamsChange = vi.fn()
    render(
      <HyperparamForm
        params={{ ...DEFAULT_HYPERPARAMS, batch_size: 999, n_epochs: 25 }}
        onParamsChange={onParamsChange}
        disabled={false}
        title=""
        onTitleChange={vi.fn()}
        onTitleValidationChange={vi.fn()}
      />,
    )
    // Basic reset button lives alongside its "BASIC" heading.
    const basicGroup = document.querySelector('[aria-labelledby="hyperparam-group-basic"]')!
    fireEvent.click(within(basicGroup as HTMLElement).getByRole('button', { name: /Reset to defaults/ }))
    // Only basic fields reset; n_epochs left alone.
    expect(onParamsChange).toHaveBeenCalledWith(
      expect.objectContaining({
        batch_size: DEFAULT_HYPERPARAMS.batch_size,
        n_epochs: 25, // unchanged
      }),
    )
  })
})

import { describe, it, expect, vi } from 'vitest'
import { render, screen, fireEvent, within } from '@testing-library/react'
import { HyperparamForm } from './HyperparamForm'
import { DEFAULT_HYPERPARAMS } from './hyperparamDefaults'
import type { LeagueSampling, PolicyType, RewardModel, TrainingMode } from '../../lib/types'

// getTrainingTitles is mocked so TitleInput's debounced dup-check
// doesn't fire real network during tests (jsdom's fetch is a stub).
vi.mock('../../lib/api', () => ({
  getTrainingTitles: vi.fn().mockResolvedValue([]),
}))

function renderForm(overrides: {
  disabled?: boolean
  title?: string
  opponentMode?: TrainingMode
  samplingStrategy?: LeagueSampling
  leaguePoolSize?: number | null
  rewardModel?: RewardModel
  policyType?: PolicyType
} = {}) {
  const onParamsChange = vi.fn()
  const onTitleChange = vi.fn()
  const onTitleValidationChange = vi.fn()
  const onOpponentModeChange = vi.fn()
  const onSamplingStrategyChange = vi.fn()
  const onRewardModelChange = vi.fn()
  const onPolicyTypeChange = vi.fn()

  render(
    <HyperparamForm
      params={DEFAULT_HYPERPARAMS}
      onParamsChange={onParamsChange}
      disabled={overrides.disabled ?? false}
      title={overrides.title ?? ''}
      onTitleChange={onTitleChange}
      onTitleValidationChange={onTitleValidationChange}
      opponentMode={overrides.opponentMode ?? 'bot_ladder'}
      onOpponentModeChange={onOpponentModeChange}
      samplingStrategy={overrides.samplingStrategy ?? 'pfsp'}
      onSamplingStrategyChange={onSamplingStrategyChange}
      leaguePoolSize={overrides.leaguePoolSize ?? null}
      rewardModel={overrides.rewardModel ?? 'shaped_v1'}
      onRewardModelChange={onRewardModelChange}
      policyType={overrides.policyType ?? 'mlp_v1'}
      onPolicyTypeChange={onPolicyTypeChange}
    />,
  )

  return {
    onParamsChange,
    onTitleChange,
    onTitleValidationChange,
    onOpponentModeChange,
    onSamplingStrategyChange,
    onRewardModelChange,
    onPolicyTypeChange,
  }
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
    // Narrow to the hint paragraph — "L1–L5" now also appears in the
    // Opponent section's "Rule-based (L1–L5)" segmented option.
    expect(screen.getByText(/Bot level is picked/)).toBeInTheDocument()
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
        opponentMode="bot_ladder"
        onOpponentModeChange={vi.fn()}
        samplingStrategy="pfsp"
        onSamplingStrategyChange={vi.fn()}
        leaguePoolSize={null}
        rewardModel="shaped_v1"
        onRewardModelChange={vi.fn()}
        policyType="mlp_v1"
        onPolicyTypeChange={vi.fn()}
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
        opponentMode="bot_ladder"
        onOpponentModeChange={vi.fn()}
        samplingStrategy="pfsp"
        onSamplingStrategyChange={vi.fn()}
        leaguePoolSize={null}
        rewardModel="shaped_v1"
        onRewardModelChange={vi.fn()}
        policyType="mlp_v1"
        onPolicyTypeChange={vi.fn()}
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

// v2.x Sprint 1 — Opponent section (docs/design/SELF-PLAY-UX.md §1)
describe('HyperparamForm — Opponent section (v2.x)', () => {
  it('renders the segmented Rule-based vs Self-play control', () => {
    renderForm()
    expect(screen.getByRole('radio', { name: /Rule-based/ })).toBeInTheDocument()
    expect(screen.getByRole('radio', { name: /Self-play league/ })).toBeInTheDocument()
  })

  it('hides the sampling radios + pool chip when mode is bot_ladder', () => {
    renderForm({ opponentMode: 'bot_ladder' })
    expect(screen.queryByRole('radio', { name: /PFSP/ })).toBeNull()
    expect(screen.queryByLabelText(/Pool size/)).toBeNull()
  })

  it('reveals sampling radios + pool chip when mode is self_play', () => {
    renderForm({ opponentMode: 'self_play', leaguePoolSize: 12 })
    expect(screen.getByRole('radio', { name: /PFSP/ })).toBeInTheDocument()
    expect(screen.getByRole('radio', { name: /Elo proximity/ })).toBeInTheDocument()
    expect(screen.getByRole('radio', { name: /Uniform/ })).toBeInTheDocument()
    expect(screen.getByLabelText('Pool size: 12 of 32')).toBeInTheDocument()
  })

  it('pool chip reads "— / 32" until the standings fetch lands', () => {
    renderForm({ opponentMode: 'self_play', leaguePoolSize: null })
    expect(screen.getByLabelText('Pool size: unknown of 32')).toBeInTheDocument()
  })

  it('clicking the Self-play segment fires onOpponentModeChange("self_play")', () => {
    const { onOpponentModeChange } = renderForm({ opponentMode: 'bot_ladder' })
    fireEvent.click(screen.getByRole('radio', { name: /Self-play league/ }))
    expect(onOpponentModeChange).toHaveBeenCalledWith('self_play')
  })

  it('selecting a sampling radio fires onSamplingStrategyChange', () => {
    const { onSamplingStrategyChange } = renderForm({
      opponentMode: 'self_play',
      samplingStrategy: 'pfsp',
      leaguePoolSize: 0,
    })
    fireEvent.click(screen.getByRole('radio', { name: /Uniform/ }))
    expect(onSamplingStrategyChange).toHaveBeenCalledWith('uniform')
  })

  it('fallback hint is surfaced in self-play branch so users know empty pools degrade cleanly', () => {
    renderForm({ opponentMode: 'self_play', leaguePoolSize: 0 })
    expect(screen.getByText(/auto-falls back to rule ladder/i)).toBeInTheDocument()
  })
})

// v2.x Sprint 2 — Reward-model selector
// (docs/design/DESIGN-REWARD-MODEL-SELECTOR.md §1, ADR 0015).
describe('HyperparamForm — Reward-model selector (v2.x Sprint 2)', () => {
  it('renders the three options as a radiogroup with Recommended + Experimental badges', () => {
    renderForm()
    const shaped = screen.getByRole('radio', { name: /Shaped \(v1\)/ })
    const sparse = screen.getByRole('radio', { name: /^Sparse/ })
    const learned = screen.getByRole('radio', { name: /Learned shaped/ })
    expect(shaped).toBeInTheDocument()
    expect(sparse).toBeInTheDocument()
    expect(learned).toBeInTheDocument()
    // shaped_v1 is the default, so it's the checked radio.
    expect(shaped.getAttribute('aria-checked')).toBe('true')
    // Badges resolve via i18n. "Recommended" appears twice once
    // the policy selector lands (reward + policy share the badge);
    // "Experimental" is reward-only.
    expect(screen.getAllByText('Recommended').length).toBeGreaterThanOrEqual(1)
    expect(screen.getByText('Experimental')).toBeInTheDocument()
  })

  it('clicking a non-default option fires onRewardModelChange with the enum value', () => {
    const { onRewardModelChange } = renderForm()
    fireEvent.click(screen.getByRole('radio', { name: /Learned shaped/ }))
    expect(onRewardModelChange).toHaveBeenCalledWith('learned_shaped_v1')
  })

  it('disables every option when the form is disabled', () => {
    renderForm({ disabled: true })
    const radios = screen.getAllByRole('radio', { name: /(Shaped \(v1\)|^Sparse|Learned shaped)/ })
    expect(radios).toHaveLength(3)
    for (const r of radios) {
      expect((r as HTMLButtonElement).disabled).toBe(true)
    }
  })
})

// v2.x Sprint 3 — Policy-type selector
// (docs/design/DESIGN-POLICY-TYPE-SELECTOR.md §1, ADR 0016).
describe('HyperparamForm — Policy-type selector (v2.x Sprint 3)', () => {
  it('renders the four options with Recommended + Coming soon badges', () => {
    renderForm()
    const mlp = screen.getByRole('radio', { name: /MLP \(v1\)/ })
    const lstm = screen.getByRole('radio', { name: /^LSTM/ })
    const gru = screen.getByRole('radio', { name: /^GRU/ })
    const transformer = screen.getByRole('radio', { name: /^Transformer/ })
    expect(mlp).toBeInTheDocument()
    expect(lstm).toBeInTheDocument()
    expect(gru).toBeInTheDocument()
    expect(transformer).toBeInTheDocument()
    expect(mlp.getAttribute('aria-checked')).toBe('true')
    // Coming soon badge appears twice (gru + transformer); Recommended
    // appears for both reward (Shaped) and policy (MLP) selectors —
    // we only assert presence of "Coming soon" since it's policy-only.
    expect(screen.getAllByText('Coming soon')).toHaveLength(2)
  })

  it('marks reserved cells (gru / transformer) as disabled', () => {
    renderForm()
    const gru = screen.getByRole('radio', { name: /^GRU/ }) as HTMLButtonElement
    const transformer = screen.getByRole('radio', { name: /^Transformer/ }) as HTMLButtonElement
    expect(gru.disabled).toBe(true)
    expect(transformer.disabled).toBe(true)
  })

  it('clicking LSTM fires onPolicyTypeChange("lstm_v1")', () => {
    const { onPolicyTypeChange } = renderForm()
    fireEvent.click(screen.getByRole('radio', { name: /^LSTM/ }))
    expect(onPolicyTypeChange).toHaveBeenCalledWith('lstm_v1')
  })

  it('clicking a reserved cell does not fire onPolicyTypeChange', () => {
    const { onPolicyTypeChange } = renderForm()
    fireEvent.click(screen.getByRole('radio', { name: /^GRU/ }))
    fireEvent.click(screen.getByRole('radio', { name: /^Transformer/ }))
    expect(onPolicyTypeChange).not.toHaveBeenCalled()
  })

  it('disables every option when the form is disabled', () => {
    renderForm({ disabled: true })
    const policyRadios = [
      screen.getByRole('radio', { name: /MLP \(v1\)/ }),
      screen.getByRole('radio', { name: /^LSTM/ }),
      screen.getByRole('radio', { name: /^GRU/ }),
      screen.getByRole('radio', { name: /^Transformer/ }),
    ]
    for (const r of policyRadios) {
      expect((r as HTMLButtonElement).disabled).toBe(true)
    }
  })
})

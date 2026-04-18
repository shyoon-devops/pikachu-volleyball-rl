import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest'
import { render, screen, fireEvent, waitFor } from '@testing-library/react'
import { TitleInput, type TitleValidationState } from './TitleInput'

const getTrainingTitles = vi.fn<(q?: string, limit?: number) => Promise<Array<{
  title: string; experimentId: string; startedAt: string | null
}>>>()
vi.mock('../../lib/api', () => ({
  getTrainingTitles: (q?: string, limit?: number) => getTrainingTitles(q, limit),
}))

function renderInput(overrides: { value?: string; disabled?: boolean } = {}) {
  const onChange = vi.fn()
  const onValidationChange = vi.fn<(s: TitleValidationState) => void>()
  const utils = render(
    <TitleInput
      value={overrides.value ?? ''}
      onChange={onChange}
      disabled={overrides.disabled ?? false}
      onValidationChange={onValidationChange}
    />,
  )
  return { ...utils, onChange, onValidationChange }
}

beforeEach(() => {
  getTrainingTitles.mockReset()
  getTrainingTitles.mockResolvedValue([])
})

afterEach(() => {
  vi.restoreAllMocks()
})

describe('TitleInput (FC-R6G)', () => {
  it('renders the label, placeholder, and optional-hint', () => {
    renderInput()
    expect(screen.getByLabelText('Title')).toBeInTheDocument()
    expect(screen.getByPlaceholderText('예: my-run-baseline')).toBeInTheDocument()
    expect(screen.getByText(/비워두면 자동으로 이름이 생성됩니다/)).toBeInTheDocument()
  })

  it('treats empty + whitespace-only as the auto-gen path (validation ok)', async () => {
    const { onValidationChange } = renderInput({ value: '   ' })
    await waitFor(() => {
      expect(onValidationChange).toHaveBeenLastCalledWith({ kind: 'ok' })
    })
    // No dup check fired for whitespace-only.
    expect(getTrainingTitles).not.toHaveBeenCalled()
  })

  it('hides the counter while the input is empty (spec §1)', () => {
    const { rerender } = renderInput({ value: '' })
    // No "/ 60" text while empty.
    expect(screen.queryByText(/\/ 60/)).not.toBeInTheDocument()
    rerender(
      <TitleInput
        value="hello"
        onChange={vi.fn()}
        disabled={false}
        onValidationChange={vi.fn()}
      />,
    )
    // Counter appears once the user types.
    expect(screen.getByText(/5 \/ 60/)).toBeInTheDocument()
  })

  it('flags length > 60 with the tooLong error and blocks submit', async () => {
    const longStr = 'a'.repeat(61)
    const { onValidationChange } = renderInput({ value: longStr })
    await waitFor(() => {
      expect(onValidationChange).toHaveBeenLastCalledWith({ kind: 'tooLong' })
    })
    expect(screen.getByText('최대 60자')).toBeInTheDocument()
    // 61/60 counter turned danger — locked in via `--over` class.
    const counter = screen.getByText(/61 \/ 60/)
    expect(counter.className).toContain('title-input-counter--over')
  })

  it('runs debounced dup-check only for non-empty input, reports duplicate', async () => {
    getTrainingTitles.mockResolvedValueOnce([
      { title: 'run-existing', experimentId: 'exp-1', startedAt: '2026-04-17T12:00:00Z' },
    ])
    const { onValidationChange } = renderInput({ value: 'run-existing' })
    await waitFor(
      () => expect(getTrainingTitles).toHaveBeenCalledWith('run-existing', 20),
      { timeout: 800 },
    )
    await waitFor(
      () => expect(onValidationChange).toHaveBeenLastCalledWith(
        expect.objectContaining({ kind: 'duplicate' }),
      ),
      { timeout: 1500 },
    )
    expect(screen.getByText(/이미 존재하는 제목/)).toBeInTheDocument()
  })

  it('degrades to ok when the titles endpoint rejects (submit allowed)', async () => {
    getTrainingTitles.mockRejectedValueOnce(new Error('titles endpoint down'))
    const { onValidationChange } = renderInput({ value: 'run-new' })
    await waitFor(
      () => expect(onValidationChange).toHaveBeenLastCalledWith({ kind: 'ok' }),
      { timeout: 1500 },
    )
  })

  it('emits onChange on every keystroke', () => {
    const { onChange } = renderInput({ value: '' })
    const input = screen.getByLabelText('Title')
    fireEvent.change(input, { target: { value: 'r' } })
    expect(onChange).toHaveBeenCalledWith('r')
  })

  it('disables the input when the disabled prop is true', () => {
    renderInput({ disabled: true, value: '' })
    expect(screen.getByLabelText('Title')).toBeDisabled()
  })
})

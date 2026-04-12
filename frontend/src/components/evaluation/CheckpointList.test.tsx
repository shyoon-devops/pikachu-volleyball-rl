import { describe, it, expect, vi } from 'vitest'
import { render, screen, fireEvent, within } from '@testing-library/react'
import { CheckpointList } from './CheckpointList'
import type { ModelInfo } from '../../lib/types'

const MODELS: ModelInfo[] = [
  { path: 'ppo/ppo_100000.zip', sizeBytes: 512 * 1024 },            // 512 KB
  { path: 'ppo/ppo_2048.zip', sizeBytes: 2 * 1024 * 1024 },         // 2 MB — short digit run
  { path: 'run_b/model_step=500000.zip', sizeBytes: 1_500_000_000 }, // ~1.4 GB
  { path: 'lonely.zip', sizeBytes: 900 },                           // bytes, no dir, no step
]

describe('CheckpointList', () => {
  it('renders one item per model', () => {
    render(
      <CheckpointList models={MODELS} selectedPath="" onSelect={vi.fn()} />,
    )
    expect(screen.getAllByRole('radio')).toHaveLength(MODELS.length)
  })

  it('uses a radiogroup role with an accessible label', () => {
    render(
      <CheckpointList models={MODELS} selectedPath="" onSelect={vi.fn()} />,
    )
    const group = screen.getByRole('radiogroup', { name: /model checkpoints/i })
    expect(group).toBeInTheDocument()
  })

  it('renders the empty state when no models are available', () => {
    render(
      <CheckpointList models={[]} selectedPath="" onSelect={vi.fn()} />,
    )
    expect(screen.getByText(/No checkpoints found/i)).toBeInTheDocument()
    expect(screen.queryByRole('radio')).not.toBeInTheDocument()
  })

  it('shows the checkpoint count, singular/plural aware', () => {
    const { rerender } = render(
      <CheckpointList models={MODELS} selectedPath="" onSelect={vi.fn()} />,
    )
    expect(screen.getByText(`${MODELS.length} checkpoints`)).toBeInTheDocument()

    rerender(
      <CheckpointList models={[MODELS[0]]} selectedPath="" onSelect={vi.fn()} />,
    )
    expect(screen.getByText('1 checkpoint')).toBeInTheDocument()
  })

  it('marks the selected model via checked radio and is-selected class', () => {
    render(
      <CheckpointList
        models={MODELS}
        selectedPath={MODELS[1].path}
        onSelect={vi.fn()}
      />,
    )
    const radios = screen.getAllByRole('radio') as HTMLInputElement[]
    const checked = radios.filter(r => r.checked)
    expect(checked).toHaveLength(1)
    expect(checked[0].value).toBe(MODELS[1].path)

    // The wrapping label gets the marker class
    const label = checked[0].closest('label')
    expect(label).not.toBeNull()
    expect(label?.className).toContain('is-selected')
    expect(label?.getAttribute('data-selected')).toBe('true')
  })

  it('calls onSelect with the model path when an item is clicked', () => {
    const onSelect = vi.fn()
    render(
      <CheckpointList
        models={MODELS}
        selectedPath=""
        onSelect={onSelect}
      />,
    )
    const radios = screen.getAllByRole('radio')
    fireEvent.click(radios[2]) // third model
    expect(onSelect).toHaveBeenCalledWith(MODELS[2].path)
  })

  it('disables every radio when `disabled` is true', () => {
    render(
      <CheckpointList
        models={MODELS}
        selectedPath=""
        onSelect={vi.fn()}
        disabled
      />,
    )
    for (const radio of screen.getAllByRole('radio')) {
      expect(radio).toBeDisabled()
    }
  })

  it('formats sizes across B / KB / MB / GB ranges', () => {
    render(
      <CheckpointList models={MODELS} selectedPath="" onSelect={vi.fn()} />,
    )
    // 900 B
    expect(screen.getByText('900 B')).toBeInTheDocument()
    // 512 KB
    expect(screen.getByText('512.0 KB')).toBeInTheDocument()
    // 2 MB
    expect(screen.getByText('2.0 MB')).toBeInTheDocument()
    // ~1.4 GB
    expect(screen.getByText(/^1\.\d{2} GB$/)).toBeInTheDocument()
  })

  it('parses step counts out of filenames like ppo_100000.zip and model_step=500000.zip', () => {
    render(
      <CheckpointList models={MODELS} selectedPath="" onSelect={vi.fn()} />,
    )
    expect(screen.getByText('step 100,000')).toBeInTheDocument()
    expect(screen.getByText('step 2,048')).toBeInTheDocument()
    expect(screen.getByText('step 500,000')).toBeInTheDocument()
  })

  it('omits step when the filename is unparseable', () => {
    render(
      <CheckpointList
        models={[{ path: 'lonely.zip', sizeBytes: 100 }]}
        selectedPath=""
        onSelect={vi.fn()}
      />,
    )
    // No "step ..." text should be visible
    expect(screen.queryByText(/^step /i)).not.toBeInTheDocument()
    // Filename is still rendered
    expect(screen.getByText('lonely.zip')).toBeInTheDocument()
  })

  it('renders the subdirectory segment only when present', () => {
    render(
      <CheckpointList models={MODELS} selectedPath="" onSelect={vi.fn()} />,
    )
    // Two models share the `ppo/` directory; one lives under `run_b/`
    expect(screen.getAllByText('ppo/')).toHaveLength(2)
    expect(screen.getByText('run_b/')).toBeInTheDocument()
    // Root-level file has no directory line
    const root = screen.getByText('lonely.zip').closest('label')!
    expect(within(root).queryByText(/\//)).not.toBeInTheDocument()
  })
})

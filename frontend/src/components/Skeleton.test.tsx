import { describe, it, expect } from 'vitest'
import { render, screen } from '@testing-library/react'
import { Skeleton } from './Skeleton'

describe('Skeleton', () => {
  it('renders as role="status" by default with a screen-reader label', () => {
    render(<Skeleton />)
    const region = screen.getByRole('status')
    expect(region).toHaveAttribute('aria-busy', 'true')
    expect(region).toHaveAttribute('aria-live', 'polite')
    expect(screen.getByText(/loading/i)).toBeInTheDocument()
  })

  it('uses a custom label when provided', () => {
    render(<Skeleton label="Loading metrics" />)
    expect(screen.getByText('Loading metrics')).toBeInTheDocument()
  })

  it('applies variant class names', () => {
    const { rerender, container } = render(<Skeleton variant="line" />)
    expect(container.querySelector('.skeleton--line')).toBeInTheDocument()

    rerender(<Skeleton variant="rect" />)
    expect(container.querySelector('.skeleton--rect')).toBeInTheDocument()

    rerender(<Skeleton variant="circle" />)
    expect(container.querySelector('.skeleton--circle')).toBeInTheDocument()
  })

  it('passes numeric width/height as pixels', () => {
    const { container } = render(<Skeleton width={120} height={16} aria-hidden="true" />)
    const el = container.querySelector('.skeleton') as HTMLElement
    expect(el.style.width).toBe('120px')
    expect(el.style.height).toBe('16px')
  })

  it('passes string width/height verbatim', () => {
    const { container } = render(<Skeleton width="80%" height="2em" aria-hidden="true" />)
    const el = container.querySelector('.skeleton') as HTMLElement
    expect(el.style.width).toBe('80%')
    expect(el.style.height).toBe('2em')
  })

  it('omits role="status" when aria-hidden is set', () => {
    render(<Skeleton aria-hidden="true" />)
    expect(screen.queryByRole('status')).not.toBeInTheDocument()
    expect(screen.queryByText(/loading/i)).not.toBeInTheDocument()
  })
})

import { describe, it, expect } from 'vitest'
import { render, screen } from '@testing-library/react'
import { DashboardSkeleton } from './DashboardSkeleton'

describe('DashboardSkeleton', () => {
  it('exposes a single role="status" region for assistive tech', () => {
    render(<DashboardSkeleton />)
    // Children use aria-hidden="true" so only the outer wrapper is a status region.
    const statuses = screen.getAllByRole('status')
    expect(statuses).toHaveLength(1)
    expect(statuses[0]).toHaveAttribute('aria-busy', 'true')
    expect(statuses[0]).toHaveAttribute('aria-label', 'Loading dashboard')
  })

  it('includes a screen-reader message so the load is announced', () => {
    render(<DashboardSkeleton />)
    expect(screen.getByText(/loading dashboard/i)).toBeInTheDocument()
  })

  it('renders four chart placeholders to match the real dashboard grid', () => {
    const { container } = render(<DashboardSkeleton />)
    expect(container.querySelectorAll('.dashboard-skeleton-chart')).toHaveLength(4)
  })
})

import { describe, it, expect, vi } from 'vitest'
import { render, screen } from '@testing-library/react'
import App from './App'

// The Dashboard tree opens real WebSockets and PixiJS. Mock them at import
// level so the App test focuses on layout/a11y primitives only.
vi.mock('./components/dashboard/Dashboard', () => ({
  Dashboard: () => <div data-testid="mock-dashboard">Dashboard</div>,
}))
vi.mock('./components/replay/ReplayList', () => ({
  ReplayList: () => <div>ReplayList</div>,
}))
vi.mock('./components/replay/ReplayPlayer', () => ({
  ReplayPlayer: () => <div>ReplayPlayer</div>,
}))
vi.mock('./components/evaluation/EvalPanel', () => ({
  EvalPanel: () => <div>EvalPanel</div>,
}))

describe('App — accessibility landmarks (FE-5 #24)', () => {
  it('renders a skip-to-content link', () => {
    render(<App />)
    const skipLink = screen.getByText(/skip to main content/i)
    expect(skipLink).toBeInTheDocument()
    expect(skipLink).toHaveAttribute('href', '#main-content')
  })

  it('exposes a <main> landmark with id="main-content"', () => {
    render(<App />)
    const main = screen.getByRole('main')
    expect(main).toBeInTheDocument()
    expect(main).toHaveAttribute('id', 'main-content')
  })

  it('exposes a <banner> landmark (header)', () => {
    render(<App />)
    expect(screen.getByRole('banner')).toBeInTheDocument()
  })

  it('gives primary nav an accessible name', () => {
    render(<App />)
    const nav = screen.getByRole('navigation', { name: /primary/i })
    expect(nav).toBeInTheDocument()
  })

  it('renders the app title as an h1', () => {
    render(<App />)
    const heading = screen.getByRole('heading', { level: 1 })
    expect(heading).toHaveTextContent(/pikachu volleyball rl/i)
  })

  it('renders the unified nav (Dashboard + Training Runs) — FC-R8A', () => {
    // FC-R8A (2026-04-18): the separate History / Evaluation nav
    // entries were merged into a single Training Runs entry. Legacy
    // routes 301-redirect to /runs, so any shared URL still works.
    render(<App />)
    expect(screen.getByRole('link', { name: 'Dashboard' })).toBeInTheDocument()
    expect(screen.getByRole('link', { name: 'Training Runs' })).toBeInTheDocument()
    // Ensure the old entries are gone to catch accidental regressions.
    expect(screen.queryByRole('link', { name: 'History' })).toBeNull()
    expect(screen.queryByRole('link', { name: 'Evaluation' })).toBeNull()
  })
})

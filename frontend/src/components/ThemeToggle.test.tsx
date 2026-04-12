import { describe, it, expect, beforeEach, afterEach, vi } from 'vitest'
import { render, screen, fireEvent } from '@testing-library/react'
import { ThemeToggle } from './ThemeToggle'

function installMatchMedia(lightMatches: boolean) {
  const mq = {
    matches: lightMatches,
    media: '(prefers-color-scheme: light)',
    onchange: null,
    addEventListener: vi.fn(),
    removeEventListener: vi.fn(),
    addListener: vi.fn(),
    removeListener: vi.fn(),
    dispatchEvent: vi.fn(),
  }
  window.matchMedia = vi.fn().mockImplementation(() => mq) as typeof window.matchMedia
}

describe('ThemeToggle', () => {
  beforeEach(() => {
    window.localStorage.clear()
    document.documentElement.removeAttribute('data-theme')
    installMatchMedia(false)
  })

  afterEach(() => {
    vi.restoreAllMocks()
  })

  it('renders a button with an accessible label', () => {
    render(<ThemeToggle />)
    // Default (dark) → label asks to switch to light
    expect(screen.getByRole('button', { name: /switch to light theme/i })).toBeInTheDocument()
  })

  it('has aria-pressed=false when theme is dark', () => {
    render(<ThemeToggle />)
    const button = screen.getByRole('button')
    expect(button).toHaveAttribute('aria-pressed', 'false')
  })

  it('toggles theme and updates aria-pressed when clicked', () => {
    render(<ThemeToggle />)
    const button = screen.getByRole('button')

    fireEvent.click(button)

    expect(button).toHaveAttribute('aria-pressed', 'true')
    expect(button).toHaveAccessibleName(/switch to dark theme/i)
    expect(document.documentElement.getAttribute('data-theme')).toBe('light')
  })

  it('toggles back to dark on second click', () => {
    render(<ThemeToggle />)
    const button = screen.getByRole('button')

    fireEvent.click(button) // dark → light
    fireEvent.click(button) // light → dark

    expect(button).toHaveAttribute('aria-pressed', 'false')
    expect(document.documentElement.getAttribute('data-theme')).toBe('dark')
  })

  it('initializes aria-pressed=true when stored preference is light', () => {
    window.localStorage.setItem('pikachu-rl:theme', 'light')
    render(<ThemeToggle />)
    const button = screen.getByRole('button')
    expect(button).toHaveAttribute('aria-pressed', 'true')
  })
})

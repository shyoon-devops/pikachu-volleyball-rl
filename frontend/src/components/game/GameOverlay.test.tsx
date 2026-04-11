import { describe, it, expect } from 'vitest'
import { render, screen } from '@testing-library/react'
import { GameOverlay } from './GameOverlay'

describe('GameOverlay', () => {
  it('renders without crashing', () => {
    render(<GameOverlay score1={0} score2={0} />)
    expect(screen.getByText('0 : 0')).toBeInTheDocument()
  })

  it('displays scores correctly', () => {
    render(<GameOverlay score1={10} score2={7} />)
    expect(screen.getByText('10 : 7')).toBeInTheDocument()
  })

  it('displays status text when provided', () => {
    render(<GameOverlay score1={0} score2={0} statusText="Game Over" />)
    expect(screen.getByText('Game Over')).toBeInTheDocument()
  })

  it('does not display status text when not provided', () => {
    render(<GameOverlay score1={0} score2={0} />)
    expect(screen.queryByText('Game Over')).not.toBeInTheDocument()
  })
})

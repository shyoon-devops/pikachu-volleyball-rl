import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest'
import { render, screen, fireEvent } from '@testing-library/react'
import { ErrorBoundary } from './ErrorBoundary'

function Boom({ message = 'kaboom' }: { message?: string }): null {
  throw new Error(message)
}

function Safe() {
  return <p>all good</p>
}

describe('ErrorBoundary', () => {
  let errorSpy: ReturnType<typeof vi.spyOn>

  beforeEach(() => {
    // React logs caught errors to console.error; silence in the test output.
    errorSpy = vi.spyOn(console, 'error').mockImplementation(() => {})
  })

  afterEach(() => {
    errorSpy.mockRestore()
  })

  it('renders children when nothing throws', () => {
    render(
      <ErrorBoundary>
        <Safe />
      </ErrorBoundary>,
    )
    expect(screen.getByText('all good')).toBeInTheDocument()
  })

  it('renders friendly fallback with role="alert" when a child throws', () => {
    render(
      <ErrorBoundary>
        <Boom message="test failure" />
      </ErrorBoundary>,
    )
    const alert = screen.getByRole('alert')
    expect(alert).toBeInTheDocument()
    expect(screen.getByRole('heading', { name: /oops/i })).toBeInTheDocument()
    // The user-facing message — match the code element, not the stack trace.
    expect(screen.getByText('test failure')).toBeInTheDocument()
  })

  it('offers Try again, Reload, and Go to dashboard actions', () => {
    render(
      <ErrorBoundary>
        <Boom />
      </ErrorBoundary>,
    )
    expect(screen.getByRole('button', { name: /try again/i })).toBeInTheDocument()
    expect(screen.getByRole('button', { name: /reload page/i })).toBeInTheDocument()
    const dashboardLink = screen.getByRole('link', { name: /go to dashboard/i })
    expect(dashboardLink).toHaveAttribute('href', '/')
  })

  it('Try again clears the error and re-renders children', () => {
    function Flaky({ shouldThrow }: { shouldThrow: boolean }) {
      if (shouldThrow) throw new Error('first render blew up')
      return <p>recovered</p>
    }

    const { rerender } = render(
      <ErrorBoundary>
        <Flaky shouldThrow={true} />
      </ErrorBoundary>,
    )
    expect(screen.getByRole('alert')).toBeInTheDocument()

    // Caller "fixes" the underlying condition before we retry.
    rerender(
      <ErrorBoundary>
        <Flaky shouldThrow={false} />
      </ErrorBoundary>,
    )

    fireEvent.click(screen.getByRole('button', { name: /try again/i }))
    expect(screen.getByText('recovered')).toBeInTheDocument()
  })

  it('exposes a technical details disclosure with a stack trace', () => {
    render(
      <ErrorBoundary>
        <Boom message="with stack" />
      </ErrorBoundary>,
    )
    expect(screen.getByText(/technical details/i)).toBeInTheDocument()
  })

  it('prefers explicit fallback prop when provided', () => {
    render(
      <ErrorBoundary fallback={<p>custom-fallback</p>}>
        <Boom />
      </ErrorBoundary>,
    )
    expect(screen.getByText('custom-fallback')).toBeInTheDocument()
    expect(screen.queryByRole('alert')).not.toBeInTheDocument()
  })
})

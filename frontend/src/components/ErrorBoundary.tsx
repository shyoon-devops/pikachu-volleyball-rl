import { Component } from 'react'
import type { ReactNode, ErrorInfo } from 'react'
import './ErrorBoundary.css'

interface Props {
  children: ReactNode
  fallback?: ReactNode
}

interface State {
  error: Error | null
  info: ErrorInfo | null
  detailsOpen: boolean
}

const FRIENDLY_MESSAGE =
  "Something unexpected happened while rendering this view. The training " +
  "loop should still be running in the background — you can try again, " +
  "reload, or head back to the dashboard."

export class ErrorBoundary extends Component<Props, State> {
  state: State = { error: null, info: null, detailsOpen: false }

  static getDerivedStateFromError(error: Error): Partial<State> {
    return { error }
  }

  componentDidCatch(error: Error, info: ErrorInfo) {
    this.setState({ info })
    if (typeof console !== 'undefined' && typeof console.error === 'function') {
      console.error('ErrorBoundary caught:', error, info.componentStack)
    }
  }

  handleRetry = () => {
    this.setState({ error: null, info: null, detailsOpen: false })
  }

  handleReload = () => {
    if (typeof window !== 'undefined') {
      window.location.reload()
    }
  }

  toggleDetails = () => {
    this.setState(prev => ({ detailsOpen: !prev.detailsOpen }))
  }

  render() {
    const { error, info, detailsOpen } = this.state

    if (!error) return this.props.children
    if (this.props.fallback) return this.props.fallback

    const stack = error.stack ?? ''
    const componentStack = info?.componentStack ?? ''

    return (
      <div className="error-boundary" role="alert" aria-live="assertive">
        <div className="error-boundary-card card">
          <div className="error-boundary-icon" aria-hidden="true">
            ⚡
          </div>
          <h2 className="error-boundary-title">Oops — the UI tripped</h2>
          <p className="error-boundary-message">{FRIENDLY_MESSAGE}</p>
          <p className="error-boundary-error">
            <span className="error-boundary-error-label">Error:</span>{' '}
            <code>{error.message || error.name || 'Unknown error'}</code>
          </p>

          <div className="error-boundary-actions">
            <button
              type="button"
              className="error-boundary-btn error-boundary-btn--primary"
              onClick={this.handleRetry}
            >
              Try again
            </button>
            <button
              type="button"
              className="error-boundary-btn"
              onClick={this.handleReload}
            >
              Reload page
            </button>
            <a href="/" className="error-boundary-btn error-boundary-btn--link">
              Go to dashboard
            </a>
          </div>

          {(stack || componentStack) && (
            <details
              className="error-boundary-details"
              open={detailsOpen}
              onToggle={this.toggleDetails}
            >
              <summary>Technical details</summary>
              {stack && (
                <pre className="error-boundary-stack" aria-label="Error stack trace">
                  {stack}
                </pre>
              )}
              {componentStack && (
                <pre
                  className="error-boundary-stack"
                  aria-label="React component stack"
                >
                  {componentStack.trim()}
                </pre>
              )}
            </details>
          )}
        </div>
      </div>
    )
  }
}

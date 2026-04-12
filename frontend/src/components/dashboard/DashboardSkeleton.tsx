import { Skeleton } from '../Skeleton'
import './DashboardSkeleton.css'

/**
 * DashboardSkeleton — shown on initial load before we have any WebSocket
 * state, metrics, or frames. Mirrors the real dashboard grid so there is
 * no layout shift when the live data arrives.
 */
export function DashboardSkeleton() {
  return (
    <div
      className="dashboard dashboard-skeleton"
      role="status"
      aria-busy="true"
      aria-live="polite"
      aria-label="Loading dashboard"
    >
      <section className="dashboard-left">
        <div className="card dashboard-skeleton-controls">
          <Skeleton variant="line" width="40%" height="1rem" aria-hidden="true" />
          <div className="dashboard-skeleton-button-row">
            <Skeleton variant="rect" width={96} height={36} aria-hidden="true" />
            <Skeleton variant="rect" width={96} height={36} aria-hidden="true" />
            <Skeleton variant="rect" width={96} height={36} aria-hidden="true" />
          </div>
        </div>

        <div className="dashboard-skeleton-canvas">
          <Skeleton variant="rect" aria-hidden="true" />
        </div>

        <div className="card dashboard-skeleton-form">
          <Skeleton variant="line" width="30%" height="1rem" aria-hidden="true" />
          <Skeleton variant="line" width="90%" aria-hidden="true" />
          <Skeleton variant="line" width="70%" aria-hidden="true" />
          <Skeleton variant="line" width="80%" aria-hidden="true" />
        </div>
      </section>

      <section className="dashboard-right">
        {[0, 1, 2, 3].map(i => (
          <div key={i} className="card dashboard-skeleton-chart">
            <Skeleton variant="line" width="40%" height="0.9rem" aria-hidden="true" />
            <Skeleton variant="rect" height={120} aria-hidden="true" />
          </div>
        ))}
      </section>

      <section className="dashboard-bottom">
        <div className="card dashboard-skeleton-table">
          <Skeleton variant="line" width="25%" height="1rem" aria-hidden="true" />
          {[0, 1, 2, 3, 4].map(i => (
            <Skeleton key={i} variant="line" height="0.9rem" aria-hidden="true" />
          ))}
        </div>
      </section>

      <span className="sr-only">Loading dashboard — waiting for live training data…</span>
    </div>
  )
}

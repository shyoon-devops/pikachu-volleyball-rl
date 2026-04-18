import { Link, useParams } from 'react-router-dom'
import { ReplayList } from '../replay/ReplayList'
import './TrainingRunDetail.css'

/**
 * Level-2 drill-down: game list for a single training run. Spec
 * c460c55b §2.
 *
 * The URL carries `/history/:title` — BE `GET /api/games?title=X`
 * (T5, fc38f3d8) serves the filtered list. We thread the title
 * through `ReplayList`'s new `titleFilter` prop so the existing
 * unified list is reused end-to-end — only the Title column is
 * hidden (it's redundant once the scope is a single run).
 *
 * Minimal header: breadcrumb + h1 title. The full spec § 2a run-info
 * block (hyperparams summary, run-picker dropdown, live-progress
 * bar) is deferred to a follow-up so the core drill-down ships now.
 */
export function TrainingRunDetail() {
  const { title = '' } = useParams<{ title: string }>()
  const decoded = decodeURIComponent(title)

  return (
    <div className="training-run-detail">
      <nav className="training-run-detail-breadcrumb" aria-label="Breadcrumb">
        <Link to="/history" className="training-run-detail-breadcrumb-link">
          All Trainings
        </Link>
        <span className="training-run-detail-breadcrumb-separator" aria-hidden="true">
          {' › '}
        </span>
        <span className="training-run-detail-breadcrumb-current">
          {decoded || 'untitled'}
        </span>
      </nav>
      <h1 className="training-run-detail-title">{decoded || 'untitled'}</h1>
      <ReplayList titleFilter={decoded} hideTitleColumn emptyStateOverride={
        `이 학습에는 아직 기록된 게임이 없습니다.`
      } />
    </div>
  )
}

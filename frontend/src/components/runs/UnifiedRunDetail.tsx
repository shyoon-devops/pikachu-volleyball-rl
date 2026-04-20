import { useEffect, useMemo, useState } from 'react'
import { Link, useParams, useSearchParams } from 'react-router-dom'
import { ErrorBoundary } from '../ErrorBoundary'
import { ReplayList } from '../replay/ReplayList'
import { EvaluationRunDetail } from '../evaluation/EvaluationRunDetail'
import { HyperparamsSummary } from '../history/HyperparamsSummary'
import { LeaguePanel } from './LeaguePanel'
import { getTrainingRuns } from '../../lib/api'
import { useTrainingState } from '../../hooks/useTrainingState'
import { TimestampText } from '../shared/TimestampText'
import { RewardModelChip } from '../shared/RewardModelChip'
import type { TrainingRun } from '../../lib/types'
import './UnifiedRunDetail.css'

/**
 * FC-R8A: the unified training-run detail at `/runs/:title`. Merges
 * the prior `/history/:title` (games) + `/evaluation/:title`
 * (checkpoints) into one surface with three sub-tabs (Overview /
 * Games / Evaluation) per docs/DESIGN-RUNS-MERGED.md.
 *
 * Sub-tab state is URL-backed (`?tab=overview|games|eval`, default
 * overview) so deep links + back-nav survive. Legacy routes
 * (`/history/:title`, `/evaluation/:title`) redirect into the right
 * sub-tab from App.tsx.
 */

type SubTab = 'overview' | 'games' | 'eval' | 'league'

const TABS: Array<{ key: SubTab; label: string }> = [
  { key: 'overview', label: 'Overview' },
  { key: 'games', label: 'Games' },
  { key: 'eval', label: 'Evaluation' },
  { key: 'league', label: 'League' },
]

function parseTab(raw: string | null): SubTab {
  if (raw === 'games' || raw === 'eval' || raw === 'overview' || raw === 'league') return raw
  return 'overview'
}

export function UnifiedRunDetail() {
  const { title = '' } = useParams<{ title: string }>()
  const decoded = decodeURIComponent(title)
  const [searchParams, setSearchParams] = useSearchParams()
  const { gameResultSeq, status } = useTrainingState()

  const activeTab = parseTab(searchParams.get('tab'))

  const setTab = (next: SubTab) => {
    const params = new URLSearchParams(searchParams)
    if (next === 'overview') params.delete('tab')
    else params.set('tab', next)
    setSearchParams(params, { replace: true })
  }

  // FC-R8b: pull the matching TrainingRun for hyperparams +
  // overview stats. Same fetch shape the run list uses so the
  // hyperparam summary path is identical.
  const [run, setRun] = useState<TrainingRun | null>(null)
  useEffect(() => {
    let cancelled = false
    getTrainingRuns(1, 100)
      .then(res => {
        if (cancelled) return
        const match = res.data.find(r => (r.title ?? '') === decoded) ?? null
        setRun(match)
      })
      .catch(() => { /* overview falls back to placeholders */ })
    return () => { cancelled = true }
  }, [decoded, gameResultSeq])

  const isActiveRun = useMemo(
    () => status.state === 'running' && (status.title ?? '').trim() === decoded.trim(),
    [status.state, status.title, decoded],
  )

  const overviewEmpty = !run && !isActiveRun

  return (
    <div className="unified-run-detail">
      <nav className="unified-run-detail-breadcrumb" aria-label="Breadcrumb">
        <Link to="/runs" className="unified-run-detail-breadcrumb-link">
          ← Training Runs
        </Link>
        <span className="unified-run-detail-breadcrumb-separator" aria-hidden="true">
          {' · '}
        </span>
        <span className="unified-run-detail-breadcrumb-current">
          {decoded || 'untitled'}
        </span>
      </nav>
      <div className="unified-run-detail-header">
        <h1 className="unified-run-detail-title">{decoded || 'untitled'}</h1>
        {isActiveRun && (
          <span
            className="unified-run-detail-running-chip"
            aria-label="This training run is currently running"
          >
            Running
          </span>
        )}
      </div>

      <div
        className="unified-run-detail-tabs"
        role="tablist"
        aria-label="Training run sub-sections"
      >
        {TABS.map(t => {
          const active = t.key === activeTab
          return (
            <button
              key={t.key}
              type="button"
              role="tab"
              aria-selected={active}
              id={`run-tab-${t.key}`}
              aria-controls={`run-panel-${t.key}`}
              tabIndex={active ? 0 : -1}
              className={`unified-run-detail-tab${active ? ' unified-run-detail-tab--active' : ''}`}
              onClick={() => setTab(t.key)}
            >
              {t.label}
            </button>
          )
        })}
      </div>

      <div
        role="tabpanel"
        id={`run-panel-${activeTab}`}
        aria-labelledby={`run-tab-${activeTab}`}
        className="unified-run-detail-panel"
      >
        {activeTab === 'overview' && (
          <div className="unified-run-overview">
            {overviewEmpty ? (
              <p className="unified-run-overview-empty text-muted">
                Collecting metrics…
              </p>
            ) : (
              <dl className="unified-run-overview-meta" aria-label="Run metadata">
                <div className="unified-run-overview-meta-item">
                  <dt>Status</dt>
                  <dd>{isActiveRun ? 'Running' : (run?.status ?? 'done')}</dd>
                </div>
                <div className="unified-run-overview-meta-item">
                  <dt>Started</dt>
                  <dd><TimestampText ts={run?.startedAt} /></dd>
                </div>
                <div className="unified-run-overview-meta-item">
                  <dt>Experiment</dt>
                  <dd className="text-mono">{run?.experimentId?.slice(0, 8) ?? '—'}</dd>
                </div>
                <div className="unified-run-overview-meta-item">
                  <dt>Games</dt>
                  <dd>{(run?.totalGames ?? 0).toLocaleString()}</dd>
                </div>
                <div className="unified-run-overview-meta-item">
                  <dt>Win rate</dt>
                  <dd>
                    {Number.isFinite(run?.winRate)
                      ? `${((run?.winRate ?? 0) * 100).toFixed(1)}%`
                      : '—'}
                  </dd>
                </div>
                <div className="unified-run-overview-meta-item">
                  <dt>Avg rally</dt>
                  <dd>
                    {Number.isFinite(run?.avgRallyLength)
                      ? (run?.avgRallyLength ?? 0).toFixed(1)
                      : '—'}
                  </dd>
                </div>
                {/* Reward-model regime — full label, no chip styling
                    (DESIGN-REWARD-MODEL-SELECTOR.md §4). */}
                <div className="unified-run-overview-meta-item">
                  <dt>Reward model</dt>
                  <dd>
                    <RewardModelChip value={run?.rewardModel} variant="full" />
                  </dd>
                </div>
              </dl>
            )}
            <HyperparamsSummary hyperparams={run?.hyperparams} />
          </div>
        )}

        {activeTab === 'games' && (
          <ErrorBoundary>
            <ReplayList
              titleFilter={decoded}
              hideTitleColumn
              emptyStateOverride="No games recorded for this training run yet."
            />
          </ErrorBoundary>
        )}

        {activeTab === 'eval' && (
          <ErrorBoundary>
            <EvaluationRunDetail embedded />
          </ErrorBoundary>
        )}

        {activeTab === 'league' && (
          <ErrorBoundary>
            <LeaguePanel />
          </ErrorBoundary>
        )}
      </div>
    </div>
  )
}

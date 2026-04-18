import { BrowserRouter, Routes, Route, NavLink, Navigate, useParams, useLocation } from 'react-router-dom'
import { ErrorBoundary } from './components/ErrorBoundary'
import { Dashboard } from './components/dashboard/Dashboard'
import { TrainingRunList } from './components/history/TrainingRunList'
import { UnifiedRunDetail } from './components/runs/UnifiedRunDetail'
import { ReplayPlayer } from './components/replay/ReplayPlayer'
import { VisualHarness } from './components/game/VisualHarness'
import { ThemeToggle } from './components/ThemeToggle'
import { ConnectionIndicator } from './components/ConnectionIndicator'
import { TrainingStateProvider } from './hooks/TrainingStateProvider'
import './App.css'

/**
 * FC-R8A legacy redirect for `/history/:title` and `/evaluation/:title`
 * — keeps shared URLs working after the nav merge. The default sub-tab
 * is pinned per origin so old links land on the expected content:
 *   /history/X    → /runs/X?tab=games
 *   /evaluation/X → /runs/X?tab=eval
 * Existing query params (e.g. `?env=3` on the history drill-down) are
 * preserved where they make sense for the target tab.
 */
function LegacyTitleRedirect({ tab }: { tab: 'games' | 'eval' }) {
  const { title = '' } = useParams<{ title: string }>()
  const location = useLocation()
  const params = new URLSearchParams(location.search)
  params.set('tab', tab)
  // Preserve namespaced query params if any. Host-specific namespacing
  // (games.env, eval.step) lives inside child components — we pass
  // whatever arrived through without mutation.
  return <Navigate to={`/runs/${title}?${params.toString()}`} replace />
}

function App() {
  return (
    <BrowserRouter>
      <TrainingStateProvider>
        <div className="app">
          <a href="#main-content" className="app-skip-link">
            Skip to main content
          </a>

          <header className="app-header" role="banner">
            <h1 className="app-title">Pikachu Volleyball RL</h1>
            <nav className="app-nav" aria-label="Primary">
              <NavLink to="/" end className={({ isActive }) => `app-nav-link${isActive ? ' active' : ''}`}>
                Dashboard
              </NavLink>
              {/*
                FC-R8A: merged History + Evaluation nav entries into a
                single "Training Runs" entry. Legacy /history and
                /evaluation routes redirect to /runs below so shared
                URLs and bookmarks keep working.
              */}
              <NavLink to="/runs" className={({ isActive }) => `app-nav-link${isActive ? ' active' : ''}`}>
                Training Runs
              </NavLink>
            </nav>
            <div className="app-header-actions">
              <ConnectionIndicator />
              <ThemeToggle />
            </div>
          </header>

          <main id="main-content" role="main" tabIndex={-1}>
            <ErrorBoundary>
              {/*
                Per-route ErrorBoundaries (FC-R7A, 2026-04-18). The
                outer boundary catches anything missed; each inner
                one isolates a single route so a stopped-state
                render crash on /runs doesn't take down other routes.
              */}
              <Routes>
                <Route path="/" element={
                  <ErrorBoundary>
                    <Dashboard />
                  </ErrorBoundary>
                } />
                {/*
                  FC-R8A unified surface (spec 43d9d1bb):
                    /runs         → L1 runs list (merged H+E)
                    /runs/:title  → L2 detail with Overview / Games /
                                    Evaluation sub-tabs
                */}
                <Route path="/runs" element={
                  <ErrorBoundary>
                    <TrainingRunList linkBase="/runs/" mode="evaluation" />
                  </ErrorBoundary>
                } />
                <Route path="/runs/:title" element={
                  <ErrorBoundary>
                    <UnifiedRunDetail />
                  </ErrorBoundary>
                } />
                {/* Legacy redirects — preserve shared URLs and bookmarks. */}
                <Route path="/history" element={<Navigate to="/runs" replace />} />
                <Route path="/history/:title" element={<LegacyTitleRedirect tab="games" />} />
                <Route path="/evaluation" element={<Navigate to="/runs" replace />} />
                <Route path="/evaluation/:title" element={<LegacyTitleRedirect tab="eval" />} />
                <Route path="/replay/:id" element={
                  <ErrorBoundary>
                    <ReplayPlayer />
                  </ErrorBoundary>
                } />
                <Route path="/visual" element={<VisualHarness />} />
              </Routes>
            </ErrorBoundary>
          </main>
        </div>
      </TrainingStateProvider>
    </BrowserRouter>
  )
}

export default App

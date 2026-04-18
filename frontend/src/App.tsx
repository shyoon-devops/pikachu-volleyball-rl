import { BrowserRouter, Routes, Route, NavLink } from 'react-router-dom'
import { ErrorBoundary } from './components/ErrorBoundary'
import { Dashboard } from './components/dashboard/Dashboard'
import { TrainingRunList } from './components/history/TrainingRunList'
import { TrainingRunDetail } from './components/history/TrainingRunDetail'
import { ReplayPlayer } from './components/replay/ReplayPlayer'
import { EvaluationRunDetail } from './components/evaluation/EvaluationRunDetail'
import { VisualHarness } from './components/game/VisualHarness'
import { ThemeToggle } from './components/ThemeToggle'
import { ConnectionIndicator } from './components/ConnectionIndicator'
import { TrainingStateProvider } from './hooks/TrainingStateProvider'
import './App.css'

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
              <NavLink to="/history" className={({ isActive }) => `app-nav-link${isActive ? ' active' : ''}`}>
                History
              </NavLink>
              <NavLink to="/evaluation" className={({ isActive }) => `app-nav-link${isActive ? ' active' : ''}`}>
                Evaluation
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
                render crash on /history doesn't take down
                /evaluation's "Try again" behaviour. qa regression
                that surfaced this: empty / null fields on
                training:status fed downstream components that
                crashed mid-render.
              */}
              <Routes>
                <Route path="/" element={
                  <ErrorBoundary>
                    <Dashboard />
                  </ErrorBoundary>
                } />
                {/*
                  History drill-down (R6H, spec c460c55b):
                    /history          → runs aggregate list (level-1)
                    /history/:title   → games of one run (level-2, ReplayList)
                  Legacy bookmarks to /history still land on the
                  hub page; deep-linked games pages go via /history/X.
                */}
                <Route path="/history" element={
                  <ErrorBoundary>
                    <TrainingRunList />
                  </ErrorBoundary>
                } />
                <Route path="/history/:title" element={
                  <ErrorBoundary>
                    <TrainingRunDetail />
                  </ErrorBoundary>
                } />
                <Route path="/replay/:id" element={
                  <ErrorBoundary>
                    <ReplayPlayer />
                  </ErrorBoundary>
                } />
                {/*
                  Evaluation drill-down (R7C, spec bf7bfaa4):
                    /evaluation          → runs aggregate list (level-1)
                    /evaluation/:title   → checkpoints of one run + eval runner
                  Reuses TrainingRunList for level-1 with a `/evaluation/`
                  link base, so the history and evaluation landing pages
                  share the same search/filter/card UX.
                */}
                <Route path="/evaluation" element={
                  <ErrorBoundary>
                    <TrainingRunList linkBase="/evaluation/" mode="evaluation" />
                  </ErrorBoundary>
                } />
                <Route path="/evaluation/:title" element={
                  <ErrorBoundary>
                    <EvaluationRunDetail />
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

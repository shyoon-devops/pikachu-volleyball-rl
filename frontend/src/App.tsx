import { BrowserRouter, Routes, Route, NavLink } from 'react-router-dom'
import { ErrorBoundary } from './components/ErrorBoundary'
import { Dashboard } from './components/dashboard/Dashboard'
import { TrainingRunList } from './components/history/TrainingRunList'
import { TrainingRunDetail } from './components/history/TrainingRunDetail'
import { ReplayPlayer } from './components/replay/ReplayPlayer'
import { EvalPanel } from './components/evaluation/EvalPanel'
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
              <Routes>
                <Route path="/" element={<Dashboard />} />
                {/*
                  History drill-down (R6H, spec c460c55b):
                    /history          → runs aggregate list (level-1)
                    /history/:title   → games of one run (level-2, ReplayList)
                  Legacy bookmarks to /history still land on the
                  hub page; deep-linked games pages go via /history/X.
                */}
                <Route path="/history" element={<TrainingRunList />} />
                <Route path="/history/:title" element={<TrainingRunDetail />} />
                <Route path="/replay/:id" element={<ReplayPlayer />} />
                <Route path="/evaluation" element={<EvalPanel />} />
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

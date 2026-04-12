import { BrowserRouter, Routes, Route, NavLink } from 'react-router-dom'
import { ErrorBoundary } from './components/ErrorBoundary'
import { Dashboard } from './components/dashboard/Dashboard'
import { ReplayList } from './components/replay/ReplayList'
import { ReplayPlayer } from './components/replay/ReplayPlayer'
import { EvalPanel } from './components/evaluation/EvalPanel'
import { ThemeToggle } from './components/ThemeToggle'
import './App.css'

function App() {
  return (
    <BrowserRouter>
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
            <ThemeToggle />
          </div>
        </header>

        <main id="main-content" role="main" tabIndex={-1}>
          <ErrorBoundary>
            <Routes>
              <Route path="/" element={<Dashboard />} />
              <Route path="/history" element={<ReplayList />} />
              <Route path="/replay/:id" element={<ReplayPlayer />} />
              <Route path="/evaluation" element={<EvalPanel />} />
            </Routes>
          </ErrorBoundary>
        </main>
      </div>
    </BrowserRouter>
  )
}

export default App

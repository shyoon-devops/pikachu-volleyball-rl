import { BrowserRouter, Routes, Route, NavLink } from 'react-router-dom'
import { ErrorBoundary } from './components/ErrorBoundary'
import { Dashboard } from './components/dashboard/Dashboard'
import { ReplayList } from './components/replay/ReplayList'
import { ReplayPlayer } from './components/replay/ReplayPlayer'
import { EvalPanel } from './components/evaluation/EvalPanel'
import './App.css'

function App() {
  return (
    <BrowserRouter>
      <div className="app">
        <header className="app-header">
          <h1 className="app-title">Pikachu Volleyball RL</h1>
          <nav className="app-nav">
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
        </header>

        <ErrorBoundary>
          <Routes>
            <Route path="/" element={<Dashboard />} />
            <Route path="/history" element={<ReplayList />} />
            <Route path="/replay/:id" element={<ReplayPlayer />} />
            <Route path="/evaluation" element={<EvalPanel />} />
          </Routes>
        </ErrorBoundary>
      </div>
    </BrowserRouter>
  )
}

export default App

import { BrowserRouter, Routes, Route, NavLink } from 'react-router-dom'
import { Dashboard } from './components/dashboard/Dashboard'
import { ReplayList } from './components/replay/ReplayList'
import { ReplayPlayer } from './components/replay/ReplayPlayer'
import { EvalPanel } from './components/evaluation/EvalPanel'
import './App.css'

function App() {
  return (
    <BrowserRouter>
      <div className="app">
        <header className="navbar">
          <NavLink to="/" className="navbar__logo">
            <span className="navbar__logo-icon">&#9889;</span>
            <span className="navbar__logo-text">Pikachu Volleyball RL</span>
          </NavLink>

          <nav className="navbar__nav">
            <NavLink
              to="/"
              end
              className={({ isActive }) =>
                `navbar__link ${isActive ? 'navbar__link--active' : ''}`
              }
            >
              Dashboard
            </NavLink>
            <NavLink
              to="/history"
              className={({ isActive }) =>
                `navbar__link ${isActive ? 'navbar__link--active' : ''}`
              }
            >
              History
            </NavLink>
            <NavLink
              to="/evaluation"
              className={({ isActive }) =>
                `navbar__link ${isActive ? 'navbar__link--active' : ''}`
              }
            >
              Evaluation
            </NavLink>
          </nav>
        </header>

        <main className="main-content">
          <Routes>
            <Route path="/" element={<Dashboard />} />
            <Route path="/history" element={<ReplayList />} />
            <Route path="/replay/:id" element={<ReplayPlayer />} />
            <Route path="/evaluation" element={<EvalPanel />} />
          </Routes>
        </main>
      </div>
    </BrowserRouter>
  )
}

export default App

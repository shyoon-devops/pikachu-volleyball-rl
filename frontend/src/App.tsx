import { BrowserRouter, Routes, Route, NavLink } from 'react-router-dom'
import { Dashboard } from './components/dashboard/Dashboard'
import { ReplayList } from './components/replay/ReplayList'
import { ReplayPlayer } from './components/replay/ReplayPlayer'
import { EvalPanel } from './components/evaluation/EvalPanel'

const navLinkStyle = (isActive: boolean): React.CSSProperties => ({
  color: isActive ? '#ffd700' : '#888',
  textDecoration: 'none',
  fontSize: 13,
  fontWeight: isActive ? 600 : 400,
  padding: '4px 0',
  borderBottom: isActive ? '2px solid #ffd700' : '2px solid transparent',
})

function App() {
  return (
    <BrowserRouter>
      <div style={{ minHeight: '100vh', background: '#0f0f1a', color: '#e0e0e0', fontFamily: 'monospace' }}>
        <header style={{ padding: '12px 24px', borderBottom: '1px solid #2a2a3e', display: 'flex', alignItems: 'center', gap: 32 }}>
          <h1 style={{ margin: 0, fontSize: 18, color: '#ffd700' }}>Pikachu Volleyball RL</h1>
          <nav style={{ display: 'flex', gap: 20 }}>
            <NavLink to="/" end style={({ isActive }) => navLinkStyle(isActive)}>
              Dashboard
            </NavLink>
            <NavLink to="/history" style={({ isActive }) => navLinkStyle(isActive)}>
              History
            </NavLink>
            <NavLink to="/evaluation" style={({ isActive }) => navLinkStyle(isActive)}>
              Evaluation
            </NavLink>
          </nav>
        </header>

        <Routes>
          <Route path="/" element={<Dashboard />} />
          <Route path="/history" element={<ReplayList />} />
          <Route path="/replay/:id" element={<ReplayPlayer />} />
          <Route path="/evaluation" element={<EvalPanel />} />
        </Routes>
      </div>
    </BrowserRouter>
  )
}

export default App

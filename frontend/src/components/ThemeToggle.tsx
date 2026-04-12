import { useTheme } from '../hooks/useTheme'
import './ThemeToggle.css'

export function ThemeToggle() {
  const { theme, toggleTheme } = useTheme()
  const isLight = theme === 'light'

  return (
    <button
      type="button"
      onClick={toggleTheme}
      className="theme-toggle"
      aria-label={`Switch to ${isLight ? 'dark' : 'light'} theme`}
      aria-pressed={isLight}
      title={`Switch to ${isLight ? 'dark' : 'light'} theme`}
    >
      <span className="theme-toggle-track" aria-hidden="true">
        <span className="theme-toggle-icon theme-toggle-icon--sun">☀</span>
        <span className="theme-toggle-icon theme-toggle-icon--moon">☾</span>
        <span className="theme-toggle-thumb" data-theme={theme} />
      </span>
      <span className="sr-only">Theme: {theme}</span>
    </button>
  )
}

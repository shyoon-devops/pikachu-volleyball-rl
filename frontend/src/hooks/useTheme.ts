import { useCallback, useEffect, useRef, useState } from 'react'

export type Theme = 'dark' | 'light'

const STORAGE_KEY = 'pikachu-rl:theme'
const DATA_ATTR = 'data-theme'

function readStoredPreference(): Theme | null {
  if (typeof window === 'undefined') return null
  try {
    const saved = window.localStorage.getItem(STORAGE_KEY)
    if (saved === 'light' || saved === 'dark') return saved
  } catch {
    // localStorage may throw in private mode / when quota is exceeded
  }
  return null
}

function readOsPreference(): Theme {
  if (typeof window === 'undefined' || !window.matchMedia) return 'dark'
  return window.matchMedia('(prefers-color-scheme: light)').matches ? 'light' : 'dark'
}

function getInitialTheme(): Theme {
  return readStoredPreference() ?? readOsPreference()
}

function applyTheme(theme: Theme): void {
  if (typeof document === 'undefined') return
  document.documentElement.setAttribute(DATA_ATTR, theme)
}

export function useTheme(): {
  theme: Theme
  toggleTheme: () => void
  setTheme: (t: Theme) => void
} {
  const [theme, setThemeState] = useState<Theme>(getInitialTheme)
  // Tracks whether the current theme was set explicitly by the user
  // (toggle/setTheme). Only explicit preferences are persisted — initial
  // OS-preference detection stays transient so OS changes still sync.
  const hasExplicitPreference = useRef<boolean>(readStoredPreference() !== null)

  // Keep <html data-theme> in sync on every change.
  useEffect(() => {
    applyTheme(theme)
  }, [theme])

  // Sync with OS-level changes only if the user hasn't set an explicit preference.
  useEffect(() => {
    if (typeof window === 'undefined' || !window.matchMedia) return
    const mq = window.matchMedia('(prefers-color-scheme: light)')
    const onChange = (e: MediaQueryListEvent) => {
      if (hasExplicitPreference.current) return
      setThemeState(e.matches ? 'light' : 'dark')
    }
    mq.addEventListener('change', onChange)
    return () => mq.removeEventListener('change', onChange)
  }, [])

  const persistExplicit = useCallback((t: Theme) => {
    hasExplicitPreference.current = true
    try {
      window.localStorage.setItem(STORAGE_KEY, t)
    } catch {
      // persistence failure is not fatal
    }
  }, [])

  const setTheme = useCallback(
    (t: Theme) => {
      persistExplicit(t)
      setThemeState(t)
    },
    [persistExplicit],
  )

  const toggleTheme = useCallback(() => {
    setThemeState(prev => {
      const next: Theme = prev === 'dark' ? 'light' : 'dark'
      persistExplicit(next)
      return next
    })
  }, [persistExplicit])

  return { theme, toggleTheme, setTheme }
}

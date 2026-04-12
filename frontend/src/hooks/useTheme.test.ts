import { describe, it, expect, beforeEach, afterEach, vi } from 'vitest'
import { act, renderHook } from '@testing-library/react'
import { useTheme } from './useTheme'

const STORAGE_KEY = 'pikachu-rl:theme'

type MatchMediaMock = {
  matches: boolean
  listeners: Array<(e: MediaQueryListEvent) => void>
  addEventListener: ReturnType<typeof vi.fn>
  removeEventListener: ReturnType<typeof vi.fn>
  addListener: ReturnType<typeof vi.fn>
  removeListener: ReturnType<typeof vi.fn>
  dispatchEvent: ReturnType<typeof vi.fn>
  media: string
  onchange: null
}

function installMatchMedia(lightMatches: boolean): MatchMediaMock {
  const mq: MatchMediaMock = {
    matches: lightMatches,
    media: '(prefers-color-scheme: light)',
    onchange: null,
    listeners: [],
    addEventListener: vi.fn(),
    removeEventListener: vi.fn(),
    addListener: vi.fn(),
    removeListener: vi.fn(),
    dispatchEvent: vi.fn(),
  }
  mq.addEventListener.mockImplementation((_event: string, cb: (e: MediaQueryListEvent) => void) => {
    mq.listeners.push(cb)
  })
  mq.removeEventListener.mockImplementation((_event: string, cb: (e: MediaQueryListEvent) => void) => {
    mq.listeners = mq.listeners.filter(l => l !== cb)
  })
  window.matchMedia = vi.fn().mockImplementation(() => mq) as typeof window.matchMedia
  return mq
}

describe('useTheme', () => {
  beforeEach(() => {
    window.localStorage.clear()
    document.documentElement.removeAttribute('data-theme')
  })

  afterEach(() => {
    vi.restoreAllMocks()
  })

  it('defaults to dark when no preference and OS prefers dark', () => {
    installMatchMedia(false)
    const { result } = renderHook(() => useTheme())
    expect(result.current.theme).toBe('dark')
    expect(document.documentElement.getAttribute('data-theme')).toBe('dark')
  })

  it('uses light when OS prefers light and no stored preference', () => {
    installMatchMedia(true)
    const { result } = renderHook(() => useTheme())
    expect(result.current.theme).toBe('light')
    expect(document.documentElement.getAttribute('data-theme')).toBe('light')
  })

  it('prefers stored value over OS preference', () => {
    installMatchMedia(true) // OS says light
    window.localStorage.setItem(STORAGE_KEY, 'dark')
    const { result } = renderHook(() => useTheme())
    expect(result.current.theme).toBe('dark')
  })

  it('toggleTheme flips dark→light and persists to localStorage', () => {
    installMatchMedia(false)
    const { result } = renderHook(() => useTheme())
    expect(result.current.theme).toBe('dark')

    act(() => {
      result.current.toggleTheme()
    })

    expect(result.current.theme).toBe('light')
    expect(document.documentElement.getAttribute('data-theme')).toBe('light')
    expect(window.localStorage.getItem(STORAGE_KEY)).toBe('light')
  })

  it('toggleTheme flips light→dark', () => {
    installMatchMedia(true)
    const { result } = renderHook(() => useTheme())
    expect(result.current.theme).toBe('light')

    act(() => {
      result.current.toggleTheme()
    })

    expect(result.current.theme).toBe('dark')
    expect(window.localStorage.getItem(STORAGE_KEY)).toBe('dark')
  })

  it('setTheme sets an explicit theme', () => {
    installMatchMedia(false)
    const { result } = renderHook(() => useTheme())

    act(() => {
      result.current.setTheme('light')
    })

    expect(result.current.theme).toBe('light')
    expect(document.documentElement.getAttribute('data-theme')).toBe('light')
  })

  it('responds to OS changes only when no explicit preference is stored', () => {
    const mq = installMatchMedia(false)
    const { result } = renderHook(() => useTheme())
    expect(result.current.theme).toBe('dark')

    // OS flips to light — user has no stored preference, so follow it
    act(() => {
      for (const l of mq.listeners) {
        l({ matches: true } as MediaQueryListEvent)
      }
    })
    expect(result.current.theme).toBe('light')
  })

  it('ignores OS changes once the user has set an explicit preference', () => {
    const mq = installMatchMedia(false)
    window.localStorage.setItem(STORAGE_KEY, 'dark')
    const { result } = renderHook(() => useTheme())
    expect(result.current.theme).toBe('dark')

    act(() => {
      for (const l of mq.listeners) {
        l({ matches: true } as MediaQueryListEvent)
      }
    })
    // Should remain dark because there is an explicit stored preference
    expect(result.current.theme).toBe('dark')
  })
})

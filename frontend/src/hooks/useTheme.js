import { useCallback, useEffect, useState } from 'react'

const KEY = 'qgf-theme'

/**
 * Theme preference: 'system' | 'light' | 'dark' — dark unless the viewer chose otherwise.
 *
 * 'system' removes the data-theme stamp so prefers-color-scheme decides;
 * an explicit choice stamps the root element and wins in both directions.
 */
export function useTheme() {
  const [theme, setTheme] = useState(() => {
    try {
      return localStorage.getItem(KEY) || 'dark'
    } catch {
      return 'dark'
    }
  })

  useEffect(() => {
    const root = document.documentElement
    if (theme === 'system') root.removeAttribute('data-theme')
    else root.setAttribute('data-theme', theme)
    try {
      localStorage.setItem(KEY, theme)
    } catch {
      /* private mode or blocked site data — the stamp above still applies */
    }
  }, [theme])

  const cycle = useCallback(() => {
    setTheme((t) => (t === 'system' ? 'light' : t === 'light' ? 'dark' : 'system'))
  }, [])

  return { theme, setTheme, cycle }
}

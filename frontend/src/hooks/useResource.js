import { useCallback, useEffect, useRef, useState } from 'react'

/**
 * Fetch a resource on mount and expose { data, error, loading, refetching, reload }.
 *
 * A refetch keeps the previous data in place (rendered at reduced opacity by the
 * caller) so charts never flash a skeleton or jump layout.
 */
export function useResource(fetcher, deps = [], { enabled = true } = {}) {
  const [state, setState] = useState({ data: null, error: null, loading: enabled, refetching: false })
  const mounted = useRef(true)
  const hasData = useRef(false)

  useEffect(() => {
    mounted.current = true
    return () => {
      mounted.current = false
    }
  }, [])

  const run = useCallback(async () => {
    if (!enabled) {
      setState({ data: null, error: null, loading: false, refetching: false })
      return
    }
    setState((s) => ({ ...s, loading: !hasData.current, refetching: hasData.current, error: null }))
    try {
      const data = await fetcher()
      if (!mounted.current) return
      hasData.current = true
      setState({ data, error: null, loading: false, refetching: false })
    } catch (error) {
      if (!mounted.current || error?.name === 'AbortError') return
      setState((s) => ({ data: s.data, error, loading: false, refetching: false }))
    }
    // fetcher is intentionally excluded: callers pass an inline closure and
    // declare its real inputs through `deps`.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [enabled, ...deps])

  useEffect(() => {
    hasData.current = false
    run()
  }, [run])

  return { ...state, reload: run }
}

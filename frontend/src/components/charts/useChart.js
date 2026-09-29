import { useCallback, useLayoutEffect, useRef, useState } from 'react'

/** Measure the chart container so the SVG viewBox tracks its real width. */
export function useChartWidth(fallback = 640) {
  const ref = useRef(null)
  const [width, setWidth] = useState(fallback)

  useLayoutEffect(() => {
    const el = ref.current
    if (!el) return
    const measure = () => setWidth(el.clientWidth || fallback)
    measure()
    if (typeof ResizeObserver === 'undefined') return
    const ro = new ResizeObserver(measure)
    ro.observe(el)
    return () => ro.disconnect()
  }, [fallback])

  return [ref, width]
}

/**
 * Chart height as clamp(210px, 46vw, desktop): a fixed desktop height would
 * swallow a phone screen. Evaluated per render; the width observer above
 * re-renders on every resize, so it tracks the viewport.
 */
export function clampHeight(desktop) {
  const vw = typeof window === 'undefined' ? 1440 : window.innerWidth
  return Math.round(Math.max(210, Math.min(desktop, vw * 0.46)))
}

/**
 * Pointer plumbing: reports the pointer position within the plot area and
 * clears it on leave. Keyboard focus is handled per-mark by each chart.
 */
export function usePointer() {
  const [pointer, setPointer] = useState(null)
  const onMove = useCallback((event) => {
    const rect = event.currentTarget.getBoundingClientRect()
    setPointer({ x: event.clientX - rect.left, y: event.clientY - rect.top })
  }, [])
  const onLeave = useCallback(() => setPointer(null), [])
  return { pointer, onMove, onLeave, setPointer }
}

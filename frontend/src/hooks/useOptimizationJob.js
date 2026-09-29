import { useCallback, useEffect, useRef, useState } from 'react'
import { api } from '../api/client'

const POLL_MS = 700

/**
 * Start a live QIEA+QPSO run and poll it to completion.
 *
 * Polling stops on a terminal status, and the interval is always cleared on
 * unmount so navigating away mid-run leaves no timer behind.
 */
export function useOptimizationJob() {
  const [job, setJob] = useState(null)
  const [error, setError] = useState(null)
  const [starting, setStarting] = useState(false)
  const timer = useRef(null)
  const mounted = useRef(true)

  const stopPolling = useCallback(() => {
    if (timer.current) {
      clearInterval(timer.current)
      timer.current = null
    }
  }, [])

  useEffect(() => {
    mounted.current = true
    return () => {
      mounted.current = false
      stopPolling()
    }
  }, [stopPolling])

  const poll = useCallback(
    async (jobId) => {
      try {
        const next = await api.job(jobId)
        if (!mounted.current) return
        setJob(next)
        if (['done', 'error', 'cancelled'].includes(next.status)) {
          stopPolling()
          if (next.status === 'error') setError(new Error(next.error || 'Optimization failed.'))
        }
      } catch (err) {
        if (!mounted.current) return
        stopPolling()
        setError(err)
      }
    },
    [stopPolling],
  )

  const start = useCallback(
    async (config) => {
      stopPolling()
      setError(null)
      setStarting(true)
      try {
        const created = await api.startOptimization(config)
        if (!mounted.current) return null
        setJob(created)
        timer.current = setInterval(() => poll(created.job_id), POLL_MS)
        poll(created.job_id)
        return created
      } catch (err) {
        if (mounted.current) setError(err)
        return null
      } finally {
        if (mounted.current) setStarting(false)
      }
    },
    [poll, stopPolling],
  )

  const cancel = useCallback(async () => {
    if (!job?.job_id) return
    try {
      const next = await api.cancelJob(job.job_id)
      if (mounted.current) setJob(next)
    } catch (err) {
      if (mounted.current) setError(err)
    }
  }, [job])

  const running = job != null && ['queued', 'running'].includes(job.status)
  return { job, error, starting, running, start, cancel }
}

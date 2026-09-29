/** Loading, error and empty placeholders sized to sit inside a Panel body. */
import { Icon } from './Icon'

export function Loader({ label = 'Loading…' }) {
  return (
    <div className="states" role="status">
      <div className="spinner" />
      <div>{label}</div>
    </div>
  )
}

export function ErrorState({ error, onRetry, title = 'Could not load this view' }) {
  const status = error?.status
  return (
    <div className="states" role="alert">
      <div className="states__icon states__icon--critical">
        <Icon name="alert" size={22} />
      </div>
      <div className="states__title">{title}</div>
      <div className="states__body">{error?.message || 'Unexpected error.'}</div>
      {status === 0 && (
        <code className="mono">
          cd QGreenFleet &amp;&amp; uvicorn src.api.main:app --port 8000
        </code>
      )}
      {onRetry && (
        <button type="button" className="btn btn--sm" onClick={onRetry}>
          Try again
        </button>
      )}
    </div>
  )
}

export function EmptyState({ icon = 'database', title, children }) {
  return (
    <div className="states">
      <div className="states__icon">
        <Icon name={icon} size={22} />
      </div>
      {title && <div className="states__title">{title}</div>}
      {children && <div className="states__body">{children}</div>}
    </div>
  )
}

/** Renders children only once a resource has data, handling the other states. */
export function Resource({ state, onRetry, loadingLabel, children, empty }) {
  if (state.loading) return <Loader label={loadingLabel} />
  if (state.error && !state.data) return <ErrorState error={state.error} onRetry={onRetry} />
  if (!state.data) return empty || <EmptyState title="No data available" />
  return children(state.data)
}

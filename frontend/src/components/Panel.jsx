import { Icon } from './Icon'

/**
 * Card wrapper: title, optional subtitle, an actions slot, a body, and an
 * optional insight line — the sentence that turns a plot into a finding.
 */
export function Panel({ title, subtitle, actions, children, flush = false, refetching = false, insight }) {
  return (
    <section className="panel">
      {(title || actions) && (
        <header className="panel__head">
          <div className="panel__titles">
            {title && <h2>{title}</h2>}
            {subtitle && <div className="panel__sub">{subtitle}</div>}
          </div>
          {actions && <div className="panel__actions">{actions}</div>}
        </header>
      )}
      <div
        className={`panel__body${flush ? ' panel__body--flush' : ''}${refetching ? ' is-refetching' : ''}`}
      >
        {children}
      </div>
      {insight && (
        <p className="panel__insight">
          <Icon name="info" size={16} />
          <span>
            <span className="panel__insight-label">Insight</span>
            {insight}
          </span>
        </p>
      )}
    </section>
  )
}

/**
 * Collapsed-by-default detail (native <details>): raw tables sit behind the
 * summary and visualisation instead of dominating the page.
 */
export function Disclosure({ title, subtitle, count, children, defaultOpen = false }) {
  return (
    <details className="disclosure" open={defaultOpen || undefined}>
      <summary>
        <span className="disclosure__titles">
          <span className="disclosure__title">{title}</span>
          {subtitle && <span className="disclosure__sub"> — {subtitle}</span>}
        </span>
        {count && <span className="disclosure__count">{count}</span>}
        <Icon name="chevronDown" size={18} className="disclosure__chev" />
      </summary>
      <div className="disclosure__body">{children}</div>
    </details>
  )
}

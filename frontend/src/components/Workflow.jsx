import { Link } from 'react-router-dom'
import { STATUS_LABEL } from '../lib/workflow'
import { Icon } from './Icon'

const STATUS_ICON = { completed: 'check', error: 'alert' }

/**
 * The pipeline stepper — a navigable list, not tabs.
 *
 * The connector fills through the leading run of completed steps. The active
 * card's tint is an opaque color-mix of the accent into the surface, so the
 * connector never shows through it.
 */
export function Workflow({ steps }) {
  let lead = 0
  while (lead < steps.length && steps[lead].status === 'completed') lead += 1
  const progress = Math.min(lead, steps.length - 1) / (steps.length - 1)

  return (
    <ol className="wf" style={{ '--wf-progress': progress }} aria-label="Decision pipeline">
      {steps.map((step) => (
        <li key={step.key} className={`wf__step is-${step.status}`}>
          <Link
            to={step.routes[0]}
            className="wf__link"
            aria-current={step.status === 'active' ? 'step' : undefined}
          >
            <span className="wf__marker" aria-hidden="true">
              {STATUS_ICON[step.status] ? (
                <Icon name={STATUS_ICON[step.status]} size={16} strokeWidth={2.25} />
              ) : (
                <span className="wf__num">{step.index + 1}</span>
              )}
            </span>
            <span className="wf__body">
              <span className="wf__stage">
                <Icon name={step.icon} size={14} />
                {step.stage}
              </span>
              <span className="wf__title">{step.title}</span>
              <span className="wf__desc">{step.description}</span>
              <span className={`wf__status wf__status--${step.status}`}>
                {step.status === 'active' && <span className="wf__pulse" aria-hidden="true" />}
                {step.status === 'completed' && <Icon name="check" size={13} strokeWidth={2.25} />}
                {step.status === 'error' && <Icon name="alert" size={13} strokeWidth={2.25} />}
                {step.status === 'upcoming' && <Icon name="circle" size={12} />}
                {STATUS_LABEL[step.status]}
              </span>
            </span>
          </Link>
        </li>
      ))}
    </ol>
  )
}

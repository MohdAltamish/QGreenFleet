import { Link } from 'react-router-dom'
import { PageHeader } from '../components/Layout'
import { EmptyState } from '../components/States'
import { Panel } from '../components/Panel'

export default function NotFound() {
  return (
    <>
      <PageHeader title="Page not found" />
      <div className="content">
        <Panel>
          <EmptyState icon="compass" title="No such view">
            <Link to="/overview">Back to the overview</Link>
          </EmptyState>
        </Panel>
      </div>
    </>
  )
}

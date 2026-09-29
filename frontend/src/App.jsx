import { Route, Routes, useLocation } from 'react-router-dom'
import { Layout } from './components/Layout'
import { api } from './api/client'
import { useResource } from './hooks/useResource'
import Landing from './pages/Landing'
import Overview from './pages/Overview'
import Fleet from './pages/Fleet'
import Predict from './pages/Predict'
import Optimize from './pages/Optimize'
import Scenarios from './pages/Scenarios'
import Benchmark from './pages/Benchmark'
import Reports from './pages/Reports'
import NotFound from './pages/NotFound'

export default function App() {
  // One health probe drives the sidebar status for every route.
  const health = useResource(() => api.health(), [])
  const { pathname } = useLocation()

  // The landing page is the product's front door and sits outside the app shell.
  if (pathname === '/') return <Landing health={health} />

  return (
    <Layout health={health.data} healthPending={health.loading}>
      <Routes>
        <Route path="/overview" element={<Overview health={health} />} />
        <Route path="/fleet" element={<Fleet onFleetChange={health.reload} />} />
        <Route path="/predict" element={<Predict />} />
        <Route path="/optimize" element={<Optimize />} />
        <Route path="/scenarios" element={<Scenarios />} />
        <Route path="/benchmark" element={<Benchmark />} />
        <Route path="/reports" element={<Reports />} />
        <Route path="*" element={<NotFound />} />
      </Routes>
    </Layout>
  )
}

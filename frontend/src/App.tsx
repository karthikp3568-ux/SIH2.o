import { Navigate, Route, Routes } from 'react-router-dom'
import type { ReactElement } from 'react'

import { AdminDashboard } from './pages/admin/AdminDashboard'
import { Conversation } from './pages/Conversation'
import { PathwayDetail } from './pages/PathwayDetail'
import { Pathways } from './pages/Pathways'
import { ProfileConfirm } from './pages/ProfileConfirm'
import { Progress } from './pages/Progress'
import { Register, SignIn } from './pages/Auth'
import { Start } from './pages/Start'
import { SystemInfo } from './pages/SystemInfo'
import { Welcome } from './pages/Welcome'
import { Layout } from './components/Layout'
import { EmptyState, Button } from './components/ui'
import { useApp } from './state/AppContext'

/** Client-side gate only. Real enforcement is server side on every endpoint. */
function RequireAuth({ children }: { children: ReactElement }) {
  const { isAuthenticated } = useApp()
  if (!isAuthenticated) return <Navigate to="/signin" replace />
  return children
}

function NotFound() {
  return (
    <Layout>
      <EmptyState
        icon="🧭"
        title="Page not found"
        description="That page does not exist."
        action={
          <Button onClick={() => window.location.assign('/')}>Go to the start</Button>
        }
      />
    </Layout>
  )
}

export function App() {
  return (
    <Routes>
      <Route path="/" element={<Welcome />} />
      <Route path="/signin" element={<SignIn />} />
      <Route path="/register" element={<Register />} />
      <Route path="/system" element={<SystemInfo />} />

      <Route
        path="/start"
        element={
          <RequireAuth>
            <Start />
          </RequireAuth>
        }
      />
      <Route
        path="/conversation/:conversationId"
        element={
          <RequireAuth>
            <Conversation />
          </RequireAuth>
        }
      />
      <Route
        path="/confirm/:conversationId"
        element={
          <RequireAuth>
            <ProfileConfirm />
          </RequireAuth>
        }
      />
      <Route
        path="/pathways"
        element={
          <RequireAuth>
            <Pathways />
          </RequireAuth>
        }
      />
      <Route
        path="/pathway/:recommendationId"
        element={
          <RequireAuth>
            <PathwayDetail />
          </RequireAuth>
        }
      />
      <Route
        path="/progress"
        element={
          <RequireAuth>
            <Progress />
          </RequireAuth>
        }
      />
      <Route
        path="/admin"
        element={
          <RequireAuth>
            <AdminDashboard />
          </RequireAuth>
        }
      />

      <Route path="*" element={<NotFound />} />
    </Routes>
  )
}

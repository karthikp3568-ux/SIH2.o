import { Navigate, Route, Routes } from 'react-router-dom'
import type { ReactElement } from 'react'

import { AdminConsole } from './pages/admin/AdminConsole'
import { Conversation } from './pages/Conversation'
import { PathwayDetail } from './pages/PathwayDetail'
import { Pathways } from './pages/Pathways'
import { MyProfile } from './pages/MyProfile'
import { MySkills } from './pages/MySkills'
import { ProfileConfirm } from './pages/ProfileConfirm'
import { Journey } from './pages/Journey'
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
        icon="compass"
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
        path="/profile"
        element={
          <RequireAuth>
            <MyProfile />
          </RequireAuth>
        }
      />
      <Route
        path="/skills"
        element={
          <RequireAuth>
            <MySkills />
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
        path="/journey"
        element={
          <RequireAuth>
            <Journey />
          </RequireAuth>
        }
      />
      <Route path="/progress" element={<Navigate to="/journey" replace />} />
      <Route
        path="/admin/:section?"
        element={
          <RequireAuth>
            <AdminConsole />
          </RequireAuth>
        }
      />

      <Route path="*" element={<NotFound />} />
    </Routes>
  )
}

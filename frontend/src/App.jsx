import { BrowserRouter, Routes, Route, Navigate } from 'react-router-dom'
import { AuthPage } from './pages/AuthPage'
import { DashboardPage } from './pages/DashboardPage'
import { ProjectPage } from './pages/ProjectPage'
import { AdminPage } from './pages/AdminPage'
import { SupportPage } from './pages/SupportPage'
import { AccountSettingsPage } from './pages/AccountSettingsPage'

function PrivateRoute({ children }) {
  const token = localStorage.getItem('rhq_token')
  return token ? children : <Navigate to="/auth" replace />
}

export default function App() {
  return (
    <BrowserRouter basename="/app">
      <Routes>
        <Route path="/auth" element={<AuthPage />} />
        <Route path="/" element={<PrivateRoute><DashboardPage /></PrivateRoute>} />
        <Route path="/project/:id" element={<PrivateRoute><ProjectPage /></PrivateRoute>} />
        <Route path="/admin" element={<PrivateRoute><AdminPage /></PrivateRoute>} />
        <Route path="/support" element={<PrivateRoute><SupportPage /></PrivateRoute>} />
        <Route path="/account" element={<PrivateRoute><AccountSettingsPage /></PrivateRoute>} />
        <Route path="*" element={<Navigate to="/" replace />} />
      </Routes>
    </BrowserRouter>
  )
}

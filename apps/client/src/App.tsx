import React, { useEffect } from 'react'
import { BrowserRouter, Routes, Route, Navigate, useParams } from 'react-router-dom'
import { Toaster } from 'react-hot-toast'
import ProjectsPage from './pages/ProjectsPage'
import AppLayout from './components/Layout/AppLayout'
import ProjectCachedViews from './pages/ProjectCachedViews'
import { projectsApi } from './api/client'
import { useAppStore } from './store'

// 进入项目时加载当前项目信息
function ProjectLoader() {
  const { projectId } = useParams<{ projectId: string }>()
  const { setCurrentProject } = useAppStore()

  useEffect(() => {
    if (projectId) {
      projectsApi.get(projectId).then(res => setCurrentProject(res.data)).catch(() => {})
    }
  }, [projectId])

  return null
}

export default function App() {
  return (
    <BrowserRouter>
      <Toaster position="top-right" toastOptions={{ duration: 3000 }} />
      <Routes>
        <Route path="/" element={<ProjectsPage />} />
        <Route path="/project/:projectId" element={<><ProjectLoader /><AppLayout /></>}>
          <Route index element={<Navigate to="outline" replace />} />
          <Route path=":tab" element={<ProjectCachedViews />} />
        </Route>
      </Routes>
    </BrowserRouter>
  )
}

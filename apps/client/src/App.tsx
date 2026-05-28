import React, { Suspense, lazy, useEffect } from 'react'
import { BrowserRouter, Routes, Route, Navigate, useParams } from 'react-router-dom'
import { Toaster } from 'react-hot-toast'
import AppLayout from './components/Layout/AppLayout'
import PageSpinner from './components/common/PageSpinner'
import { projectsApi } from './api/client'
import { useAppStore } from './store'
import { useAuthStore } from './store/authStore'

const LoginPage = lazy(() => import('./pages/LoginPage'))
const FanqiePage = lazy(() => import('./pages/FanqiePage'))
const ProjectsPage = lazy(() => import('./pages/ProjectsPage'))
const BookshelfPage = lazy(() => import('./pages/BookshelfPage'))
const ProjectDetailPage = lazy(() => import('./pages/ProjectDetailPage'))
const BookshelfDetailPage = lazy(() => import('./pages/BookshelfDetailPage'))
const ChapterCoherencePage = lazy(() => import('./pages/ChapterCoherencePage'))
const WalletPage = lazy(() => import('./pages/WalletPage'))
const StatsPage = lazy(() => import('./pages/StatsPage'))
const ProjectCachedViews = lazy(() => import('./pages/ProjectCachedViews'))

function withSuspense(children: React.ReactNode) {
  return <Suspense fallback={<PageSpinner />}>{children}</Suspense>
}

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

/**
 * 路由守卫：未登录时跳转到 /login，已登录时渲染子路由。
 * 依赖 useAuthStore.initializing 避免初始化未完成时误跳。
 */
function PrivateRoute({ children }: { children: React.ReactNode }) {
  const { token, initializing } = useAuthStore()

  if (initializing) {
    return (
      <div className="min-h-screen bg-gray-950 flex items-center justify-center">
        <div className="text-gray-500 text-sm">加载中…</div>
      </div>
    )
  }

  if (!token) {
    return <Navigate to="/login" replace />
  }

  return <>{children}</>
}

/**
 * 已登录时访问 /login 自动跳回首页。
 */
function PublicOnlyRoute({ children }: { children: React.ReactNode }) {
  const { token, initializing } = useAuthStore()

  if (initializing) {
    return (
      <div className="min-h-screen bg-gray-950 flex items-center justify-center">
        <div className="text-gray-500 text-sm">加载中…</div>
      </div>
    )
  }

  if (token) {
    return <Navigate to="/" replace />
  }

  return <>{children}</>
}

function AuthInitializer() {
  const { initialize } = useAuthStore()
  useEffect(() => { initialize() }, [])
  return null
}

export default function App() {
  return (
    <BrowserRouter>
      <AuthInitializer />
      <Toaster position="top-right" toastOptions={{ duration: 3000 }} />
      <Routes>
        <Route
          path="/login"
          element={
            <PublicOnlyRoute>
              {withSuspense(<LoginPage />)}
            </PublicOnlyRoute>
          }
        />
        <Route
          path="/"
          element={
            <PrivateRoute>
              {withSuspense(<ProjectsPage />)}
            </PrivateRoute>
          }
        />
        <Route
          path="/bookshelf"
          element={
            <PrivateRoute>
              {withSuspense(<BookshelfPage />)}
            </PrivateRoute>
          }
        />
        <Route
          path="/bookshelf/:projectId/recap"
          element={
            <PrivateRoute>
              {withSuspense(<BookshelfDetailPage />)}
            </PrivateRoute>
          }
        />
        <Route
          path="/bookshelf/:projectId"
          element={
            <PrivateRoute>
              {withSuspense(<ProjectDetailPage />)}
            </PrivateRoute>
          }
        />
        <Route
          path="/coherence-check"
          element={
            <PrivateRoute>
              {withSuspense(<ChapterCoherencePage />)}
            </PrivateRoute>
          }
        />
        <Route
          path="/fanqie"
          element={
            <PrivateRoute>
              {withSuspense(<FanqiePage />)}
            </PrivateRoute>
          }
        />
        <Route
          path="/wallet"
          element={
            <PrivateRoute>
              {withSuspense(<WalletPage />)}
            </PrivateRoute>
          }
        />
        <Route
          path="/stats"
          element={
            <PrivateRoute>
              {withSuspense(<StatsPage />)}
            </PrivateRoute>
          }
        />
        <Route
          path="/project/:projectId"
          element={
            <PrivateRoute>
              <ProjectLoader />
              <AppLayout />
            </PrivateRoute>
          }
        >
          <Route index element={<Navigate to="outline" replace />} />
          <Route path=":tab" element={withSuspense(<ProjectCachedViews />)} />
        </Route>
      </Routes>
    </BrowserRouter>
  )
}

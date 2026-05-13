import React, { useEffect } from 'react'
import { BrowserRouter, Routes, Route, Navigate, useParams } from 'react-router-dom'
import { Toaster } from 'react-hot-toast'
import ProjectsPage from './pages/ProjectsPage'
import BookshelfPage from './pages/BookshelfPage'
import ProjectDetailPage from './pages/ProjectDetailPage'
import BookshelfDetailPage from './pages/BookshelfDetailPage'
import AppLayout from './components/Layout/AppLayout'
import ProjectCachedViews from './pages/ProjectCachedViews'
import ChapterCoherencePage from './pages/ChapterCoherencePage'
import LoginPage from './pages/LoginPage'
import WalletPage from './pages/WalletPage'
import { projectsApi } from './api/client'
import { useAppStore } from './store'
import { useAuthStore } from './store/authStore'

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

  // 应用初始化（校验本地 token）期间显示空白，避免闪烁跳转
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

/**
 * 应用初始化：从 localStorage 读取 token 并调用 /auth/me 验证有效性。
 * 挂载一次即可，不产生额外渲染。
 */
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
        {/* 公开路由：已登录时自动跳回首页 */}
        <Route
          path="/login"
          element={
            <PublicOnlyRoute>
              <LoginPage />
            </PublicOnlyRoute>
          }
        />

        {/* 受保护路由：未登录时跳转 /login */}
        <Route
          path="/"
          element={
            <PrivateRoute>
              <ProjectsPage />
            </PrivateRoute>
          }
        />
        <Route
          path="/bookshelf"
          element={
            <PrivateRoute>
              <BookshelfPage />
            </PrivateRoute>
          }
        />
        {/* 书架上的「小说详情」：封面、简介、生成 Run 日志、写作门控；结构化分区纪要在 /recap */}
        <Route
          path="/bookshelf/:projectId/recap"
          element={
            <PrivateRoute>
              <BookshelfDetailPage />
            </PrivateRoute>
          }
        />
        <Route
          path="/bookshelf/:projectId"
          element={
            <PrivateRoute>
              <ProjectDetailPage />
            </PrivateRoute>
          }
        />
        <Route
          path="/coherence-check"
          element={
            <PrivateRoute>
              <ChapterCoherencePage />
            </PrivateRoute>
          }
        />
        <Route
          path="/wallet"
          element={
            <PrivateRoute>
              <WalletPage />
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
          <Route path=":tab" element={<ProjectCachedViews />} />
        </Route>
      </Routes>
    </BrowserRouter>
  )
}

import { Suspense, lazy, type LazyExoticComponent } from 'react'
import { ConfigProvider, App as AntApp } from 'antd'
import zhCN from 'antd/locale/zh_CN'
import { BrowserRouter, Navigate, Route, Routes } from 'react-router-dom'
import AdminLayout from './layouts/AdminLayout'
import RequireAdminAuth from './components/RequireAdminAuth'
import PageSpinner from './components/PageSpinner'

const AdminLoginPage = lazy(() => import('./pages/AdminLoginPage'))
const LlmCallLogsPage = lazy(() => import('./pages/LlmCallLogsPage'))
const LlmProvidersPage = lazy(() => import('./pages/LlmProvidersPage'))
const ImageProvidersPage = lazy(() => import('./pages/ImageProvidersPage'))
const CoverImageCallLogsPage = lazy(() => import('./pages/CoverImageCallLogsPage'))
const RagRetrievalLogsPage = lazy(() => import('./pages/RagRetrievalLogsPage'))
const RagMetricsPage = lazy(() => import('./pages/RagMetricsPage'))
const MemoryConflictDetectLogsPage = lazy(() => import('./pages/MemoryConflictDetectLogsPage'))
const DebriefListPage = lazy(() => import('./pages/DebriefListPage'))
const NovelManagementPage = lazy(() => import('./pages/NovelManagementPage'))
const ReadingReviewPage = lazy(() => import('./pages/ReadingReviewPage'))
const UserCreditsPage = lazy(() => import('./pages/UserCreditsPage'))
const RedeemCodesPage = lazy(() => import('./pages/RedeemCodesPage'))

export default function App() {
  return (
    <ConfigProvider locale={zhCN}>
      <AntApp>
        <BrowserRouter>
          <Routes>
            <Route
              path="/login"
              element={
                <Suspense fallback={<PageSpinner />}>
                  <AdminLoginPage />
                </Suspense>
              }
            />
            <Route
              path="/"
              element={
                <RequireAdminAuth>
                  <AdminLayout />
                </RequireAdminAuth>
              }
            >
              <Route index element={<Navigate to="/novels" replace />} />
              <Route path="novels" element={<LazyPage page={NovelManagementPage} />} />
              <Route path="debriefs" element={<LazyPage page={DebriefListPage} />} />
              <Route path="llm" element={<LazyPage page={LlmProvidersPage} />} />
              <Route path="image-providers" element={<LazyPage page={ImageProvidersPage} />} />
              <Route path="cover-image-calls" element={<LazyPage page={CoverImageCallLogsPage} />} />
              <Route path="llm-calls" element={<LazyPage page={LlmCallLogsPage} />} />
              <Route path="rag-logs" element={<LazyPage page={RagRetrievalLogsPage} />} />
              <Route path="rag-metrics" element={<LazyPage page={RagMetricsPage} />} />
              <Route path="memory-conflict-logs" element={<LazyPage page={MemoryConflictDetectLogsPage} />} />
              <Route path="reading-review" element={<LazyPage page={ReadingReviewPage} />} />
              <Route path="user-credits" element={<LazyPage page={UserCreditsPage} />} />
              <Route path="redeem-codes" element={<LazyPage page={RedeemCodesPage} />} />
            </Route>
          </Routes>
        </BrowserRouter>
      </AntApp>
    </ConfigProvider>
  )
}

function LazyPage({ page: Page }: { page: LazyExoticComponent<() => JSX.Element> }) {
  return (
    <Suspense fallback={<PageSpinner />}>
      <Page />
    </Suspense>
  )
}

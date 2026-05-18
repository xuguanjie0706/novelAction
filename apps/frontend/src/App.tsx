import { ConfigProvider, App as AntApp } from 'antd'
import zhCN from 'antd/locale/zh_CN'
import { BrowserRouter, Navigate, Route, Routes } from 'react-router-dom'
import AdminLayout from './layouts/AdminLayout'
import RequireAdminAuth from './components/RequireAdminAuth'
import AdminLoginPage from './pages/AdminLoginPage'
import LlmCallLogsPage from './pages/LlmCallLogsPage'
import LlmProvidersPage from './pages/LlmProvidersPage'
import ImageProvidersPage from './pages/ImageProvidersPage'
import CoverImageCallLogsPage from './pages/CoverImageCallLogsPage'
import RagRetrievalLogsPage from './pages/RagRetrievalLogsPage'
import DebriefListPage from './pages/DebriefListPage'
import NovelManagementPage from './pages/NovelManagementPage'
import ReadingReviewPage from './pages/ReadingReviewPage'
import UserCreditsPage from './pages/UserCreditsPage'
import RedeemCodesPage from './pages/RedeemCodesPage'

export default function App() {
  return (
    <ConfigProvider locale={zhCN}>
      <AntApp>
        <BrowserRouter>
          <Routes>
            <Route path="/login" element={<AdminLoginPage />} />
            <Route
              path="/"
              element={
                <RequireAdminAuth>
                  <AdminLayout />
                </RequireAdminAuth>
              }
            >
              <Route index element={<Navigate to="/novels" replace />} />
              <Route path="novels" element={<NovelManagementPage />} />
              <Route path="debriefs" element={<DebriefListPage />} />
              <Route path="llm" element={<LlmProvidersPage />} />
              <Route path="image-providers" element={<ImageProvidersPage />} />
              <Route path="cover-image-calls" element={<CoverImageCallLogsPage />} />
              <Route path="llm-calls" element={<LlmCallLogsPage />} />
              <Route path="rag-logs" element={<RagRetrievalLogsPage />} />
              <Route path="reading-review" element={<ReadingReviewPage />} />
              <Route path="user-credits" element={<UserCreditsPage />} />
              <Route path="redeem-codes" element={<RedeemCodesPage />} />
            </Route>
          </Routes>
        </BrowserRouter>
      </AntApp>
    </ConfigProvider>
  )
}

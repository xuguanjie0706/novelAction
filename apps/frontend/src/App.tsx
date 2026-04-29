import { ConfigProvider, App as AntApp } from 'antd'
import zhCN from 'antd/locale/zh_CN'
import { BrowserRouter, Navigate, Route, Routes } from 'react-router-dom'
import AdminLayout from './layouts/AdminLayout'
import LlmProvidersPage from './pages/LlmProvidersPage'
import NovelManagementPage from './pages/NovelManagementPage'
import ReadingReviewPage from './pages/ReadingReviewPage'

export default function App() {
  return (
    <ConfigProvider locale={zhCN}>
      <AntApp>
        <BrowserRouter>
          <Routes>
            <Route path="/" element={<AdminLayout />}>
              <Route index element={<Navigate to="/novels" replace />} />
              <Route path="novels" element={<NovelManagementPage />} />
              <Route path="llm" element={<LlmProvidersPage />} />
              <Route path="reading-review" element={<ReadingReviewPage />} />
            </Route>
          </Routes>
        </BrowserRouter>
      </AntApp>
    </ConfigProvider>
  )
}

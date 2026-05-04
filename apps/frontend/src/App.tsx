import { ConfigProvider, App as AntApp } from 'antd'
import zhCN from 'antd/locale/zh_CN'
import { BrowserRouter, Navigate, Route, Routes } from 'react-router-dom'
import AdminLayout from './layouts/AdminLayout'
import LlmCallLogsPage from './pages/LlmCallLogsPage'
import LlmProvidersPage from './pages/LlmProvidersPage'
import ImageProvidersPage from './pages/ImageProvidersPage'
import DebriefListPage from './pages/DebriefListPage'
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
              <Route path="debriefs" element={<DebriefListPage />} />
              <Route path="llm" element={<LlmProvidersPage />} />
              <Route path="image-providers" element={<ImageProvidersPage />} />
              <Route path="llm-calls" element={<LlmCallLogsPage />} />
              <Route path="reading-review" element={<ReadingReviewPage />} />
            </Route>
          </Routes>
        </BrowserRouter>
      </AntApp>
    </ConfigProvider>
  )
}

import { Spin } from 'antd'

/** 管理后台懒加载路由 chunk 等待占位 */
export default function PageSpinner() {
  return (
    <div style={{ display: 'flex', justifyContent: 'center', padding: 48 }}>
      <Spin size="large" tip="加载中…" />
    </div>
  )
}

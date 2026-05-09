import { Navigate, useLocation } from 'react-router-dom'

import { getAdminToken } from '../api/auth'

/**
 * 管理后台路由守卫：未持有 token → 跳转 /login。
 *
 * 不在这里做服务端 token 探活，避免阻塞首屏；token 失效会由 axios 拦截器
 * 在首次 401 时统一清理并跳登录页。
 */
export default function RequireAdminAuth({ children }: { children: React.ReactNode }) {
  const token = getAdminToken()
  const location = useLocation()
  if (!token) {
    return <Navigate to="/login" replace state={{ from: location }} />
  }
  return <>{children}</>
}

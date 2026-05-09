import { LockOutlined, UserOutlined } from '@ant-design/icons'
import { App, Button, Card, Form, Input, Typography } from 'antd'
import axios from 'axios'
import { useState } from 'react'
import { useNavigate } from 'react-router-dom'

import { setAdminAuth } from '../api/auth'

interface LoginValues {
  username: string
  password: string
}

interface LoginResponse {
  access_token: string
  token_type: string
  role: string
  username: string
}

/**
 * 管理后台登录页。
 *
 * 与创作端登录完全隔离：调用 /api/v1/admin/auth/login，token 写入
 * `localStorage('novelAction:admin-token')`。后端服务端未配置
 * ADMIN_USERNAME/ADMIN_PASSWORD 时返回 503，此页面会显式提示。
 */
export default function AdminLoginPage() {
  const navigate = useNavigate()
  const { message } = App.useApp()
  const [submitting, setSubmitting] = useState(false)

  const onFinish = async (values: LoginValues) => {
    setSubmitting(true)
    try {
      // 直接用 axios 而非 http 实例：避免本次请求被 401 拦截器误清 token。
      const { data } = await axios.post<LoginResponse>(
        '/api/v1/admin/auth/login',
        values,
        { timeout: 30_000 },
      )
      setAdminAuth(data.access_token, data.username)
      message.success('登录成功')
      navigate('/novels', { replace: true })
    } catch (err: unknown) {
      const e = err as { response?: { status?: number; data?: { detail?: string } } }
      const status = e?.response?.status
      const detail = e?.response?.data?.detail
      if (status === 503) {
        message.error(detail || '管理后台登录入口未启用，请检查后端 .env 的 ADMIN_USERNAME/ADMIN_PASSWORD')
      } else if (status === 401) {
        message.error(detail || '用户名或密码错误')
      } else {
        message.error(detail || '登录失败，请检查后端是否可达')
      }
    } finally {
      setSubmitting(false)
    }
  }

  return (
    <div
      style={{
        minHeight: '100vh',
        display: 'flex',
        alignItems: 'center',
        justifyContent: 'center',
        background: 'linear-gradient(135deg, #1f2a48 0%, #364268 100%)',
      }}
    >
      <Card style={{ width: 360, boxShadow: '0 12px 32px rgba(0,0,0,0.18)' }}>
        <Typography.Title level={3} style={{ textAlign: 'center', marginBottom: 8 }}>
          小说系统 · 后台
        </Typography.Title>
        <Typography.Paragraph type="secondary" style={{ textAlign: 'center', marginBottom: 24 }}>
          仅限管理员账号登录
        </Typography.Paragraph>
        <Form<LoginValues>
          layout="vertical"
          requiredMark={false}
          onFinish={onFinish}
          autoComplete="off"
        >
          <Form.Item
            name="username"
            rules={[{ required: true, message: '请输入用户名' }]}
          >
            <Input
              prefix={<UserOutlined />}
              placeholder="用户名"
              autoFocus
              size="large"
            />
          </Form.Item>
          <Form.Item
            name="password"
            rules={[{ required: true, message: '请输入密码' }]}
          >
            <Input.Password
              prefix={<LockOutlined />}
              placeholder="密码"
              size="large"
            />
          </Form.Item>
          <Form.Item style={{ marginBottom: 0 }}>
            <Button
              type="primary"
              htmlType="submit"
              block
              size="large"
              loading={submitting}
            >
              登录
            </Button>
          </Form.Item>
        </Form>
      </Card>
    </div>
  )
}

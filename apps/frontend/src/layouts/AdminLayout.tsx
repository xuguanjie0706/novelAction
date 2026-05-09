import { Button, Layout, Menu, Popconfirm, Space, Typography, theme } from 'antd'
import {
  BookOutlined,
  CheckSquareOutlined,
  DatabaseOutlined,
  ExperimentOutlined,
  FileImageOutlined,
  LogoutOutlined,
  PictureOutlined,
  ReadOutlined,
  UserOutlined,
} from '@ant-design/icons'
import { Outlet, useLocation, useNavigate } from 'react-router-dom'
import { useMemo } from 'react'

import { clearAdminAuth, getAdminUsername } from '../api/auth'

const { Header, Sider, Content } = Layout

export default function AdminLayout() {
  const navigate = useNavigate()
  const loc = useLocation()
  const username = getAdminUsername()

  const handleLogout = () => {
    clearAdminAuth()
    navigate('/login', { replace: true })
  }
  const {
    token: { colorBgContainer, borderRadiusLG },
  } = theme.useToken()

  const selected = useMemo(() => {
    if (loc.pathname.startsWith('/novels')) return ['/novels']
    if (loc.pathname.startsWith('/debriefs')) return ['/debriefs']
    if (loc.pathname.startsWith('/reading-review')) return ['/reading-review']
    if (loc.pathname.startsWith('/llm-calls')) return ['/llm-calls']
    if (loc.pathname.startsWith('/cover-image-calls')) return ['/cover-image-calls']
    if (loc.pathname.startsWith('/image-providers')) return ['/image-providers']
    if (loc.pathname.startsWith('/llm')) return ['/llm']
    return ['/novels']
  }, [loc.pathname])

  return (
    <Layout style={{ minHeight: '100vh' }}>
      <Sider breakpoint="lg" collapsedWidth={0}>
        <div
          style={{
            height: 48,
            margin: 12,
            display: 'flex',
            alignItems: 'center',
            justifyContent: 'center',
            color: '#fff',
            fontWeight: 600,
            fontSize: 14,
          }}
        >
          小说系统 · 后台
        </div>
        <Menu
          theme="dark"
          mode="inline"
          selectedKeys={selected}
          items={[
            {
              key: '/novels',
              icon: <BookOutlined />,
              label: '小说管理',
              onClick: () => navigate('/novels'),
            },
            {
              key: '/debriefs',
              icon: <CheckSquareOutlined />,
              label: '复盘列表',
              onClick: () => navigate('/debriefs'),
            },
            {
              key: '/llm',
              icon: <ExperimentOutlined />,
              label: '大模型',
              onClick: () => navigate('/llm'),
            },
            {
              key: '/image-providers',
              icon: <PictureOutlined />,
              label: '图片模型',
              onClick: () => navigate('/image-providers'),
            },
            {
              key: '/cover-image-calls',
              icon: <FileImageOutlined />,
              label: '封面生成记录',
              onClick: () => navigate('/cover-image-calls'),
            },
            {
              key: '/llm-calls',
              icon: <DatabaseOutlined />,
              label: 'LLM调用记录',
              onClick: () => navigate('/llm-calls'),
            },
            {
              key: '/reading-review',
              icon: <ReadOutlined />,
              label: '小说评测',
              onClick: () => navigate('/reading-review'),
            },
          ]}
        />
      </Sider>
      <Layout style={{ minHeight: '100vh', overflow: 'hidden' }}>
        <Header
          style={{
            padding: '0 24px',
            background: colorBgContainer,
            lineHeight: '56px',
            display: 'flex',
            alignItems: 'center',
            justifyContent: 'space-between',
          }}
        >
          <span style={{ fontWeight: 600 }}>管理后台</span>
          <Space>
            <Typography.Text type="secondary">
              <UserOutlined /> {username || '管理员'}
            </Typography.Text>
            <Popconfirm title="确认退出登录？" okText="退出" cancelText="取消" onConfirm={handleLogout}>
              <Button type="text" icon={<LogoutOutlined />}>
                退出
              </Button>
            </Popconfirm>
          </Space>
        </Header>
        <Content style={{ flex: 1, minHeight: 0, padding: 24, overflow: 'hidden' }}>
          <div
            style={{
              padding: 24,
              height: '100%',
              background: colorBgContainer,
              borderRadius: borderRadiusLG,
              overflow: 'hidden',
            }}
          >
            <Outlet />
          </div>
        </Content>
      </Layout>
    </Layout>
  )
}

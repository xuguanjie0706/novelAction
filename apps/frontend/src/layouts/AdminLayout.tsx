import { Layout, Menu, theme } from 'antd'
import {
  BookOutlined,
  DatabaseOutlined,
  ExperimentOutlined,
  PictureOutlined,
  ReadOutlined,
} from '@ant-design/icons'
import { Outlet, useLocation, useNavigate } from 'react-router-dom'
import { useMemo } from 'react'

const { Header, Sider, Content } = Layout

export default function AdminLayout() {
  const navigate = useNavigate()
  const loc = useLocation()
  const {
    token: { colorBgContainer, borderRadiusLG },
  } = theme.useToken()

  const selected = useMemo(() => {
    if (loc.pathname.startsWith('/novels')) return ['/novels']
    if (loc.pathname.startsWith('/reading-review')) return ['/reading-review']
    if (loc.pathname.startsWith('/llm-calls')) return ['/llm-calls']
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
        <Header style={{ padding: '0 24px', background: colorBgContainer, lineHeight: '56px' }}>
          <span style={{ fontWeight: 600 }}>管理后台</span>
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

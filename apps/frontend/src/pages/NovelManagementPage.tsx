import { App, Button, Card, Col, Empty, List, Popconfirm, Row, Select, Space, Tag, Typography } from 'antd'
import { useCallback, useEffect, useMemo, useState } from 'react'
import { useSearchParams } from 'react-router-dom'
import { http } from '../api/http'
import type { ReviewChapter, ReviewProject } from '../types/review'

function htmlToPlainText(input: string | undefined) {
  if (!input) return ''
  return input
    .replace(/<style[\s\S]*?<\/style>/gi, '')
    .replace(/<script[\s\S]*?<\/script>/gi, '')
    .replace(/<br\s*\/?>/gi, '\n')
    .replace(/<\/p>/gi, '\n\n')
    .replace(/<[^>]+>/g, '')
    .replace(/&nbsp;/g, ' ')
    .replace(/&amp;/g, '&')
    .replace(/&lt;/g, '<')
    .replace(/&gt;/g, '>')
    .replace(/&#39;/g, "'")
    .replace(/&quot;/g, '"')
    .replace(/\n{3,}/g, '\n\n')
    .trim()
}

export default function NovelManagementPage() {
  const { message } = App.useApp()
  const [searchParams, setSearchParams] = useSearchParams()
  const [projects, setProjects] = useState<ReviewProject[]>([])
  const [loading, setLoading] = useState(false)
  const [deleteLoading, setDeleteLoading] = useState(false)
  const [projectId, setProjectId] = useState<string>()
  const [chapters, setChapters] = useState<ReviewChapter[]>([])
  const [selectedChapterId, setSelectedChapterId] = useState<string>()

  const loadProjects = useCallback(async () => {
    setLoading(true)
    try {
      const { data } = await http.get<ReviewProject[]>('/api/v1/projects/')
      setProjects(data)
      const queryProjectId = searchParams.get('projectId')
      const defaultProjectId = queryProjectId || data[0]?.id
      if (defaultProjectId) setProjectId(defaultProjectId)
    } catch {
      message.error('加载小说列表失败')
    } finally {
      setLoading(false)
    }
  }, [message, searchParams])

  const loadChapters = useCallback(async (pid: string) => {
    try {
      const { data } = await http.get<ReviewChapter[]>(`/api/v1/projects/${pid}/chapters/`)
      setChapters(data)
      const queryChapterId = searchParams.get('chapterId')
      const exists = queryChapterId && data.some((item) => item.id === queryChapterId)
      setSelectedChapterId(exists ? queryChapterId : data[0]?.id)
    } catch {
      message.error('加载章节失败')
      setChapters([])
      setSelectedChapterId(undefined)
    }
  }, [message, searchParams])

  useEffect(() => {
    void loadProjects()
  }, [loadProjects])

  useEffect(() => {
    if (!projectId) return
    void loadChapters(projectId)
  }, [projectId, loadChapters])

  useEffect(() => {
    if (!projectId) return
    const next = new URLSearchParams(searchParams)
    next.set('projectId', projectId)
    if (selectedChapterId) {
      next.set('chapterId', selectedChapterId)
    } else {
      next.delete('chapterId')
    }
    setSearchParams(next, { replace: true })
  }, [projectId, searchParams, selectedChapterId, setSearchParams])

  const selectedChapter = useMemo(
    () => chapters.find((item) => item.id === selectedChapterId),
    [chapters, selectedChapterId],
  )
  const chapterText = useMemo(() => htmlToPlainText(selectedChapter?.content), [selectedChapter?.content])
  const selectedProject = useMemo(
    () => projects.find((item) => item.id === projectId),
    [projectId, projects],
  )

  const handleDeleteProject = useCallback(async () => {
    if (!projectId) {
      message.warning('请先选择要删除的小说')
      return
    }
    setDeleteLoading(true)
    try {
      await http.delete(`/api/v1/projects/${projectId}`)
      const remaining = projects.filter((item) => item.id !== projectId)
      setProjects(remaining)
      setProjectId(remaining[0]?.id)
      setChapters([])
      setSelectedChapterId(undefined)
      message.success('小说已删除')
    } catch {
      message.error('删除失败，请稍后重试')
    } finally {
      setDeleteLoading(false)
    }
  }, [message, projectId, projects])

  return (
    <div style={{ height: '100%', display: 'flex', flexDirection: 'column', overflow: 'hidden' }}>
      <Space wrap style={{ justifyContent: 'space-between', width: '100%' }}>
        <Typography.Title level={4} style={{ margin: 0 }}>
          小说管理
        </Typography.Title>
        <Space>
          <Select
            style={{ minWidth: 280 }}
            placeholder="选择小说"
            options={projects.map((item) => ({ value: item.id, label: item.title }))}
            value={projectId}
            loading={loading}
            onChange={setProjectId}
          />
          <Popconfirm
            title="确认删除小说？"
            description={selectedProject ? `将删除《${selectedProject.title}》及其全部章节，此操作不可恢复。` : '此操作不可恢复。'}
            okText="确认删除"
            cancelText="取消"
            okButtonProps={{ danger: true, loading: deleteLoading }}
            onConfirm={() => void handleDeleteProject()}
            disabled={!projectId}
          >
            <Button danger disabled={!projectId} loading={deleteLoading}>
              删除小说
            </Button>
          </Popconfirm>
        </Space>
      </Space>

      <Row gutter={16} style={{ marginTop: 16, flex: 1, minHeight: 0 }}>
        <Col span={7} style={{ height: '100%' }}>
          <Card
            title={`章节列表（${chapters.length}）`}
            bodyStyle={{ padding: 0, flex: 1, minHeight: 0, overflowY: 'auto' }}
            style={{ height: '100%', display: 'flex', flexDirection: 'column' }}
          >
            {chapters.length === 0 ? (
              <div style={{ padding: 24 }}>
                <Empty description="暂无章节" />
              </div>
            ) : (
              <List
                dataSource={chapters}
                renderItem={(item) => (
                  <List.Item
                    onClick={() => setSelectedChapterId(item.id)}
                    style={{
                      cursor: 'pointer',
                      padding: '10px 16px',
                      background: item.id === selectedChapterId ? '#e6f4ff' : 'transparent',
                    }}
                  >
                    <Space direction="vertical" size={2} style={{ width: '100%' }}>
                      <Typography.Text strong>第{item.sort_order + 1}章 · {item.title || '未命名'}</Typography.Text>
                      <Typography.Text type="secondary">字数：{item.word_count ?? 0}</Typography.Text>
                    </Space>
                  </List.Item>
                )}
              />
            )}
          </Card>
        </Col>
        <Col span={17} style={{ height: '100%' }}>
          {!selectedChapter ? (
            <Card style={{ height: '100%' }}>
              <Empty description="请选择左侧章节查看正文" />
            </Card>
          ) : (
            <Space direction="vertical" size="middle" style={{ width: '100%', height: '100%' }}>
              <Card title={`第${selectedChapter.sort_order + 1}章 · ${selectedChapter.title || '未命名'}`}>
                <Space wrap>
                  <Tag color="blue">字数：{selectedChapter.word_count ?? chapterText.length}</Tag>
                  <Tag color={selectedChapter.status === 'published' ? 'green' : 'default'}>
                    状态：{selectedChapter.status || 'draft'}
                  </Tag>
                  <Tag>
                    更新时间：{selectedChapter.updated_at ? new Date(selectedChapter.updated_at).toLocaleString() : '未知'}
                  </Tag>
                </Space>
              </Card>
              <Card
                title="正文"
                bodyStyle={{ flex: 1, minHeight: 0, overflowY: 'auto' }}
                style={{ flex: 1, minHeight: 0, display: 'flex', flexDirection: 'column' }}
              >
                {chapterText ? (
                  <Typography.Paragraph style={{ marginBottom: 0, whiteSpace: 'pre-wrap', lineHeight: 1.9 }}>
                    {chapterText}
                  </Typography.Paragraph>
                ) : (
                  <Empty description="该章节暂无正文内容" />
                )}
              </Card>
            </Space>
          )}
        </Col>
      </Row>
    </div>
  )
}

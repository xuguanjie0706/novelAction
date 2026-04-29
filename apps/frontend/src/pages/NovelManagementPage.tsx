import { App, Button, Card, Col, Empty, List, Modal, Popconfirm, Row, Select, Space, Tag, Typography } from 'antd'
import { useCallback, useEffect, useMemo, useState } from 'react'
import { useSearchParams } from 'react-router-dom'
import { http } from '../api/http'
import type {
  QualityReport,
  ReviewChapter,
  ReviewChapterIndex,
  ReviewForeshadow,
  ReviewMemoryChunk,
  ReviewProject,
} from '../types/review'

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
  const [chapterDetailLoading, setChapterDetailLoading] = useState(false)
  const [chapterMemories, setChapterMemories] = useState<ReviewMemoryChunk[]>([])
  const [chapterIndex, setChapterIndex] = useState<ReviewChapterIndex | null>(null)
  const [chapterForeshadows, setChapterForeshadows] = useState<ReviewForeshadow[]>([])
  const [jsonModalOpen, setJsonModalOpen] = useState(false)

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
  const selectedChapterQuality = (selectedChapter?.last_quality_report ?? null) as QualityReport | null

  const loadChapterDetails = useCallback(async (pid: string, chapterId: string) => {
    setChapterDetailLoading(true)
    try {
      const [memoriesRes, chapterIndexRes, foreshadowsRes] = await Promise.allSettled([
        http.get<ReviewMemoryChunk[]>(`/api/v1/projects/${pid}/ai/memory`),
        http.get<ReviewChapterIndex>(`/api/v1/projects/${pid}/chapter-indexes/chapter/${chapterId}`),
        http.get<ReviewForeshadow[]>(`/api/v1/projects/${pid}/foreshadows/`),
      ])

      if (memoriesRes.status === 'fulfilled') {
        setChapterMemories(memoriesRes.value.data.filter((item) => item.chapter_id === chapterId))
      } else {
        setChapterMemories([])
      }

      if (chapterIndexRes.status === 'fulfilled') {
        setChapterIndex(chapterIndexRes.value.data)
      } else {
        setChapterIndex(null)
      }

      if (foreshadowsRes.status === 'fulfilled') {
        setChapterForeshadows(
          foreshadowsRes.value.data.filter(
            (item) => item.laid_chapter_id === chapterId || item.resolved_chapter_id === chapterId,
          ),
        )
      } else {
        setChapterForeshadows([])
      }
    } catch {
      setChapterMemories([])
      setChapterIndex(null)
      setChapterForeshadows([])
    } finally {
      setChapterDetailLoading(false)
    }
  }, [])

  useEffect(() => {
    if (!projectId || !selectedChapterId) {
      setChapterMemories([])
      setChapterIndex(null)
      setChapterForeshadows([])
      return
    }
    void loadChapterDetails(projectId, selectedChapterId)
  }, [loadChapterDetails, projectId, selectedChapterId])

  const renderAnyValue = (value: unknown) => {
    if (value == null || value === '') return '—'
    if (typeof value === 'string' || typeof value === 'number' || typeof value === 'boolean') return String(value)
    return JSON.stringify(value)
  }

  const chapterFullJson = useMemo(() => JSON.stringify({
    chapter: selectedChapter ?? null,
    quality_report: selectedChapterQuality,
    memories: chapterMemories,
    chapter_index: chapterIndex,
    foreshadows: chapterForeshadows,
  }, null, 2), [chapterForeshadows, chapterIndex, chapterMemories, selectedChapter, selectedChapterQuality])

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
    <div style={{ height: '100%', minHeight: 0, display: 'flex', flexDirection: 'column', overflow: 'hidden' }}>
      <div
        style={{
          position: 'sticky',
          top: 0,
          zIndex: 10,
          background: '#fff',
          paddingBottom: 8,
        }}
      >
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
      </div>

      <Row gutter={16} style={{ marginTop: 16, flex: 1, minHeight: 0, overflow: 'hidden' }}>
        <Col span={7} style={{ height: '100%', minHeight: 0, overflow: 'hidden' }}>
          <Card
            title={`章节列表（${chapters.length}）`}
            bodyStyle={{ padding: 0, flex: 1, minHeight: 0, overflowY: 'auto' }}
            style={{ height: '100%', minHeight: 0, overflow: 'hidden', display: 'flex', flexDirection: 'column' }}
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
                    </Space>
                  </List.Item>
                )}
              />
            )}
          </Card>
        </Col>
        <Col span={17} style={{ height: '100%', minHeight: 0, overflow: 'hidden' }}>
          {!selectedChapter ? (
            <Card style={{ height: '100%' }}>
              <Empty description="请选择左侧章节查看对账详情" />
            </Card>
          ) : (
            <Space direction="vertical" size="middle" style={{ width: '100%', height: '100%' }}>
              <Card
                title={`第${selectedChapter.sort_order + 1}章 · ${selectedChapter.title || '未命名'}`}
                extra={(
                  <Button size="small" onClick={() => setJsonModalOpen(true)}>
                    查看完整 JSON
                  </Button>
                )}
              >
                <Space wrap>
                  <Tag color="blue">字数：{selectedChapter.word_count ?? chapterText.length}</Tag>
                  <Tag color={selectedChapter.status === 'published' ? 'green' : 'default'}>
                    状态：{selectedChapter.status || 'draft'}
                  </Tag>
                  <Tag>
                    更新时间：{selectedChapter.updated_at ? new Date(selectedChapter.updated_at).toLocaleString() : '未知'}
                  </Tag>
                  <Tag color={selectedChapter.last_quality_score != null && selectedChapter.last_quality_score < 70 ? 'red' : 'green'}>
                    最近质检分：{selectedChapter.last_quality_score ?? '未评测'}
                  </Tag>
                </Space>
              </Card>
              <Row gutter={16} style={{ flex: 1, minHeight: 0 }}>
                <Col span={12} style={{ minHeight: 0 }}>
                  <Space direction="vertical" size="middle" style={{ width: '100%' }}>
                    <Card loading={chapterDetailLoading} title="复盘记录（Memory）" bodyStyle={{ maxHeight: 220, overflowY: 'auto' }}>
                      {chapterMemories.length === 0 ? (
                        <Empty image={Empty.PRESENTED_IMAGE_SIMPLE} description="暂无复盘记录" />
                      ) : (
                        <List
                          size="small"
                          dataSource={chapterMemories}
                          renderItem={(item) => (
                            <List.Item>
                              <Space direction="vertical" size={2} style={{ width: '100%' }}>
                                <Space>
                                  <Tag color="purple">{item.memory_type}</Tag>
                                  <Typography.Text strong>{item.title || '未命名复盘'}</Typography.Text>
                                </Space>
                                <Typography.Text type="secondary">{item.content}</Typography.Text>
                              </Space>
                            </List.Item>
                          )}
                        />
                      )}
                    </Card>
                    <Card loading={chapterDetailLoading} title="质检结果" bodyStyle={{ maxHeight: 220, overflowY: 'auto' }}>
                      {!selectedChapterQuality ? (
                        <Empty image={Empty.PRESENTED_IMAGE_SIMPLE} description="暂无质检报告" />
                      ) : (
                        <Space direction="vertical" size="small" style={{ width: '100%' }}>
                          <Typography.Text strong>总分：{selectedChapterQuality.overall_score ?? '—'}</Typography.Text>
                          <Space wrap>
                            {Object.entries(selectedChapterQuality.dimensions || {}).map(([key, dim]) => (
                              <Tag key={key} color={dim.status === 'fail' ? 'red' : dim.status === 'warning' ? 'orange' : 'blue'}>
                                {key}: {dim.score}
                              </Tag>
                            ))}
                          </Space>
                          <Typography.Text type="secondary">{selectedChapterQuality.summary || '暂无总结'}</Typography.Text>
                        </Space>
                      )}
                    </Card>
                  </Space>
                </Col>
                <Col span={12} style={{ minHeight: 0 }}>
                  <Space direction="vertical" size="middle" style={{ width: '100%' }}>
                    <Card loading={chapterDetailLoading} title="情节档案（Chapter Index）" bodyStyle={{ maxHeight: 220, overflowY: 'auto' }}>
                      {!chapterIndex ? (
                        <Empty image={Empty.PRESENTED_IMAGE_SIMPLE} description="暂无情节档案" />
                      ) : (
                        <Space direction="vertical" size="small" style={{ width: '100%' }}>
                          <Typography.Text>故事日：{chapterIndex.story_day || '—'}</Typography.Text>
                          <Typography.Text>章末钩子：{chapterIndex.ending_hook || '—'}</Typography.Text>
                          <Typography.Text>钩子强度：{chapterIndex.hook_strength ?? '—'}</Typography.Text>
                          <Typography.Text strong>核心事件</Typography.Text>
                          <List
                            size="small"
                            bordered
                            dataSource={chapterIndex.core_events || []}
                            locale={{ emptyText: '暂无事件' }}
                            renderItem={(item) => <List.Item>{renderAnyValue(item)}</List.Item>}
                          />
                        </Space>
                      )}
                    </Card>
                    <Card loading={chapterDetailLoading} title="伏笔对账" bodyStyle={{ maxHeight: 220, overflowY: 'auto' }}>
                      {chapterForeshadows.length === 0 ? (
                        <Empty image={Empty.PRESENTED_IMAGE_SIMPLE} description="本章暂无伏笔相关记录" />
                      ) : (
                        <List
                          size="small"
                          dataSource={chapterForeshadows}
                          renderItem={(item) => {
                            const phase = item.laid_chapter_id === selectedChapter.id ? '埋设' : '回收'
                            return (
                              <List.Item>
                                <Space direction="vertical" size={2} style={{ width: '100%' }}>
                                  <Space>
                                    <Tag color={phase === '埋设' ? 'blue' : 'green'}>{phase}</Tag>
                                    <Tag>{item.status}</Tag>
                                    <Typography.Text strong>{item.title}</Typography.Text>
                                  </Space>
                                  <Typography.Text type="secondary">{item.description || '—'}</Typography.Text>
                                </Space>
                              </List.Item>
                            )
                          }}
                        />
                      )}
                    </Card>
                  </Space>
                </Col>
              </Row>
              <Card
                title="正文"
                bodyStyle={{ maxHeight: 280, overflowY: 'auto' }}
              >
                {chapterText ? (
                  <Typography.Paragraph style={{ marginBottom: 0, whiteSpace: 'pre-wrap', lineHeight: 1.9 }}>
                    {chapterText}
                  </Typography.Paragraph>
                ) : (
                  <Empty description="该章节暂无正文内容" />
                )}
              </Card>
              <Modal
                title="章节完整 JSON"
                open={jsonModalOpen}
                onCancel={() => setJsonModalOpen(false)}
                footer={null}
                width={960}
              >
                <pre
                  style={{
                    margin: 0,
                    maxHeight: '70vh',
                    overflow: 'auto',
                    background: '#fafafa',
                    border: '1px solid #f0f0f0',
                    borderRadius: 8,
                    padding: 12,
                    fontSize: 12,
                    lineHeight: 1.5,
                  }}
                >
                  {chapterFullJson}
                </pre>
              </Modal>
            </Space>
          )}
        </Col>
      </Row>
    </div>
  )
}

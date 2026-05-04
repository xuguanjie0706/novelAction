import { App, Button, Card, Empty, Input, Select, Space, Table, Tag, Typography } from 'antd'
import type { ColumnsType } from 'antd/es/table'
import { useCallback, useEffect, useMemo, useState } from 'react'
import { useNavigate, useSearchParams } from 'react-router-dom'
import { http } from '../api/http'
import type { ReviewChapter, ReviewMemoryChunk, ReviewProject } from '../types/review'

const MEMORY_TYPE_LABELS: Record<string, string> = {
  event: '事件',
  character_state: '人物状态',
  foreshadow: '伏笔',
  setting: '设定',
  conflict: '冲突',
}

type Row = ReviewMemoryChunk & { chapterSort: number; chapterTitle: string }

export default function DebriefListPage() {
  const { message } = App.useApp()
  const navigate = useNavigate()
  const [searchParams, setSearchParams] = useSearchParams()

  const [projects, setProjects] = useState<ReviewProject[]>([])
  const [projectsLoading, setProjectsLoading] = useState(false)
  const [projectId, setProjectId] = useState<string>()

  const [chapters, setChapters] = useState<ReviewChapter[]>([])
  const [chaptersLoading, setChaptersLoading] = useState(false)

  const [memories, setMemories] = useState<ReviewMemoryChunk[]>([])
  const [memoriesLoading, setMemoriesLoading] = useState(false)

  const [chapterFilter, setChapterFilter] = useState<string | 'all'>('all')
  const [typeFilter, setTypeFilter] = useState<string | 'all'>('all')
  const [keyword, setKeyword] = useState('')

  const loadProjects = useCallback(async () => {
    setProjectsLoading(true)
    try {
      const { data } = await http.get<ReviewProject[]>('/api/v1/projects/')
      setProjects(data)
      const qPid = searchParams.get('projectId')
      const nextId = qPid && data.some((p) => p.id === qPid) ? qPid : data[0]?.id
      setProjectId(nextId)
    } catch {
      message.error('加载小说列表失败')
    } finally {
      setProjectsLoading(false)
    }
  }, [message, searchParams])

  useEffect(() => {
    void loadProjects()
  }, [loadProjects])

  const loadChapters = useCallback(
    async (pid: string) => {
      setChaptersLoading(true)
      try {
        const { data } = await http.get<ReviewChapter[]>(`/api/v1/projects/${pid}/chapters/`)
        setChapters(data)
      } catch {
        message.error('加载章节失败')
        setChapters([])
      } finally {
        setChaptersLoading(false)
      }
    },
    [message],
  )

  const loadMemories = useCallback(
    async (pid: string) => {
      setMemoriesLoading(true)
      try {
        const { data } = await http.get<ReviewMemoryChunk[]>(`/api/v1/projects/${pid}/ai/memory`)
        setMemories(data)
      } catch {
        message.error('加载记忆库失败')
        setMemories([])
      } finally {
        setMemoriesLoading(false)
      }
    },
    [message],
  )

  useEffect(() => {
    if (!projectId) {
      setChapters([])
      setMemories([])
      return
    }
    void loadChapters(projectId)
    void loadMemories(projectId)
  }, [projectId, loadChapters, loadMemories])

  useEffect(() => {
    if (!projectId) return
    const next = new URLSearchParams(searchParams)
    next.set('projectId', projectId)
    setSearchParams(next, { replace: true })
  }, [projectId, searchParams, setSearchParams])

  const chapterById = useMemo(() => {
    const m = new Map<string, ReviewChapter>()
    for (const c of chapters) m.set(c.id, c)
    return m
  }, [chapters])

  /** 与小说管理页一致：仅展示绑定到某一写作章节的记忆（含复盘提交与章内提取） */
  const rows: Row[] = useMemo(() => {
    const bound = memories.filter((item) => item.chapter_id)
    const out: Row[] = bound.map((item) => {
      const ch = item.chapter_id ? chapterById.get(item.chapter_id) : undefined
      const sort = ch?.sort_order ?? item.chapter_number ?? 0
      const title = ch?.title || '（章节已删或未知）'
      return {
        ...item,
        chapterSort: sort,
        chapterTitle: title,
      }
    })
    out.sort((a, b) => {
      if (a.chapterSort !== b.chapterSort) return a.chapterSort - b.chapterSort
      const ta = a.created_at ? new Date(a.created_at).getTime() : 0
      const tb = b.created_at ? new Date(b.created_at).getTime() : 0
      return ta - tb
    })
    return out
  }, [memories, chapterById])

  const filteredRows = useMemo(() => {
    let list = rows
    if (chapterFilter !== 'all') {
      list = list.filter((r) => r.chapter_id === chapterFilter)
    }
    if (typeFilter !== 'all') {
      list = list.filter((r) => r.memory_type === typeFilter)
    }
    const q = keyword.trim().toLowerCase()
    if (q) {
      list = list.filter((r) => {
        const t = (r.title || '').toLowerCase()
        const c = (r.content || '').toLowerCase()
        const tags = (r.tags || []).join(' ').toLowerCase()
        return t.includes(q) || c.includes(q) || tags.includes(q)
      })
    }
    return list
  }, [rows, chapterFilter, typeFilter, keyword])

  const memoryTypeOptions = useMemo(() => {
    const s = new Set<string>()
    for (const r of rows) s.add(r.memory_type)
    return [...s].sort()
  }, [rows])

  const columns: ColumnsType<Row> = useMemo(
    () => [
      {
        title: '章节',
        width: 220,
        render: (_, r) => {
          const ch = r.chapter_id ? chapterById.get(r.chapter_id) : undefined
          const n = ch ? ch.sort_order + 1 : (r.chapter_number ?? '—')
          return (
            <Typography.Text>
              第{n}章 · {r.chapterTitle}
            </Typography.Text>
          )
        },
      },
      {
        title: '类型',
        width: 100,
        dataIndex: 'memory_type',
        render: (t: string) => (
          <Tag color="purple">{MEMORY_TYPE_LABELS[t] ?? t}</Tag>
        ),
      },
      {
        title: '标题',
        width: 200,
        ellipsis: true,
        dataIndex: 'title',
        render: (t: string | undefined) => t || '—',
      },
      {
        title: '标签',
        width: 180,
        render: (_, r) => (
          <Space size={[0, 4]} wrap>
            {(r.tags || []).length === 0 ? (
              <Typography.Text type="secondary">—</Typography.Text>
            ) : (
              (r.tags || []).map((tag) => (
                <Tag key={tag}>{tag}</Tag>
              ))
            )}
          </Space>
        ),
      },
      {
        title: '内容',
        ellipsis: true,
        dataIndex: 'content',
        render: (c: string) => (
          <Typography.Text style={{ maxWidth: 420 }} ellipsis={{ tooltip: c }}>
            {c}
          </Typography.Text>
        ),
      },
      {
        title: '时间',
        width: 170,
        dataIndex: 'created_at',
        render: (v: string | undefined) =>
          v ? new Date(v).toLocaleString() : '—',
      },
      {
        title: '操作',
        width: 120,
        fixed: 'right',
        render: (_, r) =>
          r.chapter_id ? (
            <Button
              type="link"
              size="small"
              onClick={() =>
                navigate(`/novels?projectId=${projectId}&chapterId=${r.chapter_id}`)
              }
            >
              小说管理
            </Button>
          ) : null,
      },
    ],
    [chapterById, navigate, projectId],
  )

  return (
    <div style={{ height: '100%', minHeight: 0, display: 'flex', flexDirection: 'column', overflow: 'hidden' }}>
      <Space wrap style={{ justifyContent: 'space-between', width: '100%', marginBottom: 12 }}>
        <Typography.Title level={4} style={{ margin: 0 }}>
          复盘列表
        </Typography.Title>
        <Space wrap>
          <Select
            style={{ minWidth: 260 }}
            placeholder="选择小说"
            loading={projectsLoading}
            options={projects.map((p) => ({ value: p.id, label: p.title }))}
            value={projectId}
            onChange={(v) => {
              setProjectId(v)
              setChapterFilter('all')
            }}
          />
        </Space>
      </Space>

      <Typography.Paragraph type="secondary" style={{ marginBottom: 12 }}>
        展示当前项目中绑定章节的记忆条目（与「小说管理」右侧「复盘记录」口径一致：含章节复盘提交与章内记忆提取）。
      </Typography.Paragraph>

      <Card
        style={{ flex: 1, minHeight: 0, display: 'flex', flexDirection: 'column', overflow: 'hidden' }}
        bodyStyle={{ flex: 1, minHeight: 0, padding: 16, overflow: 'hidden', display: 'flex', flexDirection: 'column' }}
      >
        <Space wrap style={{ marginBottom: 12 }}>
          <Select
            style={{ minWidth: 200 }}
            value={chapterFilter}
            onChange={(v) => setChapterFilter(v)}
            loading={chaptersLoading}
            options={[
              { value: 'all', label: '全部章节' },
              ...[...chapters]
                .sort((a, b) => a.sort_order - b.sort_order)
                .map((c) => ({
                  value: c.id,
                  label: `第${c.sort_order + 1}章 · ${c.title || '未命名'}`,
                })),
            ]}
          />
          <Select
            style={{ minWidth: 140 }}
            value={typeFilter}
            onChange={(v) => setTypeFilter(v)}
            options={[
              { value: 'all', label: '全部类型' },
              ...memoryTypeOptions.map((t) => ({
                value: t,
                label: MEMORY_TYPE_LABELS[t] ?? t,
              })),
            ]}
          />
          <Input
            allowClear
            placeholder="搜索标题、正文、标签"
            style={{ minWidth: 220, maxWidth: 320 }}
            value={keyword}
            onChange={(e) => setKeyword(e.target.value)}
          />
        </Space>

        {!projectId ? (
          <Empty description="请先选择小说" />
        ) : (
          <Table<Row>
            rowKey="id"
            size="small"
            loading={memoriesLoading || chaptersLoading}
            columns={columns}
            dataSource={filteredRows}
            pagination={{ pageSize: 25, showSizeChanger: true, pageSizeOptions: [25, 50, 100] }}
            scroll={{ x: 1100, y: 'calc(100vh - 320px)' }}
            locale={{ emptyText: <Empty image={Empty.PRESENTED_IMAGE_SIMPLE} description="暂无绑定章节的记忆" /> }}
          />
        )}
      </Card>
    </div>
  )
}

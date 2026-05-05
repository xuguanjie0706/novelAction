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

/** 去掉标题里自带的「第N章：」前缀，避免与 sort_order 推导的章节号重复叠显示 */
function stripLeadingChapterTitlePrefix(title: string): string {
  const stripped = title.replace(/^第\s*\d+\s*章\s*[：:]\s*/u, '').trim()
  return stripped.length > 0 ? stripped : title
}

/**
 * 与后端 `display_chapter_number` 一致：标题以「第N章」开头则取 N，否则为列表顺位 sort_order+1。
 * 复盘落库的 `chapter_number` 按此规则，列表若只用 sort_order+1 会与标题/库内章号错位。
 */
function displayChapterNumber(title: string | undefined, sortOrder: number | undefined): number {
  const raw = (title || '').trim()
  const m = raw.match(/^\s*第\s*0*(\d+)\s*章/u)
  if (m) return Math.max(1, parseInt(m[1], 10))
  const so = sortOrder == null || Number.isNaN(Number(sortOrder)) ? 0 : Number(sortOrder)
  return Math.max(1, so + 1)
}

function isChapterBodyEmpty(ch: ReviewChapter): boolean {
  const wc = ch.word_count ?? 0
  if (wc > 0) return false
  const plain = (ch.content || '').replace(/<[^>]*>/g, '').replace(/\u00a0/g, ' ').trim()
  return plain.length === 0
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

  const [chapterFilter, setChapterFilter] = useState<string | 'all' | '__bootstrap__'>('all')
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

  /**
   * 含：① 已绑定章节的记忆（复盘提交、章内提取）；② 未绑定但带 chapter_number 的条目（如开书时写入的种子 chapter_number=0）。
   * 后者在旧逻辑里被整表过滤掉，容易表现为「第一章/开书信息没了」。
   */
  const rows: Row[] = useMemo(() => {
    const included = memories.filter((item) => {
      if (item.chapter_id) return true
      return item.chapter_number !== null && item.chapter_number !== undefined
    })
    const sortedChapters = [...chapters].sort((a, b) => a.sort_order - b.sort_order)
    const out: Row[] = included.map((item) => {
      const ch = item.chapter_id ? chapterById.get(item.chapter_id) : undefined
      let chapterSort: number
      let chapterTitle: string
      if (ch) {
        chapterSort = ch.sort_order
        const raw = ch.title || '（章节已删或未知）'
        chapterTitle = stripLeadingChapterTitlePrefix(raw)
      } else if (item.chapter_number === 0) {
        chapterSort = -1
        chapterTitle = '全书基线（未绑定章节）'
      } else if (item.chapter_number != null && item.chapter_number > 0) {
        const matched = sortedChapters.find(
          (c) => displayChapterNumber(c.title, c.sort_order) === item.chapter_number,
        )
        chapterSort = matched ? matched.sort_order : item.chapter_number - 1
        chapterTitle = matched
          ? stripLeadingChapterTitlePrefix(matched.title || '未命名')
          : `第${item.chapter_number}章（未关联写作章节）`
      } else {
        chapterSort = 9999
        chapterTitle = '（未绑定章节）'
      }
      return {
        ...item,
        chapterSort,
        chapterTitle,
      }
    })
    // 倒序：最新写入的在上；同时间再按章节顺位倒序，保证顺序稳定
    out.sort((a, b) => {
      const ta = a.created_at ? new Date(a.created_at).getTime() : 0
      const tb = b.created_at ? new Date(b.created_at).getTime() : 0
      if (tb !== ta) return tb - ta
      if (a.chapterSort !== b.chapterSort) return b.chapterSort - a.chapterSort
      return String(b.id).localeCompare(String(a.id))
    })
    return out
  }, [memories, chapterById, chapters])

  const filteredRows = useMemo(() => {
    let list = rows
    if (chapterFilter === '__bootstrap__') {
      list = list.filter((r) => !r.chapter_id && r.chapter_number === 0)
    } else if (chapterFilter !== 'all') {
      const sel = chapters.find((c) => c.id === chapterFilter)
      list = list.filter((r) => {
        if (r.chapter_id === chapterFilter) return true
        if (!r.chapter_id && sel != null && r.chapter_number === displayChapterNumber(sel.title, sel.sort_order)) {
          return true
        }
        return false
      })
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
  }, [rows, chapterFilter, typeFilter, keyword, chapters])

  const memoryTypeOptions = useMemo(() => {
    const s = new Set<string>()
    for (const r of rows) s.add(r.memory_type)
    return [...s].sort()
  }, [rows])

  const columns: ColumnsType<Row> = useMemo(
    () => [
      {
        title: '章节',
        width: 200,
        render: (_, r) => {
          const ch = r.chapter_id ? chapterById.get(r.chapter_id) : undefined
          if (!r.chapter_id && r.chapter_number === 0) {
            return <Typography.Text>开书记忆 · {r.chapterTitle}</Typography.Text>
          }
          const n = ch ? displayChapterNumber(ch.title, ch.sort_order) : (r.chapter_number ?? '—')
          const emptyBody = ch ? isChapterBodyEmpty(ch) : false
          return (
            <Typography.Text>
              第{n}章 · {r.chapterTitle}
              {emptyBody ? (
                <Typography.Text type="secondary" style={{ marginLeft: 4 }}>
                  （正文未录入）
                </Typography.Text>
              ) : null}
            </Typography.Text>
          )
        },
      },
      {
        title: '类型',
        width: 88,
        dataIndex: 'memory_type',
        render: (t: string) => (
          <Tag color="purple">{MEMORY_TYPE_LABELS[t] ?? t}</Tag>
        ),
      },
      {
        title: '标题',
        width: 160,
        ellipsis: true,
        dataIndex: 'title',
        render: (t: string | undefined) => t || '—',
      },
      {
        title: '标签',
        width: 140,
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
        minWidth: 640,
        render: (c: string) => (
          <Typography.Text style={{ maxWidth: '100%', display: 'block' }} ellipsis={{ tooltip: c }}>
            {c}
          </Typography.Text>
        ),
      },
      {
        title: '时间',
        width: 158,
        dataIndex: 'created_at',
        render: (v: string | undefined) =>
          v ? new Date(v).toLocaleString() : '—',
      },
      {
        title: '操作',
        width: 100,
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
        含已绑定写作章节的记忆（复盘提交、章内提取），以及开书时生成的记忆种子（未绑定章节，在列表中显示为「开书记忆」）。
        章号与后端一致：优先取章节标题里的「第N章」，否则取正文列表顺位；若标题与顺位不一致，请勿混用二者理解进度。
        标注「正文未录入」表示该章节尚无正文却已有记忆，多为自动生成或误绑，可在小说管理中核对。
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
              { value: '__bootstrap__', label: '开书记忆种子' },
              ...[...chapters]
                .sort((a, b) => a.sort_order - b.sort_order)
                .map((c) => ({
                  value: c.id,
                  label: `第${displayChapterNumber(c.title, c.sort_order)}章 · ${stripLeadingChapterTitlePrefix(c.title || '未命名')}`,
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
            scroll={{ x: 1560, y: 'calc(100vh - 320px)' }}
            locale={{ emptyText: <Empty image={Empty.PRESENTED_IMAGE_SIMPLE} description="暂无记忆条目" /> }}
          />
        )}
      </Card>
    </div>
  )
}

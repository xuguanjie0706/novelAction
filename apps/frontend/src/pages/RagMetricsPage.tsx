/**
 * @file RagMetricsPage — RAG 命中率质量监控
 *
 * 职责：从 /api/v1/projects/{pid}/ai/memory/rag-metrics 拉取统计指标并可视化。
 * 数据全部来自 rag_retrieval_logs 表，无需额外存储。
 *
 * 布局：
 *   顶部 — 项目选择 + 时间窗口选择 + 刷新
 *   KPI 卡片行 — 总查询 / 语义命中率 / 兜底率 / 零命中率 / 平均耗时
 *   来源细分表格 — 按 source（draft_context / suggest / …）展示各项指标
 *   每日趋势 — 简单文字趋势（antd 内置图表能力有限，此处用 sparkline 表格行代替）
 */
import { useCallback, useEffect, useState } from 'react'
import {
  Alert,
  Card,
  Col,
  Empty,
  Row,
  Select,
  Space,
  Spin,
  Statistic,
  Table,
  Tag,
  Typography,
} from 'antd'
import type { ColumnsType } from 'antd/es/table'
import { BarChartOutlined, ReloadOutlined, SearchOutlined } from '@ant-design/icons'
import { http } from '../api/http'
import type { ReviewProject } from '../types/review'

const { Title, Text } = Typography

// ── 类型 ────────────────────────────────────────────────────────────────────

interface RagMetrics {
  total_queries: number
  semantic_hit_rate: number | null
  fallback_rate: number | null
  zero_hit_rate: number | null
  avg_hit_count: number | null
  avg_duration_ms: number | null
  by_source: Record<string, {
    total: number
    semantic_hit_rate: number | null
    zero_hit_rate: number | null
    avg_duration_ms: number | null
  }>
  daily_trend: Array<{
    date: string
    queries: number
    semantic_hit_rate: number | null
  }>
}

// ── 辅助 ────────────────────────────────────────────────────────────────────

const SOURCE_LABELS: Record<string, string> = {
  draft_context:    '写章上下文',
  pre_write_warning: '写前预警',
  suggest:          'AI 建议',
  rag_query:        '手动查询',
}

function pct(v: number | null) {
  if (v == null) return '—'
  return `${(v * 100).toFixed(1)}%`
}

function hitRateColor(v: number | null) {
  if (v == null) return undefined
  if (v >= 0.8) return 'green'
  if (v >= 0.5) return 'orange'
  return 'red'
}

// ── 每日趋势简表 ─────────────────────────────────────────────────────────────

interface TrendRowType {
  key: string
  date: string
  queries: number
  semantic_hit_rate: number | null
}

const trendColumns: ColumnsType<TrendRowType> = [
  {
    title: '日期',
    dataIndex: 'date',
    key: 'date',
    width: 110,
  },
  {
    title: '查询次数',
    dataIndex: 'queries',
    key: 'queries',
    width: 90,
    align: 'right',
  },
  {
    title: '语义命中率',
    dataIndex: 'semantic_hit_rate',
    key: 'semantic_hit_rate',
    align: 'right',
    render: (v: number | null) => (
      <Tag color={hitRateColor(v)}>{pct(v)}</Tag>
    ),
  },
]

// ── 来源细分表 ───────────────────────────────────────────────────────────────

interface SourceRowType {
  key: string
  source: string
  total: number
  semantic_hit_rate: number | null
  zero_hit_rate: number | null
  avg_duration_ms: number | null
}

const sourceColumns: ColumnsType<SourceRowType> = [
  {
    title: '来源',
    dataIndex: 'source',
    key: 'source',
    render: (v: string) => SOURCE_LABELS[v] ?? v,
  },
  {
    title: '查询次数',
    dataIndex: 'total',
    key: 'total',
    align: 'right',
    width: 90,
  },
  {
    title: '语义命中率',
    dataIndex: 'semantic_hit_rate',
    key: 'semantic_hit_rate',
    align: 'right',
    render: (v: number | null) => <Tag color={hitRateColor(v)}>{pct(v)}</Tag>,
  },
  {
    title: '零命中率',
    dataIndex: 'zero_hit_rate',
    key: 'zero_hit_rate',
    align: 'right',
    render: (v: number | null) => {
      if (v == null) return '—'
      const color = v > 0.3 ? 'red' : v > 0.1 ? 'orange' : 'green'
      return <Tag color={color}>{pct(v)}</Tag>
    },
  },
  {
    title: '平均耗时',
    dataIndex: 'avg_duration_ms',
    key: 'avg_duration_ms',
    align: 'right',
    render: (v: number | null) => v == null ? '—' : `${v} ms`,
  },
]

// ── 主页面 ───────────────────────────────────────────────────────────────────

const DAYS_OPTIONS = [
  { value: 7,  label: '最近 7 天' },
  { value: 14, label: '最近 14 天' },
  { value: 30, label: '最近 30 天' },
  { value: 90, label: '最近 90 天' },
]

/**
 * RAG 命中率质量监控页（管理后台）。
 *
 * 选择项目后展示该项目的 RAG 检索质量聚合指标；
 * 所有数据来自 rag_retrieval_logs 表，无需额外存储。
 */
export default function RagMetricsPage() {
  const [projects, setProjects]   = useState<ReviewProject[]>([])
  const [projectId, setProjectId] = useState<string>()
  const [days, setDays]           = useState<number>(7)
  const [metrics, setMetrics]     = useState<RagMetrics | null>(null)
  const [loading, setLoading]     = useState(false)
  const [error, setError]         = useState<string | null>(null)
  const [projectsError, setProjectsError] = useState<string | null>(null)

  // 加载项目列表（与其它管理页一致：GET /api/v1/projects/）
  useEffect(() => {
    http.get<ReviewProject[]>('/api/v1/projects/')
      .then(r => {
        const list = Array.isArray(r.data) ? r.data : []
        setProjects(list)
        setProjectsError(null)
        if (list.length > 0 && !projectId) setProjectId(list[0].id)
      })
      .catch((e: unknown) => {
        setProjects([])
        const msg = (e as { response?: { data?: { detail?: string } }; message?: string })
        setProjectsError(
          msg?.response?.data?.detail ?? msg?.message ?? '加载项目列表失败，请确认已登录管理后台',
        )
      })
  }, [])

  const fetchMetrics = useCallback(async () => {
    if (!projectId) return
    setLoading(true)
    setError(null)
    try {
      const r = await http.get<RagMetrics>(
        `/api/v1/projects/${projectId}/ai/memory/rag-metrics?days=${days}`,
      )
      setMetrics(r.data)
    } catch (e: unknown) {
      setError((e as { message?: string })?.message ?? '加载失败')
      setMetrics(null)
    } finally {
      setLoading(false)
    }
  }, [projectId, days])

  useEffect(() => { void fetchMetrics() }, [fetchMetrics])

  // 来源细分表数据
  const sourceRows: SourceRowType[] = metrics
    ? Object.entries(metrics.by_source).map(([src, s]) => ({
        key: src,
        source: src,
        total: s.total,
        semantic_hit_rate: s.semantic_hit_rate,
        zero_hit_rate: s.zero_hit_rate,
        avg_duration_ms: s.avg_duration_ms,
      }))
    : []

  // 每日趋势表数据
  const trendRows: TrendRowType[] = (metrics?.daily_trend ?? [])
    .slice()
    .reverse()
    .map(d => ({ key: d.date, date: d.date, queries: d.queries, semantic_hit_rate: d.semantic_hit_rate }))

  return (
    <div style={{ padding: 24 }}>
      <div style={{ display: 'flex', alignItems: 'center', gap: 8, marginBottom: 20 }}>
        <BarChartOutlined style={{ fontSize: 20, color: '#1677ff' }} />
        <Title level={4} style={{ margin: 0 }}>RAG 命中率质量监控</Title>
      </div>

      {/* 筛选栏 */}
      <Card size="small" style={{ marginBottom: 16 }}>
        <Space wrap>
          <Text type="secondary">项目：</Text>
          <Select
            style={{ width: 240 }}
            placeholder="选择项目"
            value={projectId}
            onChange={setProjectId}
            options={projects.map(p => ({ value: p.id, label: p.title }))}
            showSearch
            filterOption={(input, opt) =>
              (opt?.label as string)?.toLowerCase().includes(input.toLowerCase())
            }
          />
          <Text type="secondary">时间窗口：</Text>
          <Select
            style={{ width: 130 }}
            value={days}
            onChange={setDays}
            options={DAYS_OPTIONS}
          />
          <ReloadOutlined
            style={{ cursor: 'pointer', color: '#1677ff' }}
            spin={loading}
            onClick={() => void fetchMetrics()}
          />
        </Space>
      </Card>

      {projectsError && (
        <Alert type="error" message={projectsError} style={{ marginBottom: 16 }} />
      )}
      {error && (
        <Alert type="error" message={error} style={{ marginBottom: 16 }} />
      )}

      <Spin spinning={loading}>
        {!projectId ? (
          <Empty description={projects.length === 0 ? '暂无项目，请先在创作端创建小说' : '请选择项目'} />
        ) : !metrics || metrics.total_queries === 0 ? (
          <Empty description="该项目在所选时间窗口内暂无 RAG 检索记录" />
        ) : (
          <>
            {/* KPI 卡片行 */}
            <Row gutter={[16, 16]} style={{ marginBottom: 16 }}>
              <Col xs={12} sm={8} md={4}>
                <Card size="small">
                  <Statistic title="总查询次数" value={metrics.total_queries} />
                </Card>
              </Col>
              <Col xs={12} sm={8} md={4}>
                <Card size="small">
                  <Statistic
                    title="语义命中率"
                    value={pct(metrics.semantic_hit_rate)}
                    valueStyle={{ color: hitRateColor(metrics.semantic_hit_rate) === 'green' ? '#3f8600' : hitRateColor(metrics.semantic_hit_rate) === 'red' ? '#cf1322' : '#d46b08' }}
                  />
                </Card>
              </Col>
              <Col xs={12} sm={8} md={4}>
                <Card size="small">
                  <Statistic
                    title="兜底率"
                    value={pct(metrics.fallback_rate)}
                    valueStyle={{ color: (metrics.fallback_rate ?? 0) > 0.3 ? '#cf1322' : undefined }}
                  />
                </Card>
              </Col>
              <Col xs={12} sm={8} md={4}>
                <Card size="small">
                  <Statistic
                    title="零命中率"
                    value={pct(metrics.zero_hit_rate)}
                    valueStyle={{ color: (metrics.zero_hit_rate ?? 0) > 0.2 ? '#cf1322' : undefined }}
                  />
                </Card>
              </Col>
              <Col xs={12} sm={8} md={4}>
                <Card size="small">
                  <Statistic
                    title="平均命中条数"
                    value={metrics.avg_hit_count ?? '—'}
                    precision={1}
                  />
                </Card>
              </Col>
              <Col xs={12} sm={8} md={4}>
                <Card size="small">
                  <Statistic
                    title="平均耗时"
                    value={metrics.avg_duration_ms != null ? `${metrics.avg_duration_ms} ms` : '—'}
                  />
                </Card>
              </Col>
            </Row>

            {/* 来源细分表 */}
            <Card
              title={<><SearchOutlined style={{ marginRight: 6 }} />按来源细分</>}
              size="small"
              style={{ marginBottom: 16 }}
            >
              <Table<SourceRowType>
                dataSource={sourceRows}
                columns={sourceColumns}
                pagination={false}
                size="small"
              />
            </Card>

            {/* 每日趋势 */}
            <Card title="每日趋势" size="small">
              <Table<TrendRowType>
                dataSource={trendRows}
                columns={trendColumns}
                pagination={false}
                size="small"
                locale={{ emptyText: '无趋势数据' }}
              />
            </Card>
          </>
        )}
      </Spin>
    </div>
  )
}

/**
 * 管理后台控制台页面（Dashboard）。
 *
 * 数据来源：GET /api/v1/admin/dashboard/stats
 * 刷新策略：手动刷新 + 可选自动刷新（30s 轮询）。
 *
 * 布局（从上到下）：
 * 1. 顶栏：标题 / 刷新时间 / 刷新按钮 / 自动刷新开关
 * 2. 第一行 KPI 卡片：小说总数 / 总章节 / 总字数 / 注册用户数
 * 3. 第二行 KPI 卡片：今日 Token / 总 Token / 今日成功率 / 平均耗时 / 今日 Bootstrap
 * 4. 告警条（上下文截断 / 质检欠债 / 记忆冲突提醒）
 * 5. 第三行：近 7 天 Token 趋势图 + 任务分布 + RAG 命中率
 * 6. 第四行：积分经济 + 小说状态分布
 * 7. 第五行：最近活动流（Bootstrap / 错误 / 冲突）
 */

import { useCallback, useEffect, useRef, useState } from 'react'
import {
  Alert,
  App,
  Badge,
  Button,
  Col,
  Divider,
  Row,
  Space,
  Switch,
  Tag,
  Tooltip,
  Typography,
} from 'antd'
import {
  BookOutlined,
  BulbOutlined,
  CloudServerOutlined,
  CreditCardOutlined,
  DashboardOutlined,
  FileTextOutlined,
  ReloadOutlined,
  RocketOutlined,
  ThunderboltOutlined,
  UserOutlined,
  WarningOutlined,
} from '@ant-design/icons'
import { http } from '../../api/http'
import type { DashboardStats } from '../../types/dashboard'
import StatCard from './StatCard'
import TokenTrendChart from './TokenTrendChart'
import TopTasksChart from './TopTasksChart'
import ActivityPanel from './ActivityPanel'

const { Title, Text } = Typography

const NOVEL_STATUS_LABEL: Record<string, string> = {
  drafting: '设定阶段',
  writing: '写作中',
  completed: '已完结',
  unknown: '未知',
}
const NOVEL_STATUS_COLOR: Record<string, string> = {
  drafting: '#6366f1',
  writing: '#10b981',
  completed: '#f59e0b',
  unknown: '#d1d5db',
}
const DEBT_SEVERITY_COLOR: Record<string, string> = {
  high: '#ff4d4f',
  medium: '#faad14',
  low: '#52c41a',
}

function formatK(n: number): string {
  if (n >= 100_000_000) return `${(n / 100_000_000).toFixed(1)}亿`
  if (n >= 10_000) return `${(n / 10_000).toFixed(1)}万`
  return n.toLocaleString()
}

function formatTokens(n: number): string {
  if (n >= 1_000_000) return `${(n / 1_000_000).toFixed(1)}M`
  if (n >= 1_000) return `${(n / 1_000).toFixed(0)}K`
  return String(n)
}

const AUTO_REFRESH_INTERVAL = 30_000 // 30 秒

export default function DashboardPage() {
  const { message } = App.useApp()
  const [stats, setStats] = useState<DashboardStats | null>(null)
  const [loading, setLoading] = useState(false)
  const [autoRefresh, setAutoRefresh] = useState(false)
  const timerRef = useRef<ReturnType<typeof setInterval> | null>(null)

  const load = useCallback(async () => {
    setLoading(true)
    try {
      const { data } = await http.get<DashboardStats>('/api/v1/admin/dashboard/stats')
      setStats(data)
    } catch {
      message.error('加载控制台数据失败')
    } finally {
      setLoading(false)
    }
  }, [message])

  useEffect(() => {
    void load()
  }, [load])

  // 自动刷新
  useEffect(() => {
    if (autoRefresh) {
      timerRef.current = setInterval(() => void load(), AUTO_REFRESH_INTERVAL)
    } else {
      if (timerRef.current) clearInterval(timerRef.current)
    }
    return () => {
      if (timerRef.current) clearInterval(timerRef.current)
    }
  }, [autoRefresh, load])

  const s = stats

  // ── 告警条逻辑 ──────────────────────────────────────────────────────────
  const alerts: { type: 'error' | 'warning' | 'info'; msg: string }[] = []
  if (s) {
    if (s.llm.limit_exceeded_today > 0) {
      alerts.push({ type: 'error', msg: `今日 ${s.llm.limit_exceeded_today} 次 AI 调用上下文超限，建议升级模型或压缩输入。` })
    }
    if (s.llm.truncated_today > 0) {
      alerts.push({ type: 'warning', msg: `今日 ${s.llm.truncated_today} 次 Prompt 被业务层裁剪，建议换更大上下文模型。` })
    }
    if (s.quality.quality_debt_pending > 10) {
      alerts.push({ type: 'warning', msg: `存在 ${s.quality.quality_debt_pending} 条未处理质检欠债，建议尽快修复高优先级问题。` })
    }
    if (s.rag.rag_semantic_rate < 60 && s.rag.rag_total > 20) {
      alerts.push({ type: 'warning', msg: `RAG 语义命中率仅 ${s.rag.rag_semantic_rate}%，embedding 服务可能异常，建议检查向量索引。` })
    }
  }

  return (
    <div style={{ height: '100%', overflow: 'auto' }}>
      {/* ── 顶栏 ── */}
      <div
        style={{
          display: 'flex',
          alignItems: 'center',
          justifyContent: 'space-between',
          marginBottom: 20,
        }}
      >
        <div style={{ display: 'flex', alignItems: 'center', gap: 10 }}>
          <DashboardOutlined style={{ fontSize: 22, color: '#6366f1' }} />
          <Title level={4} style={{ margin: 0 }}>
            系统控制台
          </Title>
          {s && (
            <Text type="secondary" style={{ fontSize: 12, marginLeft: 8 }}>
              数据截止 {new Date(s.generated_at).toLocaleTimeString()}
            </Text>
          )}
        </div>
        <Space>
          <Tooltip title="每 30 秒自动刷新">
            <Space size={6}>
              <Switch
                size="small"
                checked={autoRefresh}
                onChange={setAutoRefresh}
              />
              <Text style={{ fontSize: 12 }}>自动刷新</Text>
            </Space>
          </Tooltip>
          <Button
            icon={<ReloadOutlined spin={loading} />}
            onClick={() => void load()}
            loading={loading}
          >
            刷新
          </Button>
        </Space>
      </div>

      {/* ── 告警条 ── */}
      {alerts.map((a, i) => (
        <Alert
          key={i}
          type={a.type}
          message={a.msg}
          showIcon
          style={{ marginBottom: 10, borderRadius: 8 }}
          closable
        />
      ))}

      {/* ── 第一行：内容 & 用户 KPI ── */}
      <Row gutter={[14, 14]} style={{ marginBottom: 14 }}>
        <Col xs={12} sm={6}>
          <StatCard
            loading={loading}
            title="小说总数"
            value={s?.content.total_projects ?? 0}
            suffix="部"
            icon={<BookOutlined />}
            color="#6366f1"
            sub={
              s
                ? Object.entries(s.content.projects_by_status)
                    .map(([st, cnt]) => `${NOVEL_STATUS_LABEL[st] ?? st} ${cnt}`)
                    .join(' / ')
                : undefined
            }
          />
        </Col>
        <Col xs={12} sm={6}>
          <StatCard
            loading={loading}
            title="总章节数"
            value={s?.content.total_chapters ?? 0}
            suffix="章"
            icon={<FileTextOutlined />}
            color="#10b981"
            sub={`共 ${formatK(s?.content.total_words ?? 0)} 字`}
          />
        </Col>
        <Col xs={12} sm={6}>
          <StatCard
            loading={loading}
            title="注册用户"
            value={s?.users.total_users ?? 0}
            suffix="人"
            icon={<UserOutlined />}
            color="#f59e0b"
            sub={`活跃 ${s?.users.active_users ?? 0} 人`}
          />
        </Col>
        <Col xs={12} sm={6}>
          <StatCard
            loading={loading}
            title="Bootstrap 生成"
            value={s?.bootstrap.bootstrap_today ?? 0}
            suffix="次（今日）"
            icon={<ThunderboltOutlined />}
            color="#8b5cf6"
            sub={`累计 ${s?.bootstrap.bootstrap_total ?? 0} 次`}
          />
        </Col>
      </Row>

      {/* ── 第二行：AI 调用 KPI ── */}
      <Row gutter={[14, 14]} style={{ marginBottom: 14 }}>
        <Col xs={12} sm={6} lg={4}>
          <StatCard
            loading={loading}
            title="今日 Token"
            value={formatTokens(s?.llm.token_today ?? 0)}
            icon={<BulbOutlined />}
            color="#6366f1"
            sub={`↑ ${formatTokens(s?.llm.prompt_tokens_today ?? 0)} / ↓ ${formatTokens(s?.llm.completion_tokens_today ?? 0)}`}
          />
        </Col>
        <Col xs={12} sm={6} lg={4}>
          <StatCard
            loading={loading}
            title="累计 Token"
            value={formatTokens(s?.llm.token_total ?? 0)}
            icon={<CloudServerOutlined />}
            color="#10b981"
            sub={`累计调用 ${(s?.llm.llm_calls_total ?? 0).toLocaleString()} 次`}
          />
        </Col>
        <Col xs={12} sm={6} lg={4}>
          <StatCard
            loading={loading}
            title="今日成功率"
            value={s?.llm.success_rate_today ?? 0}
            suffix="%"
            icon={<RocketOutlined />}
            color={
              (s?.llm.success_rate_today ?? 100) >= 95
                ? '#10b981'
                : (s?.llm.success_rate_today ?? 100) >= 80
                  ? '#faad14'
                  : '#ff4d4f'
            }
            sub={`${s?.llm.llm_ok_today ?? 0} 成功 / ${s?.llm.llm_error_today ?? 0} 失败`}
          />
        </Col>
        <Col xs={12} sm={6} lg={4}>
          <StatCard
            loading={loading}
            title="平均响应耗时"
            value={s?.llm.avg_duration_ms_today ?? 0}
            suffix="ms（今日）"
            icon={<DashboardOutlined />}
            color="#f59e0b"
          />
        </Col>
        <Col xs={12} sm={6} lg={4}>
          <StatCard
            loading={loading}
            title="质检欠债"
            value={s?.quality.quality_debt_pending ?? 0}
            suffix="条待处理"
            icon={<WarningOutlined />}
            color={(s?.quality.quality_debt_pending ?? 0) > 0 ? '#ff4d4f' : '#10b981'}
            sub={
              s
                ? Object.entries(s.quality.quality_debt_by_severity)
                    .map(([sv, cnt]) => `${sv} ${cnt}`)
                    .join(' / ')
                : undefined
            }
          />
        </Col>
        <Col xs={12} sm={6} lg={4}>
          <StatCard
            loading={loading}
            title="积分今日消耗"
            value={(s?.credits.credits_consumed_today ?? 0).toLocaleString()}
            suffix="积分"
            icon={<CreditCardOutlined />}
            color="#8b5cf6"
            sub={`今日充入 ${(s?.credits.credits_topup_today ?? 0).toLocaleString()} 积分`}
          />
        </Col>
      </Row>

      {/* ── 第三行：Token 趋势图 ── */}
      <div style={{ marginBottom: 14 }}>
        <TokenTrendChart data={s?.token_trend ?? []} loading={loading} />
      </div>

      {/* ── 第四行：任务分布 + RAG ── */}
      <div style={{ marginBottom: 14 }}>
        <TopTasksChart
          tasks={s?.llm.top_tasks_by_token ?? []}
          rag={
            s?.rag ?? {
              rag_total: 0,
              rag_semantic_ok: 0,
              rag_fallback: 0,
              rag_semantic_rate: 0,
              rag_avg_duration_ms: 0,
              rag_today: 0,
              rag_by_status: {},
            }
          }
          loading={loading}
        />
      </div>

      {/* ── 小说状态 & 积分分布 ── */}
      {s && (
        <Row gutter={[14, 14]} style={{ marginBottom: 14 }}>
          <Col xs={24} sm={12}>
            <div
              style={{
                background: '#fff',
                borderRadius: 10,
                border: '1px solid #f0f0f0',
                padding: '14px 18px',
              }}
            >
              <Text strong style={{ fontSize: 13 }}>
                小说状态分布
              </Text>
              <div style={{ display: 'flex', gap: 12, marginTop: 12, flexWrap: 'wrap' }}>
                {Object.entries(s.content.projects_by_status).map(([st, cnt]) => (
                  <div
                    key={st}
                    style={{
                      flex: 1,
                      minWidth: 80,
                      background: (NOVEL_STATUS_COLOR[st] ?? '#6366f1') + '11',
                      border: `1px solid ${NOVEL_STATUS_COLOR[st] ?? '#6366f1'}44`,
                      borderRadius: 8,
                      padding: '10px 12px',
                      textAlign: 'center',
                    }}
                  >
                    <div
                      style={{
                        fontWeight: 700,
                        fontSize: 22,
                        color: NOVEL_STATUS_COLOR[st] ?? '#6366f1',
                      }}
                    >
                      {cnt}
                    </div>
                    <Text type="secondary" style={{ fontSize: 11 }}>
                      {NOVEL_STATUS_LABEL[st] ?? st}
                    </Text>
                  </div>
                ))}
              </div>
            </div>
          </Col>
          <Col xs={24} sm={12}>
            <div
              style={{
                background: '#fff',
                borderRadius: 10,
                border: '1px solid #f0f0f0',
                padding: '14px 18px',
              }}
            >
              <Text strong style={{ fontSize: 13 }}>
                积分经济概览
              </Text>
              <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 10, marginTop: 12 }}>
                {[
                  { label: '累计充入', value: s.credits.credits_topup_total, color: '#10b981' },
                  { label: '累计消耗', value: s.credits.credits_consumed_total, color: '#ff4d4f' },
                  { label: '今日充入', value: s.credits.credits_topup_today, color: '#6366f1' },
                  { label: '今日消耗', value: s.credits.credits_consumed_today, color: '#f59e0b' },
                ].map(({ label, value, color }) => (
                  <div
                    key={label}
                    style={{
                      background: color + '11',
                      border: `1px solid ${color}33`,
                      borderRadius: 8,
                      padding: '8px 12px',
                    }}
                  >
                    <Text type="secondary" style={{ fontSize: 11 }}>
                      {label}
                    </Text>
                    <div style={{ fontWeight: 700, fontSize: 16, color }}>
                      {value.toLocaleString()}
                    </div>
                  </div>
                ))}
              </div>
            </div>
          </Col>
        </Row>
      )}

      <Divider style={{ margin: '8px 0 14px' }} />

      {/* ── 活动流 ── */}
      <div style={{ marginBottom: 8 }}>
        <Text strong style={{ fontSize: 13, display: 'block', marginBottom: 10 }}>
          近期活动
        </Text>
        <ActivityPanel data={s?.activity ?? { recent_bootstraps: [], recent_llm_errors: [], recent_memory_conflicts: [] }} loading={loading} />
      </div>
    </div>
  )
}

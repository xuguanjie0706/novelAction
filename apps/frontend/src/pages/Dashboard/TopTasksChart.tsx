/**
 * 任务类型 Token 占比图（水平条形图 + RAG 语义命中率环形进度）。
 *
 * 两个小图共用一个 Card，展示「谁在消耗 Token」与「RAG 质量」两个维度。
 */
import { Card, Progress, Typography } from 'antd'
import type { TopTask, RagStats } from '../../types/dashboard'

const { Text } = Typography

// 操作名简化映射
const OP_ABBR: Record<string, string> = {
  'bootstrap.positioning': 'BS 立项',
  'bootstrap.project': 'BS 项目初始化',
  'bootstrap.settings': 'BS 设定卡',
  'bootstrap.power_systems': 'BS 境界体系',
  'bootstrap.factions': 'BS 势力',
  'bootstrap.storylines': 'BS 故事线',
  'bootstrap.characters': 'BS 人物库',
  'bootstrap.skills': 'BS 技能体系',
  'bootstrap.items': 'BS 道具体系',
  'bootstrap.volumes': 'BS 卷规划',
  'bootstrap.memory': 'BS 记忆库',
  'bootstrap.relations': 'BS 人物关系',
  'bootstrap.consistency_scan': 'BS 一致性扫描',
  quality_check: '章节质检',
  draft_assist_stream: '章节写作',
  expand_outline: '大纲展开',
  auto_extract_debrief: '自动复盘',
  extract_memory: '记忆提取',
  suggest_stream: 'AI 建议',
  memory_conflict_detect: '记忆冲突检测',
  chapter_coherence_check: '连贯性检测',
}

function abbr(op: string): string {
  return OP_ABBR[op] ?? (op.length > 16 ? op.slice(0, 16) + '…' : op)
}

function formatK(n: number): string {
  if (n >= 1_000_000) return `${(n / 1_000_000).toFixed(1)}M`
  if (n >= 1_000) return `${(n / 1_000).toFixed(0)}K`
  return String(n)
}

// 渐变颜色数组
const BAR_COLORS = [
  '#6366f1', '#8b5cf6', '#a78bfa', '#c4b5fd',
  '#10b981', '#34d399', '#6ee7b7', '#d1fae5',
  '#f59e0b', '#fbbf24',
]

interface Props {
  tasks: TopTask[]
  rag: RagStats
  loading?: boolean
}

export default function TopTasksChart({ tasks, rag, loading }: Props) {
  const maxTokens = tasks.length > 0 ? tasks[0].tokens : 1

  return (
    <div style={{ display: 'grid', gridTemplateColumns: '3fr 2fr', gap: 16 }}>
      {/* 任务类型 Token 分布 */}
      <Card
        loading={loading}
        title={<span style={{ fontWeight: 600, fontSize: 14 }}>Token 消耗 TOP 任务</span>}
        bodyStyle={{ padding: '12px 16px' }}
        style={{ borderRadius: 10 }}
        size="small"
      >
        {tasks.length === 0 ? (
          <Text type="secondary">暂无数据</Text>
        ) : (
          <div style={{ display: 'flex', flexDirection: 'column', gap: 8 }}>
            {tasks.map((t, i) => (
              <div key={t.task}>
                <div
                  style={{
                    display: 'flex',
                    justifyContent: 'space-between',
                    alignItems: 'center',
                    marginBottom: 2,
                  }}
                >
                  <Text style={{ fontSize: 12 }}>{abbr(t.task)}</Text>
                  <Text type="secondary" style={{ fontSize: 12 }}>
                    {formatK(t.tokens)}
                  </Text>
                </div>
                <div
                  style={{
                    height: 6,
                    borderRadius: 3,
                    background: '#f5f5f5',
                    overflow: 'hidden',
                  }}
                >
                  <div
                    style={{
                      height: '100%',
                      width: `${(t.tokens / maxTokens) * 100}%`,
                      background: BAR_COLORS[i % BAR_COLORS.length],
                      borderRadius: 3,
                      transition: 'width 0.4s ease',
                    }}
                  />
                </div>
              </div>
            ))}
          </div>
        )}
      </Card>

      {/* RAG 语义命中率 */}
      <Card
        loading={loading}
        title={<span style={{ fontWeight: 600, fontSize: 14 }}>RAG 语义命中率</span>}
        bodyStyle={{ padding: '16px', textAlign: 'center' }}
        style={{ borderRadius: 10 }}
        size="small"
      >
        <Progress
          type="dashboard"
          percent={rag.rag_semantic_rate}
          strokeColor={rag.rag_semantic_rate >= 80 ? '#10b981' : rag.rag_semantic_rate >= 60 ? '#faad14' : '#ff4d4f'}
          format={(p) => (
            <div>
              <div style={{ fontWeight: 700, fontSize: 18 }}>{p}%</div>
              <div style={{ fontSize: 11, color: '#999' }}>语义</div>
            </div>
          )}
          size={100}
        />
        <div style={{ display: 'flex', justifyContent: 'space-around', marginTop: 12 }}>
          <div style={{ textAlign: 'center' }}>
            <div style={{ fontWeight: 600, color: '#10b981' }}>{rag.rag_semantic_ok.toLocaleString()}</div>
            <Text type="secondary" style={{ fontSize: 11 }}>语义命中</Text>
          </div>
          <div style={{ textAlign: 'center' }}>
            <div style={{ fontWeight: 600, color: '#faad14' }}>{rag.rag_fallback.toLocaleString()}</div>
            <Text type="secondary" style={{ fontSize: 11 }}>降级兜底</Text>
          </div>
          <div style={{ textAlign: 'center' }}>
            <div style={{ fontWeight: 600, color: '#6366f1' }}>{rag.rag_avg_duration_ms}</div>
            <Text type="secondary" style={{ fontSize: 11 }}>均耗时(ms)</Text>
          </div>
        </div>
      </Card>
    </div>
  )
}

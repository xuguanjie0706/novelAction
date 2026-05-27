import { Col, Row, Select, Space, Typography } from 'antd'
import type { LlmOverview } from '../../types/llm'
import type { ReviewProject } from '../../types/review'

type PageHeaderProps = {
  loading: boolean
  projects: ReviewProject[]
  projectId: string | undefined
  onProjectChange: (id: string) => void
  llmOverview: LlmOverview | null
  selectedModelOption: string
  onModelChange: (value: string) => void
}

/** 项目与模型选择栏 */
export function PageHeader({
  loading,
  projects,
  projectId,
  onProjectChange,
  llmOverview,
  selectedModelOption,
  onModelChange,
}: PageHeaderProps) {
  return (
    <Row gutter={[24, 12]} align="middle" justify="space-between" style={{ width: '100%' }}>
      <Col flex="auto">
        <Typography.Title level={4} style={{ margin: 0 }}>
          作品质量与修订
        </Typography.Title>
        <Typography.Paragraph type="secondary" style={{ margin: '6px 0 0', maxWidth: 720 }}>
          先诊断再修订；改正文须预览差异后写入数据库，并自动保留修订前快照。定向修订中可勾选评测条目并补充关键词。
        </Typography.Paragraph>
      </Col>
      <Col>
        <Space wrap size="middle" align="center">
          <Space align="center">
            <Typography.Text type="secondary">项目</Typography.Text>
            <Select
              style={{ minWidth: 220 }}
              placeholder="选择项目"
              options={projects.map((p) => ({ value: p.id, label: p.title }))}
              value={projectId}
              loading={loading}
              onChange={onProjectChange}
            />
          </Space>
          <Space align="center">
            <Typography.Text type="secondary">模型</Typography.Text>
            <Select<string>
              style={{ width: 300 }}
              value={selectedModelOption}
              options={[
                {
                  label: `本地 · ${llmOverview?.local_model_name ?? 'default'}`,
                  value: 'local',
                },
                ...(llmOverview?.remote_providers ?? []).map((p) => ({
                  label: `远程 · ${p.name} (${p.model_name})${p.is_default ? ' [默认]' : ''}`,
                  value: `provider:${p.id}`,
                })),
              ]}
              onChange={onModelChange}
            />
          </Space>
        </Space>
      </Col>
    </Row>
  )
}

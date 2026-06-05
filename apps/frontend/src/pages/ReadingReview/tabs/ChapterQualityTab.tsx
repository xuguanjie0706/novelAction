import { Button, Card, Empty, List, Select, Space, Tag, Typography } from 'antd'
import { ChapterQualityDimensionsView } from '../../../components/ChapterQualityDimensionsView'
import type { QualityReport } from '../../../types/review'

type ChapterOption = { label: string; value: string }

type ChapterQualityTabProps = {
  chapterOptions: ChapterOption[]
  selectedChapterId: string | undefined
  onChapterChange: (id: string) => void
  qualityLoading: boolean
  onRunQualityCheck: () => void
  onViewChapter: () => void
  qualityReport: QualityReport | null
}

/** 单章评测 Tab */
export function ChapterQualityTab({
  chapterOptions,
  selectedChapterId,
  onChapterChange,
  qualityLoading,
  onRunQualityCheck,
  onViewChapter,
  qualityReport,
}: ChapterQualityTabProps) {
  return (
    <Space direction="vertical" size="middle" style={{ width: '100%' }}>
      <Space wrap>
        <Select
          style={{ minWidth: 420 }}
          placeholder="选择章节"
          options={chapterOptions}
          value={selectedChapterId}
          onChange={onChapterChange}
        />
        <Button type="primary" loading={qualityLoading} onClick={() => void onRunQualityCheck()}>
          开始评测
        </Button>
        <Button onClick={onViewChapter}>
          查看正文
        </Button>
      </Space>
      {!qualityReport ? (
        <Card>
          <Empty description="尚未评测，选择章节后点击开始评测" />
        </Card>
      ) : (
        <Space direction="vertical" size="middle" style={{ width: '100%' }}>
          <Card title={`总分：${qualityReport.overall_score ?? '-'} 分`}>
            <ChapterQualityDimensionsView dimensions={qualityReport.dimensions} />
            <Typography.Paragraph style={{ marginTop: 12, marginBottom: 0 }}>
              {qualityReport.summary || '暂无总结'}
            </Typography.Paragraph>

            {(qualityReport.highlight_quote || qualityReport.subscribe_intent_score != null) && (
              <Card
                size="small"
                style={{ marginTop: 12, background: '#f6ffed', borderColor: '#b7eb8f' }}
                title="读者沉浸亮点"
              >
                <Space direction="vertical" style={{ width: '100%' }}>
                  {qualityReport.highlight_quote && (
                    <div>
                      <Typography.Text strong>📸 截图时刻：</Typography.Text>
                      <Typography.Text italic style={{ marginLeft: 8, color: '#389e0d' }}>
                        「{qualityReport.highlight_quote}」
                      </Typography.Text>
                    </div>
                  )}
                  {qualityReport.subscribe_intent_score != null && (
                    <div>
                      <Typography.Text strong>📈 追读意愿估分：</Typography.Text>
                      <Tag
                        color={
                          qualityReport.subscribe_intent_score >= 7
                            ? 'green'
                            : qualityReport.subscribe_intent_score >= 5
                              ? 'orange'
                              : 'red'
                        }
                        style={{ marginLeft: 8 }}
                      >
                        {qualityReport.subscribe_intent_score}/10
                      </Tag>
                      <Typography.Text type="secondary" style={{ marginLeft: 8 }}>
                        {qualityReport.subscribe_intent_score >= 7
                          ? '高意愿，易形成连更'
                          : '需加强章末钩子'}
                      </Typography.Text>
                    </div>
                  )}
                </Space>
              </Card>
            )}
          </Card>
          <Card title="问题清单">
            <List
              dataSource={qualityReport.issues || []}
              locale={{ emptyText: '未发现明显问题' }}
              renderItem={(item) => (
                <List.Item>
                  <Space>
                    <Tag
                      color={
                        ['warning', 'low_hook', 'overdue_foreshadow'].includes(item.type) ? 'orange' : 'red'
                      }
                    >
                      {item.type === 'low_hook'
                        ? '弱钩子'
                        : item.type === 'overdue_foreshadow'
                          ? '逾期伏笔'
                          : item.type}
                    </Tag>
                    <span>{item.description}</span>
                  </Space>
                </List.Item>
              )}
            />
          </Card>
          <Card title="修改建议">
            <List
              dataSource={qualityReport.suggestions || []}
              locale={{ emptyText: '暂无建议' }}
              renderItem={(item) => <List.Item>{item}</List.Item>}
            />
          </Card>
        </Space>
      )}
    </Space>
  )
}

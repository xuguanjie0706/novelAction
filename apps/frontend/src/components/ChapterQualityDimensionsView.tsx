import { Space, Tag, Typography } from 'antd'
import { qualityDimensionLabel } from '../constants/chapterQualityDimensions'
import type { QualityDimensionResult } from '../types/review'

function statusTagColor(status: string | undefined): string {
  if (status === 'fail') return 'red'
  if (status === 'warning') return 'orange'
  return 'blue'
}

type Props = {
  dimensions: Record<string, QualityDimensionResult> | undefined
}

/** 章节质检各维度：中文名 + 分数 + comment（原因） */
export function ChapterQualityDimensionsView({ dimensions }: Props) {
  const entries = Object.entries(dimensions || {})
  if (!entries.length) {
    return <Typography.Text type="secondary">暂无维度评分</Typography.Text>
  }

  return (
    <Space direction="vertical" size={6} style={{ width: '100%' }}>
      {entries.map(([key, dim]) => (
        <div key={key}>
          <Space align="start" size={8} style={{ width: '100%' }}>
            <Tag color={statusTagColor(dim.status)} style={{ margin: 0 }}>
              {dim.score}
            </Tag>
            <div style={{ flex: 1, minWidth: 0 }}>
              <Typography.Text strong style={{ fontSize: 13 }}>
                {qualityDimensionLabel(key)}
              </Typography.Text>
              {dim.comment ? (
                <Typography.Paragraph
                  type="secondary"
                  style={{ marginBottom: 0, marginTop: 2, fontSize: 12 }}
                >
                  {dim.comment}
                </Typography.Paragraph>
              ) : (
                <Typography.Text type="secondary" style={{ fontSize: 12 }}>
                  暂无说明
                </Typography.Text>
              )}
            </div>
          </Space>
        </div>
      ))}
    </Space>
  )
}

import { Card, Col, Empty, List, Row, Space, Statistic, Table, Tag } from 'antd'
import type { ColumnsType } from 'antd/es/table'
import type { ReviewChapter } from '../../../types/review'

type OverviewTabProps = {
  chapters: ReviewChapter[]
  chapterColumns: ColumnsType<ReviewChapter>
  overviewAvg: number | undefined
  lowCount: number
  outlineRiskChapters: Array<{
    id: string
    title: string
    chapterNo: number
    score: number | undefined
  }>
}

/** 总览：章节评分统计与偏纲风险 */
export function OverviewTab({
  chapters,
  chapterColumns,
  overviewAvg,
  lowCount,
  outlineRiskChapters,
}: OverviewTabProps) {
  return (
    <Space direction="vertical" size="middle" style={{ width: '100%' }}>
      <Row gutter={16}>
        <Col span={8}>
          <Card>
            <Statistic title="章节总数" value={chapters.length} />
          </Card>
        </Col>
        <Col span={8}>
          <Card>
            <Statistic title="平均分（已评测）" value={overviewAvg ?? '-'} />
          </Card>
        </Col>
        <Col span={8}>
          <Card>
            <Statistic title="低分章节（<70）" value={lowCount} />
          </Card>
        </Col>
      </Row>
      <Card title="章节评分概览">
        <Table<ReviewChapter>
          size="small"
          rowKey="id"
          pagination={false}
          columns={chapterColumns}
          dataSource={chapters}
          locale={{ emptyText: <Empty description="暂无章节，先在创作端生成章节" /> }}
        />
      </Card>
      <Card title="偏纲风险章节（大纲匹配度 < 70）">
        {outlineRiskChapters.length === 0 ? (
          <Empty description="当前暂无偏纲风险章节（或尚未产生大纲匹配度历史数据）" />
        ) : (
          <List
            dataSource={outlineRiskChapters}
            renderItem={(item) => (
              <List.Item>
                <Space>
                  <Tag color="red">第{item.chapterNo}章</Tag>
                  <span>{item.title}</span>
                  <Tag color="orange">大纲匹配度：{item.score}</Tag>
                </Space>
              </List.Item>
            )}
          />
        )}
      </Card>
    </Space>
  )
}

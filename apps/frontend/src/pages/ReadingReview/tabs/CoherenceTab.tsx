import { Button, Card, Checkbox, Col, List, Row, Select, Space, Tag, Typography } from 'antd'
import type { ChapterCoherenceResult, CoherenceReportRecord, ReviewChapter } from '../../../types/review'

type ChapterOption = { label: string; value: string }

type CoherenceTabProps = {
  chapters: ReviewChapter[]
  chapterOptions: ChapterOption[]
  selectedCoherenceChapters: string[]
  onSelectedChaptersChange: (ids: string[]) => void
  rangeStartId: string | undefined
  rangeEndId: string | undefined
  anchorChapterId: string | undefined
  onRangeStartChange: (id: string) => void
  onRangeEndChange: (id: string) => void
  onAnchorChange: (id: string) => void
  applyContinuousRange: (startId?: string, endId?: string) => void
  applyAnchorWindow: (size: number, direction: 'prev' | 'next') => void
  selectedRangeHint: string
  coherenceLoading: boolean
  onRunCoherenceCheck: () => void
  coherenceResult: ChapterCoherenceResult | null
  saveLoading: boolean
  lastSavedCoherenceReport: CoherenceReportRecord | null
  onOpenRevisionDrawer: (report: CoherenceReportRecord) => void
}

/** 连贯性评测 Tab */
export function CoherenceTab({
  chapters,
  chapterOptions,
  selectedCoherenceChapters,
  onSelectedChaptersChange,
  rangeStartId,
  rangeEndId,
  anchorChapterId,
  onRangeStartChange,
  onRangeEndChange,
  onAnchorChange,
  applyContinuousRange,
  applyAnchorWindow,
  selectedRangeHint,
  coherenceLoading,
  onRunCoherenceCheck,
  coherenceResult,
  saveLoading,
  lastSavedCoherenceReport,
  onOpenRevisionDrawer,
}: CoherenceTabProps) {
  return (
    <Space direction="vertical" size="middle" style={{ width: '100%' }}>
      <Card title="选择章节范围">
        <Space direction="vertical" style={{ width: '100%' }} size="middle">
          <Space>
            <Button onClick={() => onSelectedChaptersChange(chapters.slice(-3).map((c) => c.id))}>
              最近3章
            </Button>
            <Button onClick={() => onSelectedChaptersChange(chapters.slice(-5).map((c) => c.id))}>
              最近5章
            </Button>
            <Button onClick={() => onSelectedChaptersChange(chapters.slice(-10).map((c) => c.id))}>
              最近10章
            </Button>
          </Space>
          <Space wrap>
            <Select
              style={{ width: 260 }}
              placeholder="起始章节"
              options={chapterOptions}
              value={rangeStartId}
              onChange={(val) => {
                onRangeStartChange(val)
                applyContinuousRange(val, rangeEndId)
              }}
            />
            <Select
              style={{ width: 260 }}
              placeholder="结束章节"
              options={chapterOptions}
              value={rangeEndId}
              onChange={(val) => {
                onRangeEndChange(val)
                applyContinuousRange(rangeStartId, val)
              }}
            />
            <Button onClick={() => applyContinuousRange(rangeStartId, rangeEndId)}>应用连续范围</Button>
          </Space>
          <Space wrap>
            <Select
              style={{ width: 260 }}
              placeholder="先选一个锚点章节"
              options={chapterOptions}
              value={anchorChapterId}
              onChange={onAnchorChange}
            />
            <Button onClick={() => applyAnchorWindow(3, 'prev')}>选中该章及前2章</Button>
            <Button onClick={() => applyAnchorWindow(5, 'prev')}>选中该章及前4章</Button>
            <Button onClick={() => applyAnchorWindow(10, 'prev')}>选中该章及前9章</Button>
            <Button onClick={() => applyAnchorWindow(3, 'next')}>选中该章及后2章</Button>
            <Button onClick={() => applyAnchorWindow(5, 'next')}>选中该章及后4章</Button>
            <Button onClick={() => applyAnchorWindow(10, 'next')}>选中该章及后9章</Button>
          </Space>
          <Typography.Text type="secondary">
            已选 {selectedCoherenceChapters.length} 章（{selectedRangeHint}）
          </Typography.Text>
          <div
            style={{
              maxHeight: 280,
              overflowY: 'auto',
              padding: 12,
              border: '1px solid #f0f0f0',
              borderRadius: 8,
              background: '#fafafa',
            }}
          >
            <Checkbox.Group
              style={{ width: '100%' }}
              value={selectedCoherenceChapters}
              onChange={(vals) => onSelectedChaptersChange(vals as string[])}
            >
              <Row gutter={[12, 12]}>
                {chapters.map((c) => (
                  <Col key={c.id} span={8}>
                    <Checkbox value={c.id}>
                      第{c.sort_order + 1}章 · {c.title || '未命名'}
                    </Checkbox>
                  </Col>
                ))}
              </Row>
            </Checkbox.Group>
          </div>
          <Button type="primary" loading={coherenceLoading} onClick={() => void onRunCoherenceCheck()}>
            开始连贯性评测
          </Button>
        </Space>
      </Card>

      {coherenceResult ? (
        <Space direction="vertical" size="middle" style={{ width: '100%' }}>
          <Card title="评测结果">
            <Space wrap>
              <Tag color="blue">总分：{coherenceResult.overall_score}</Tag>
              <Tag color="geekblue">标题匹配：{coherenceResult.title_match_score}</Tag>
              <Tag color="purple">跨章连贯：{coherenceResult.continuity_score}</Tag>
            </Space>
            <Typography.Paragraph style={{ marginTop: 12, marginBottom: 0 }}>
              {coherenceResult.summary || '暂无总结'}
            </Typography.Paragraph>
          </Card>
          <Card title="跨章风险">
            <List
              dataSource={coherenceResult.cross_chapter_issues || []}
              locale={{ emptyText: '未发现明显跨章风险' }}
              renderItem={(item) => (
                <List.Item>
                  <Space>
                    <Tag color={item.severity === 'warning' ? 'orange' : 'red'}>{item.type}</Tag>
                    <span>{item.description}</span>
                  </Space>
                </List.Item>
              )}
            />
          </Card>
          <Card title="修改建议">
            <List
              dataSource={coherenceResult.suggestions || []}
              locale={{ emptyText: '暂无建议' }}
              renderItem={(item) => <List.Item>{item}</List.Item>}
            />
          </Card>
          <Card title="章节点评（标题匹配）">
            <List
              dataSource={coherenceResult.chapter_evaluations || []}
              locale={{ emptyText: '暂无章节点评' }}
              renderItem={(item) => (
                <List.Item>
                  <Space direction="vertical" size={2} style={{ width: '100%' }}>
                    <Space wrap>
                      <Typography.Text strong>{item.chapter_title || item.chapter_id}</Typography.Text>
                      <Tag>{item.risk_level}</Tag>
                      <Typography.Text type="secondary">标题匹配 {item.title_match_score}</Typography.Text>
                    </Space>
                    <Typography.Text type="secondary">{item.title_match_comment}</Typography.Text>
                  </Space>
                </List.Item>
              )}
            />
          </Card>
          <Card size="small" type="inner" title="正文修订">
            <Space direction="vertical" style={{ width: '100%' }}>
              <Typography.Text type="secondary" style={{ fontSize: 13 }}>
                报告已自动保存后，可在此进入「定向修订」：勾选要落实的条目，并可选填关键词与补充说明，再生成预览。
              </Typography.Text>
              <Button
                type="primary"
                disabled={!lastSavedCoherenceReport}
                onClick={() => lastSavedCoherenceReport && onOpenRevisionDrawer(lastSavedCoherenceReport)}
              >
                定向修订正文
              </Button>
            </Space>
          </Card>
          <Card title="保存状态">
            <Typography.Text type={saveLoading ? 'secondary' : 'success'}>
              {saveLoading ? '正在自动保存报告...' : '评测结果已自动保存到历史记录'}
            </Typography.Text>
          </Card>
        </Space>
      ) : null}
    </Space>
  )
}

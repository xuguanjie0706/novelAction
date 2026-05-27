import { Button, Card, Empty, List, Space, Steps, Table, Tag, Typography } from 'antd'
import type {
  CoherenceApplyChapterResult,
  CoherenceReportRecord,
  ReviewChapter,
} from '../../types/review'

type ApplyTimelineRow = {
  appliedAt: string
  reportId: string
  reportName: string
  applied: CoherenceApplyChapterResult[]
}

type HistoryReportListProps = {
  revisionStepIndex: number
  applyTimeline: ApplyTimelineRow[]
  chapters: ReviewChapter[]
  formatApplyChapterLine: (chapters: ReviewChapter[], a: CoherenceApplyChapterResult) => string
  compareA: CoherenceReportRecord | undefined
  compareB: CoherenceReportRecord | undefined
  historyLoading: boolean
  historyRows: CoherenceReportRecord[]
  compareIds: string[]
  onCompareIdsChange: (ids: string[]) => void
  coherenceApplyLoadingId: string | null
  onOpenRevisionDrawer: (row: CoherenceReportRecord) => void
}

/** 报告与修订：历史列表、对比与展开详情 */
export function HistoryReportList({
  revisionStepIndex,
  applyTimeline,
  chapters,
  formatApplyChapterLine,
  compareA,
  compareB,
  historyLoading,
  historyRows,
  compareIds,
  onCompareIdsChange,
  coherenceApplyLoadingId,
  onOpenRevisionDrawer,
}: HistoryReportListProps) {
  return (
    <Card>
      <Steps
        size="small"
        current={revisionStepIndex}
        style={{ marginBottom: 20 }}
        items={[
          { title: '选择报告与条目', description: '勾选评测结论' },
          { title: '定向条件', description: '关键词与说明' },
          { title: '预览并写入', description: '确认后落库' },
        ]}
      />
      <Card size="small" style={{ marginBottom: 16 }} title="改正文写入记录（按评测落库，可回顾每次「写入数据库」）">
        <Typography.Paragraph type="secondary" style={{ marginTop: 0, marginBottom: 12, fontSize: 12 }}>
          每次点击「写入数据库」后都会落库保存；离开或刷新页面后再进来，仍在本页按时间显示。也可展开下方对应报告，查看「本报告的改正文历史」。
        </Typography.Paragraph>
        {applyTimeline.length === 0 ? (
          <Typography.Text type="secondary">
            暂无记录。在下方报告中展开，点击「定向修订」→ 勾选条目并生成预览 →「写入数据库」后即会出现。
          </Typography.Text>
        ) : (
          <List
            size="small"
            dataSource={applyTimeline}
            renderItem={(item) => (
              <List.Item>
                <Space direction="vertical" size={4} style={{ width: '100%' }}>
                  <Space wrap>
                    <Tag color="green">{new Date(item.appliedAt).toLocaleString('zh-CN')}</Tag>
                    <Typography.Text type="secondary">来源报告：</Typography.Text>
                    <Typography.Text strong>{item.reportName}</Typography.Text>
                  </Space>
                  <Typography.Text type="secondary" style={{ fontSize: 12 }}>
                    {item.applied.map((a) => formatApplyChapterLine(chapters, a)).join('；')}
                  </Typography.Text>
                </Space>
              </List.Item>
            )}
          />
        )}
      </Card>
      {compareA && compareB ? (
        <Card
          size="small"
          style={{ marginBottom: 16, background: '#f6ffed', borderColor: '#b7eb8f' }}
          title="报告对比（本次 vs 上次）"
        >
          <Space direction="vertical" style={{ width: '100%' }}>
            <Typography.Text>
              {compareA.name}（{compareA.result?.overall_score ?? '-'}） vs {compareB.name}（
              {compareB.result?.overall_score ?? '-'}）
            </Typography.Text>
            <Typography.Text type="secondary">
              分差：{Number((compareA.result?.overall_score ?? 0) - (compareB.result?.overall_score ?? 0)).toFixed(1)}
            </Typography.Text>
            <Typography.Text type="secondary">
              标题匹配分差：
              {Number((compareA.result?.title_match_score ?? 0) - (compareB.result?.title_match_score ?? 0)).toFixed(1)}
            </Typography.Text>
            <Typography.Text type="secondary">
              连贯性分差：
              {Number((compareA.result?.continuity_score ?? 0) - (compareB.result?.continuity_score ?? 0)).toFixed(1)}
            </Typography.Text>
          </Space>
        </Card>
      ) : null}
      <Table<CoherenceReportRecord>
        rowKey="id"
        loading={historyLoading}
        dataSource={historyRows}
        pagination={{ pageSize: 10 }}
        rowSelection={{
          selectedRowKeys: compareIds,
          onChange: (keys) => onCompareIdsChange((keys as string[]).slice(-2)),
        }}
        columns={[
          { title: '报告名', dataIndex: 'name' },
          { title: '模型', dataIndex: 'model_profile', width: 120 },
          {
            title: '章节数',
            width: 100,
            render: (_, row) => row.selected_chapter_ids?.length ?? 0,
          },
          {
            title: '总分',
            width: 100,
            render: (_, row) => row.result?.overall_score ?? '-',
          },
          {
            title: '创建时间',
            dataIndex: 'created_at',
            width: 220,
          },
          {
            title: '改正文',
            width: 100,
            render: (_, row) =>
              row.apply_events?.length ? <Tag color="processing">{row.apply_events.length} 次</Tag> : '—',
          },
        ]}
        expandable={{
          expandedRowRender: (row) => (
            <Space direction="vertical" style={{ width: '100%' }}>
              <Space wrap>
                <Button
                  type="primary"
                  size="small"
                  loading={coherenceApplyLoadingId === row.id}
                  disabled={!!row.result?.error}
                  onClick={() => onOpenRevisionDrawer(row)}
                >
                  定向修订
                </Button>
                <Typography.Text type="secondary" style={{ fontSize: 12 }}>
                  勾选要落实的评测条目，可填关键词；按最小幅度修改并预览，确认后再写入数据库（自动打修订前快照）。
                </Typography.Text>
              </Space>
              {(row.apply_events?.length ?? 0) > 0 ? (
                <Card size="small" title="本报告的改正文历史" type="inner">
                  <List
                    size="small"
                    dataSource={row.apply_events}
                    renderItem={(ev, idx) => (
                      <List.Item>
                        <Space direction="vertical" size={4} style={{ width: '100%' }}>
                          <Typography.Text strong>
                            第 {idx + 1} 次写入 · {new Date(ev.applied_at).toLocaleString('zh-CN')}
                          </Typography.Text>
                          <Typography.Text type="secondary" style={{ fontSize: 12 }}>
                            {(ev.applied ?? []).map((a) => formatApplyChapterLine(chapters, a)).join('；')}
                          </Typography.Text>
                        </Space>
                      </List.Item>
                    )}
                  />
                </Card>
              ) : null}
              <Typography.Text type="secondary">{row.result?.summary || '暂无总结'}</Typography.Text>
              <List
                size="small"
                header="建议"
                dataSource={row.result?.suggestions || []}
                locale={{ emptyText: '暂无建议' }}
                renderItem={(item) => <List.Item>{item}</List.Item>}
              />
            </Space>
          ),
        }}
        locale={{ emptyText: <Empty description="暂无历史报告" /> }}
      />
    </Card>
  )
}

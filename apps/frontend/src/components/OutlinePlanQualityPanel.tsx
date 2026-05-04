import { Card, Collapse, List, Space, Tag, Typography } from 'antd'
import type { OutlinePlanQualityReport } from '../types/review'

function statusColor(status: string | undefined) {
  const s = (status || '').toLowerCase()
  if (s === 'fail') return 'red'
  if (s === 'warning') return 'orange'
  if (s === 'pass') return 'green'
  return 'default'
}

const REPORT_STATUS_LABELS: Record<string, string> = {
  pass: '通过',
  fail: '未通过',
  warning: '警告',
  excellent: '优秀',
}

export default function OutlinePlanQualityPanel({ report, title }: { report: OutlinePlanQualityReport; title?: string }) {
  if (report.error) {
    return (
      <Typography.Text type="danger">
        {title ? `${title}：` : ''}质检失败：{String(report.error)}
      </Typography.Text>
    )
  }

  const issues = report.issues ?? []
  const must = report.must_fix_chapter_numbers ?? []

  return (
    <Space direction="vertical" size="small" style={{ width: '100%' }}>
      <Space wrap>
        {report.overall_score != null && (
          <Typography.Text strong>总分：{String(report.overall_score)}</Typography.Text>
        )}
        {report.status && (
          <Tag color={statusColor(report.status)}>
            {REPORT_STATUS_LABELS[(report.status || '').toLowerCase()] ?? report.status}
          </Tag>
        )}
        {report.scope && <Typography.Text type="secondary">范围：{report.scope}</Typography.Text>}
      </Space>
      {report.summary && <Typography.Paragraph type="secondary" style={{ marginBottom: 0 }}>{report.summary}</Typography.Paragraph>}
      {must.length > 0 && (
        <div>
          <Typography.Text type="secondary">必修章节：</Typography.Text>{' '}
          {must.map((n) => (
            <Tag key={n}>第{n}章</Tag>
          ))}
        </div>
      )}
      {issues.length > 0 && (
        <List
          size="small"
          bordered
          dataSource={issues}
          locale={{ emptyText: '—' }}
          renderItem={(issue) => (
            <List.Item style={{ flexDirection: 'column', alignItems: 'stretch' }}>
              <Space wrap size={4}>
                {issue.severity && <Tag>{issue.severity}</Tag>}
                {issue.type && <Typography.Text type="secondary">{issue.type}</Typography.Text>}
                {issue.chapter_numbers && issue.chapter_numbers.length > 0 && (
                  <Typography.Text type="secondary">章 {issue.chapter_numbers.join('、')}</Typography.Text>
                )}
              </Space>
              <Typography.Paragraph style={{ marginBottom: 0, marginTop: 4 }}>{issue.description}</Typography.Paragraph>
              {issue.suggested_patch?.replacement && (
                <Typography.Text type="secondary" style={{ fontSize: 12 }}>
                  建议：{issue.suggested_patch.replacement}
                </Typography.Text>
              )}
            </List.Item>
          )}
        />
      )}
      {(report.strengths ?? []).length > 0 && (
        <div>
          <Typography.Text strong style={{ fontSize: 12 }}>亮点</Typography.Text>
          <ul style={{ margin: '4px 0 0 16px', padding: 0 }}>
            {(report.strengths ?? []).map((s, i) => (
              <li key={i}><Typography.Text style={{ fontSize: 12 }}>{s}</Typography.Text></li>
            ))}
          </ul>
        </div>
      )}
    </Space>
  )
}

export function OutlineQualityManagementSection({
  loading,
  bookReport,
  volumeReports,
}: {
  loading: boolean
  bookReport: OutlinePlanQualityReport | null
  volumeReports: Array<{ title: string; report: OutlinePlanQualityReport }>
}) {
  if (loading) {
    return <Card size="small" title="大纲计划质检（结构化）" loading />
  }

  const hasAny =
    (bookReport && Object.keys(bookReport).length > 0) || (volumeReports && volumeReports.length > 0)

  if (!hasAny) {
    return (
      <Card size="small" title="大纲计划质检">
        <Typography.Text type="secondary">
          暂无数据。使用 Gemini 进行「全量生成大纲」且完成后，全书与各卷的结构化质检会落库于此。
        </Typography.Text>
      </Card>
    )
  }

  const items = []
  if (bookReport) {
    items.push({
      key: 'book',
      label: '全书大纲质检',
      children: <OutlinePlanQualityPanel report={bookReport} />,
    })
  }
  volumeReports.forEach((v, i) => {
    items.push({
      key: `vol-${i}-${v.title}`,
      label: `卷内质检 · ${v.title}`,
      children: <OutlinePlanQualityPanel report={v.report} title={v.title} />,
    })
  })

  return (
    <Card size="small" title="大纲计划质检（结构化）" loading={loading}>
      <Collapse items={items} />
    </Card>
  )
}

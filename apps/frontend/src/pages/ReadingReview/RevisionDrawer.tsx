import { Button, Checkbox, Divider, Drawer, Input, Select, Space, Tag, Typography } from 'antd'
import type { CoherenceReportRecord } from '../../types/review'
import { clipLabel } from './utils'

type RevisionDrawerProps = {
  open: boolean
  report: CoherenceReportRecord | null
  focusIssueIndices: number[]
  focusSuggIndices: number[]
  focusEvalIndices: number[]
  revisionKeywordTags: string[]
  revisionNote: string
  loading: boolean
  onClose: () => void
  onFocusIssueChange: (indices: number[]) => void
  onFocusSuggChange: (indices: number[]) => void
  onFocusEvalChange: (indices: number[]) => void
  onKeywordTagsChange: (tags: string[]) => void
  onRevisionNoteChange: (note: string) => void
  onSubmitPreview: () => void
}

/** 定向修订：勾选评测条目与补充条件 */
export function RevisionDrawer({
  open,
  report,
  focusIssueIndices,
  focusSuggIndices,
  focusEvalIndices,
  revisionKeywordTags,
  revisionNote,
  loading,
  onClose,
  onFocusIssueChange,
  onFocusSuggChange,
  onFocusEvalChange,
  onKeywordTagsChange,
  onRevisionNoteChange,
  onSubmitPreview,
}: RevisionDrawerProps) {
  return (
    <Drawer
      title="定向修订"
      width={560}
      open={open}
      onClose={onClose}
      destroyOnClose
      footer={
        <Space style={{ width: '100%', justifyContent: 'flex-end' }}>
          <Button onClick={onClose}>关闭</Button>
          <Button
            type="primary"
            loading={loading}
            disabled={!report || !!report.result?.error}
            onClick={() => void onSubmitPreview()}
          >
            生成修订预览
          </Button>
        </Space>
      }
    >
      {report ? (
        <Space direction="vertical" size="middle" style={{ width: '100%' }}>
          <div>
            <Typography.Text strong>{report.name}</Typography.Text>
            <Typography.Text type="secondary" style={{ marginLeft: 8 }}>
              {new Date(report.created_at).toLocaleString('zh-CN')}
            </Typography.Text>
          </div>
          <Typography.Paragraph type="secondary" style={{ marginBottom: 0 }}>
            {report.result?.summary || '暂无摘要'}
          </Typography.Paragraph>
          <Divider orientation="left" plain style={{ margin: '8px 0' }}>
            勾选要纳入改正文的条目
          </Divider>
          <div>
            <Space style={{ marginBottom: 8 }} wrap>
              <Typography.Text strong>跨章风险</Typography.Text>
              <Button
                type="link"
                size="small"
                style={{ padding: 0, height: 'auto' }}
                onClick={() => {
                  const n = (report.result.cross_chapter_issues ?? []).length
                  onFocusIssueChange(Array.from({ length: n }, (_, i) => i))
                }}
              >
                全选
              </Button>
              <Button
                type="link"
                size="small"
                style={{ padding: 0, height: 'auto' }}
                onClick={() => onFocusIssueChange([])}
              >
                全不选
              </Button>
            </Space>
            {(report.result.cross_chapter_issues ?? []).length === 0 ? (
              <Typography.Text type="secondary">无</Typography.Text>
            ) : (
              <Checkbox.Group
                style={{ width: '100%' }}
                value={focusIssueIndices}
                onChange={(vals) => onFocusIssueChange(vals as number[])}
              >
                <Space direction="vertical" style={{ width: '100%' }}>
                  {(report.result.cross_chapter_issues ?? []).map((item, idx) => (
                    <Checkbox key={`iss-${idx}`} value={idx}>
                      <Tag color={item.severity === 'warning' ? 'orange' : 'red'}>{item.type}</Tag>
                      {clipLabel(item.description, 200)}
                    </Checkbox>
                  ))}
                </Space>
              </Checkbox.Group>
            )}
          </div>
          <div>
            <Space style={{ marginBottom: 8 }} wrap>
              <Typography.Text strong>修改建议</Typography.Text>
              <Button
                type="link"
                size="small"
                style={{ padding: 0, height: 'auto' }}
                onClick={() => {
                  const n = (report.result.suggestions ?? []).length
                  onFocusSuggChange(Array.from({ length: n }, (_, i) => i))
                }}
              >
                全选
              </Button>
              <Button
                type="link"
                size="small"
                style={{ padding: 0, height: 'auto' }}
                onClick={() => onFocusSuggChange([])}
              >
                全不选
              </Button>
            </Space>
            {(report.result.suggestions ?? []).length === 0 ? (
              <Typography.Text type="secondary">无</Typography.Text>
            ) : (
              <Checkbox.Group
                style={{ width: '100%' }}
                value={focusSuggIndices}
                onChange={(vals) => onFocusSuggChange(vals as number[])}
              >
                <Space direction="vertical" style={{ width: '100%' }}>
                  {(report.result.suggestions ?? []).map((item, idx) => (
                    <Checkbox key={`sug-${idx}`} value={idx}>
                      {clipLabel(item, 220)}
                    </Checkbox>
                  ))}
                </Space>
              </Checkbox.Group>
            )}
          </div>
          <div>
            <Space style={{ marginBottom: 8 }} wrap>
              <Typography.Text strong>章节点评</Typography.Text>
              <Button
                type="link"
                size="small"
                style={{ padding: 0, height: 'auto' }}
                onClick={() => {
                  const n = (report.result.chapter_evaluations ?? []).length
                  onFocusEvalChange(Array.from({ length: n }, (_, i) => i))
                }}
              >
                全选
              </Button>
              <Button
                type="link"
                size="small"
                style={{ padding: 0, height: 'auto' }}
                onClick={() => onFocusEvalChange([])}
              >
                全不选
              </Button>
            </Space>
            {(report.result.chapter_evaluations ?? []).length === 0 ? (
              <Typography.Text type="secondary">无</Typography.Text>
            ) : (
              <Checkbox.Group
                style={{ width: '100%' }}
                value={focusEvalIndices}
                onChange={(vals) => onFocusEvalChange(vals as number[])}
              >
                <Space direction="vertical" style={{ width: '100%' }}>
                  {(report.result.chapter_evaluations ?? []).map((ev, idx) => (
                    <Checkbox key={`ev-${idx}`} value={idx}>
                      <Space direction="vertical" size={0}>
                        <Typography.Text strong>{ev.chapter_title || ev.chapter_id}</Typography.Text>
                        <Typography.Text type="secondary">{clipLabel(ev.title_match_comment, 160)}</Typography.Text>
                      </Space>
                    </Checkbox>
                  ))}
                </Space>
              </Checkbox.Group>
            )}
          </div>
          <Divider orientation="left" plain style={{ margin: '8px 0' }}>
            定向条件（可选）
          </Divider>
          <div>
            <Typography.Text type="secondary" style={{ display: 'block', marginBottom: 6 }}>
              关键词（回车添加多个）
            </Typography.Text>
            <Select
              mode="tags"
              style={{ width: '100%' }}
              placeholder="例如：时间线、某角色名、称谓统一"
              value={revisionKeywordTags}
              onChange={onKeywordTagsChange}
              tokenSeparators={[',', '，', ';', '；']}
            />
          </div>
          <div>
            <Typography.Text type="secondary" style={{ display: 'block', marginBottom: 6 }}>
              补充说明
            </Typography.Text>
            <Input.TextArea
              rows={3}
              value={revisionNote}
              onChange={(e) => onRevisionNoteChange(e.target.value)}
              placeholder="可选：风格禁忌、优先处理的矛盾等（与评测冲突时以评测为准）"
              maxLength={2000}
              showCount
            />
          </div>
        </Space>
      ) : null}
    </Drawer>
  )
}

import { Col, Row, Typography } from 'antd'
import { diffLines } from 'diff'
import { useMemo, type CSSProperties } from 'react'

export type ChapterSnapshotDiffViewProps = {
  chapterTitle: string
  leftMeta: string
  rightMeta: string
  leftPlain: string
  rightPlain: string
  /** 左栏标题，默认「改正前（本快照）」 */
  leftHeading?: string
  /** 右栏标题，默认「改正后（当前正文）」 */
  rightHeading?: string
}

export type AlignedDiffRow = {
  left: string
  right: string
  leftChanged: boolean
  rightChanged: boolean
}

/** 将 diff 块拆成不含换行符的展示行 */
function chunkToDisplayLines(value: string): string[] {
  const s = value.replace(/\r\n/g, '\n')
  if (!s) return []
  const hasFinalNl = s.endsWith('\n')
  const core = hasFinalNl ? s.slice(0, -1) : s
  if (core === '') return hasFinalNl ? [''] : []
  return core.split('\n')
}

/** 行级对齐：便于左右同高、单滚动条对照；变更行在左/右分别高亮 */
export function alignChapterLines(before: string, after: string): AlignedDiffRow[] {
  const a = before.replace(/\r\n/g, '\n')
  const b = after.replace(/\r\n/g, '\n')
  const parts = diffLines(a, b)
  const rows: AlignedDiffRow[] = []

  for (let i = 0; i < parts.length; i++) {
    const part = parts[i]
    if (!part.added && !part.removed) {
      for (const line of chunkToDisplayLines(part.value)) {
        rows.push({ left: line, right: line, leftChanged: false, rightChanged: false })
      }
    } else if (part.removed) {
      const next = parts[i + 1]
      if (next?.added) {
        const lLines = chunkToDisplayLines(part.value)
        const rLines = chunkToDisplayLines(next.value)
        const n = Math.max(lLines.length, rLines.length)
        for (let j = 0; j < n; j++) {
          const left = lLines[j] ?? ''
          const right = rLines[j] ?? ''
          rows.push({
            left,
            right,
            leftChanged: j < lLines.length,
            rightChanged: j < rLines.length,
          })
        }
        i++
      } else {
        for (const line of chunkToDisplayLines(part.value)) {
          rows.push({ left: line, right: '', leftChanged: true, rightChanged: false })
        }
      }
    } else if (part.added) {
      for (const line of chunkToDisplayLines(part.value)) {
        rows.push({ left: '', right: line, leftChanged: false, rightChanged: true })
      }
    }
  }

  return rows
}

const cellBase: CSSProperties = {
  whiteSpace: 'pre-wrap',
  wordBreak: 'break-word',
  fontSize: 13,
  lineHeight: 1.6,
  padding: '6px 10px',
  borderBottom: '1px solid #f5f5f5',
  verticalAlign: 'top',
}

export function ChapterSnapshotDiffView({
  chapterTitle,
  leftMeta,
  rightMeta,
  leftPlain,
  rightPlain,
  leftHeading = '改正前（本快照）',
  rightHeading = '改正后（当前正文）',
}: ChapterSnapshotDiffViewProps) {
  const rows = useMemo(() => alignChapterLines(leftPlain, rightPlain), [leftPlain, rightPlain])
  const displayRows = useMemo(
    () =>
      rows.length > 0
        ? rows
        : [{ left: '（空）', right: '（空）', leftChanged: false, rightChanged: false }],
    [rows],
  )

  return (
    <>
      <Row gutter={16} style={{ marginBottom: 12 }}>
        <Col span={12}>
          <Typography.Text strong style={{ display: 'block' }}>
            {leftHeading} · {chapterTitle}
          </Typography.Text>
          <Typography.Text type="secondary" style={{ display: 'block', fontSize: 12, marginTop: 4 }}>
            {leftMeta}
          </Typography.Text>
        </Col>
        <Col span={12}>
          <Typography.Text strong style={{ display: 'block' }}>
            {rightHeading} · {chapterTitle}
          </Typography.Text>
          <Typography.Text type="secondary" style={{ display: 'block', fontSize: 12, marginTop: 4 }}>
            {rightMeta}
          </Typography.Text>
        </Col>
      </Row>
      <Typography.Text type="secondary" style={{ fontSize: 12, display: 'block', marginBottom: 8 }}>
        下方共用一个滚动条，左右逐行对齐；左栏浅红为删改侧，右栏浅绿为新增侧。
      </Typography.Text>
      <div
        style={{
          maxHeight: '65vh',
          overflow: 'auto',
          border: '1px solid #f0f0f0',
          borderRadius: 8,
          background: '#fff',
        }}
      >
        <table
          style={{
            width: '100%',
            tableLayout: 'fixed',
            borderCollapse: 'collapse',
          }}
        >
          <colgroup>
            <col style={{ width: '50%' }} />
            <col style={{ width: '50%' }} />
          </colgroup>
          <tbody>
            {displayRows.map((row, idx) => (
              <tr key={idx}>
                <td
                  style={{
                    ...cellBase,
                    borderRight: '1px solid #f0f0f0',
                    background: row.leftChanged ? '#fff1f0' : '#fff',
                  }}
                >
                  {row.left || '\u00a0'}
                </td>
                <td
                  style={{
                    ...cellBase,
                    background: row.rightChanged ? '#f6ffed' : '#fafafa',
                  }}
                >
                  {row.right || '\u00a0'}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </>
  )
}

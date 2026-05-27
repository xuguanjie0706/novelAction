import { Button, Card, Empty, Space, Table, Tag, Typography } from 'antd'
import type { ChapterVersionTimelineItem } from '../../../types/review'
import { snapshotSourceTag } from '../utils'

type BodySnapshotsTabProps = {
  versionTimelineLoading: boolean
  versionTimelineRows: ChapterVersionTimelineItem[]
  onOpenSnapshotDiff: (row: ChapterVersionTimelineItem) => void
  onGoToEditor: (chapterId: string) => void
}

/** 正文快照时间轴 */
export function BodySnapshotsTab({
  versionTimelineLoading,
  versionTimelineRows,
  onOpenSnapshotDiff,
  onGoToEditor,
}: BodySnapshotsTabProps) {
  return (
    <Card>
      <Typography.Paragraph type="secondary" style={{ marginTop: 0 }}>
        此处按时间列出本书各章的「修订前快照」（连贯性评测在点「写入数据库」时会自动各落一条）。点「改正前后对照」会并排展示：左侧为该快照保存时的正文（改正前），右侧为当前章节在数据库中的正文（改正后）；若尚未写入或正文未变，两侧可能相同。
      </Typography.Paragraph>
      <Table<ChapterVersionTimelineItem>
        rowKey="id"
        loading={versionTimelineLoading}
        dataSource={versionTimelineRows}
        pagination={{ pageSize: 15 }}
        locale={{ emptyText: <Empty description="暂无快照。写入改正文或手动保存版本后会出现" /> }}
        columns={[
          {
            title: '快照时间',
            dataIndex: 'created_at',
            width: 200,
            render: (v: string) => new Date(v).toLocaleString('zh-CN'),
          },
          {
            title: '章节',
            render: (_, row) => `第${row.chapter_sort_order + 1}章 · ${row.chapter_title || '未命名'}`,
          },
          {
            title: '来源',
            width: 130,
            render: (_, row) => {
              const t = snapshotSourceTag(row.note, row.is_auto)
              return <Tag color={t.color}>{t.text}</Tag>
            },
          },
          {
            title: '备注',
            dataIndex: 'note',
            ellipsis: true,
            render: (v: string | null | undefined) => v || '—',
          },
          {
            title: '字数',
            dataIndex: 'word_count',
            width: 90,
            render: (w: number | null | undefined) => (w != null ? w : '—'),
          },
          {
            title: '操作',
            width: 200,
            render: (_, row) => (
              <Space size="small">
                <Button type="link" size="small" onClick={() => void onOpenSnapshotDiff(row)}>
                  改正前后对照
                </Button>
                <Button type="link" size="small" onClick={() => onGoToEditor(row.chapter_id)}>
                  去编辑
                </Button>
              </Space>
            ),
          },
        ]}
      />
    </Card>
  )
}

import { useState } from 'react'
import { Button, List, Modal, Space, Tag, Typography } from 'antd'
import { DiffOutlined } from '@ant-design/icons'
import type { CoherenceApplyRevisionPreview } from '../../types/review'
import { RevisionTextCompareModal } from './RevisionTextCompareModal'

type CoherenceApplyModalProps = {
  open: boolean
  revisions: CoherenceApplyRevisionPreview[]
  committing: boolean
  onCancel: () => void
  onCommit: () => void
}

type CompareTarget = {
  chapterTitle: string
  leftPlain: string
  rightPlain: string
}

/** 连贯性修订预览与写入确认 */
export function CoherenceApplyModal({
  open,
  revisions,
  committing,
  onCancel,
  onCommit,
}: CoherenceApplyModalProps) {
  const [compareTarget, setCompareTarget] = useState<CompareTarget | null>(null)

  const openCompare = (item: CoherenceApplyRevisionPreview) => {
    const left = (item.previous_plain || item.previous_plain_preview || '').trim()
    const right = (item.revised_content || item.revised_plain_preview || '').trim()
    if (!left && !right) return
    setCompareTarget({
      chapterTitle: item.chapter_title || item.chapter_id,
      leftPlain: left,
      rightPlain: right,
    })
  }

  return (
    <>
      <Modal
        title="连贯性修订预览"
        open={open}
        onCancel={onCancel}
        width={640}
        footer={[
          <Button key="cancel" onClick={onCancel}>
            返回修改条件
          </Button>,
          <Button
            key="ok"
            type="primary"
            loading={committing}
            disabled={revisions.every((r) => r.unchanged || !r.revised_content.trim())}
            onClick={() => void onCommit()}
          >
            写入数据库
          </Button>,
        ]}
      >
        <Typography.Paragraph type="secondary" style={{ marginTop: 0, fontSize: 12 }}>
          有改动的章节可点「对比」查看改写前后全文；确认无误后再写入数据库。
        </Typography.Paragraph>
        <List
          size="small"
          dataSource={revisions}
          locale={{ emptyText: '暂无预览数据' }}
          renderItem={(item) => (
            <List.Item
              actions={
                !item.unchanged
                  ? [
                      <Button
                        key="diff"
                        type="link"
                        size="small"
                        icon={<DiffOutlined />}
                        onClick={() => openCompare(item)}
                      >
                        对比
                      </Button>,
                    ]
                  : undefined
              }
            >
              <Space direction="vertical" size={4} style={{ width: '100%' }}>
                <Space wrap>
                  <Typography.Text strong>{item.chapter_title || item.chapter_id}</Typography.Text>
                  <Tag color={item.unchanged ? 'default' : 'orange'}>{item.unchanged ? '未改动' : '有修订'}</Tag>
                </Space>
                {item.change_note ? (
                  <Typography.Text type="secondary" style={{ fontSize: 12 }}>
                    {item.change_note}
                  </Typography.Text>
                ) : null}
              </Space>
            </List.Item>
          )}
        />
      </Modal>

      <RevisionTextCompareModal
        open={compareTarget != null}
        chapterTitle={compareTarget?.chapterTitle ?? ''}
        leftPlain={compareTarget?.leftPlain ?? ''}
        rightPlain={compareTarget?.rightPlain ?? ''}
        onClose={() => setCompareTarget(null)}
      />
    </>
  )
}

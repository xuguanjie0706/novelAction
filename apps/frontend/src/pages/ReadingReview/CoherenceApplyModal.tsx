import { Button, Col, List, Modal, Row, Space, Tag, Typography } from 'antd'
import type { CoherenceApplyRevisionPreview } from '../../types/review'

type CoherenceApplyModalProps = {
  open: boolean
  revisions: CoherenceApplyRevisionPreview[]
  committing: boolean
  onCancel: () => void
  onCommit: () => void
}

/** 连贯性修订预览与写入确认 */
export function CoherenceApplyModal({
  open,
  revisions,
  committing,
  onCancel,
  onCommit,
}: CoherenceApplyModalProps) {
  return (
    <Modal
      title="连贯性修订预览"
      open={open}
      onCancel={onCancel}
      width={720}
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
      <List
        size="small"
        dataSource={revisions}
        locale={{ emptyText: '暂无预览数据' }}
        renderItem={(item) => (
          <List.Item>
            <Space direction="vertical" size={4} style={{ width: '100%' }}>
              <Space wrap>
                <Typography.Text strong>{item.chapter_title || item.chapter_id}</Typography.Text>
                <Tag color={item.unchanged ? 'default' : 'orange'}>{item.unchanged ? '未改动' : '有修订'}</Tag>
              </Space>
              {item.change_note ? <Typography.Text type="secondary">{item.change_note}</Typography.Text> : null}
              {!item.unchanged ? (
                <Row gutter={8}>
                  <Col span={12}>
                    <Typography.Text type="secondary" style={{ fontSize: 12 }}>
                      修前摘要
                    </Typography.Text>
                    <div style={{ fontSize: 12, maxHeight: 120, overflow: 'auto', whiteSpace: 'pre-wrap' }}>
                      {item.previous_plain_preview}
                    </div>
                  </Col>
                  <Col span={12}>
                    <Typography.Text type="secondary" style={{ fontSize: 12 }}>
                      修后摘要
                    </Typography.Text>
                    <div style={{ fontSize: 12, maxHeight: 120, overflow: 'auto', whiteSpace: 'pre-wrap' }}>
                      {item.revised_plain_preview}
                    </div>
                  </Col>
                </Row>
              ) : null}
            </Space>
          </List.Item>
        )}
      />
    </Modal>
  )
}

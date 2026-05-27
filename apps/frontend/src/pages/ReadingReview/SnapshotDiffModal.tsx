import { Button, Modal, Typography } from 'antd'
import { ChapterSnapshotDiffView } from '../../components/ReadingReview/ChapterSnapshotDiffView'
import type { VersionPreviewPanel } from './types'

type SnapshotDiffModalProps = {
  title: string
  open: boolean
  loading: boolean
  panels: VersionPreviewPanel[]
  onClose: () => void
}

/** 改正前后正文对照弹窗 */
export function SnapshotDiffModal({ title, open, loading, panels, onClose }: SnapshotDiffModalProps) {
  return (
    <Modal
      title={title}
      open={open}
      onCancel={onClose}
      footer={[
        <Button key="close" onClick={onClose}>
          关闭
        </Button>,
      ]}
      width={1100}
    >
      {loading && panels.length === 0 ? (
        <Typography.Text type="secondary">加载中…</Typography.Text>
      ) : panels.length >= 2 ? (
        <ChapterSnapshotDiffView
          chapterTitle={panels[0].title}
          leftMeta={panels[0].meta}
          rightMeta={panels[1].meta}
          leftPlain={panels[0].plain}
          rightPlain={panels[1].plain}
        />
      ) : null}
    </Modal>
  )
}

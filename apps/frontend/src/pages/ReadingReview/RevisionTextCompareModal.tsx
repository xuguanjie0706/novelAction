/**
 * @file 连贯性修订预览 — 单章改写前后对照弹窗
 */
import { Modal } from 'antd'
import { ChapterSnapshotDiffView } from '../../components/ReadingReview/ChapterSnapshotDiffView'

export type RevisionTextCompareModalProps = {
  open: boolean
  chapterTitle: string
  leftPlain: string
  rightPlain: string
  leftMeta?: string
  rightMeta?: string
  onClose: () => void
}

/** 改写前后全文对照（与正文快照 Tab 同一 diff 组件） */
export function RevisionTextCompareModal({
  open,
  chapterTitle,
  leftPlain,
  rightPlain,
  leftMeta = '改写前（评测修订前）',
  rightMeta = '改写后（AI 预览稿）',
  onClose,
}: RevisionTextCompareModalProps) {
  return (
    <Modal
      title={`改写前后对比 · ${chapterTitle}`}
      open={open}
      onCancel={onClose}
      footer={null}
      width={1100}
      destroyOnClose
      styles={{
        body: { paddingTop: 8 },
        header: { borderBottom: '1px solid #f0ebe3', background: 'linear-gradient(90deg, #fffbeb 0%, #fff 55%)' },
      }}
    >
      <ChapterSnapshotDiffView
        chapterTitle={chapterTitle}
        leftMeta={leftMeta}
        rightMeta={rightMeta}
        leftPlain={leftPlain}
        rightPlain={rightPlain}
        leftHeading="改写前"
        rightHeading="改写后"
      />
    </Modal>
  )
}

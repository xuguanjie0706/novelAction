/**
 * 纪要页顶栏：返回、继续生成（可恢复 run）、进入工作台。
 */
import React from 'react'
import { ArrowLeft, BookOpen, ChevronRight, Sparkles } from 'lucide-react'
import type { BootstrapResumeSnapshot } from '../../hooks/useBootstrapResumeBanner'

interface Props {
  title: string
  genre?: string | null
  activeSectionLabel: string
  bootstrapResume: BootstrapResumeSnapshot | null
  onContinueBootstrap: () => void
  onEnterWorkbench: () => void
  onBackToDetail: () => void
  onBackToShelf: () => void
}

export default function RecapPageHeader({
  title,
  genre,
  activeSectionLabel,
  bootstrapResume,
  onContinueBootstrap,
  onEnterWorkbench,
  onBackToDetail,
  onBackToShelf,
}: Props) {
  return (
    <header style={{
      height: 52, flexShrink: 0,
      background: '#ffffff', borderBottom: '1px solid #e5e7eb',
      display: 'flex', alignItems: 'center', padding: '0 20px', gap: 12,
      boxShadow: '0 1px 3px rgba(0,0,0,0.04)',
    }}>
      <button
        type="button"
        onClick={onBackToDetail}
        style={{
          display: 'flex', alignItems: 'center', gap: 6,
          padding: '5px 10px', borderRadius: 6,
          background: 'transparent', border: '1px solid #e5e7eb',
          color: '#6b7280', fontSize: 13, cursor: 'pointer',
        }}
      >
        <ArrowLeft size={14} />
        小说详情
      </button>
      <button
        type="button"
        onClick={onBackToShelf}
        style={{
          padding: '5px 10px', borderRadius: 6, border: 'none', background: 'transparent',
          color: '#9ca3af', fontSize: 12, cursor: 'pointer', textDecoration: 'underline',
        }}
      >
        书架
      </button>
      <span style={{ color: '#d1d5db', fontSize: 18 }}>·</span>
      <div style={{ flex: 1, minWidth: 0 }}>
        <span style={{ fontSize: 15, fontWeight: 600, color: '#111827' }}>
          {title || '（未命名项目）'}
        </span>
        {genre && (
          <span style={{
            marginLeft: 10, fontSize: 11, padding: '2px 8px',
            borderRadius: 10, background: '#fef3c7', color: '#b45309',
            border: '1px solid #fde68a',
          }}>
            {genre}
          </span>
        )}
      </div>
      <span style={{ fontSize: 12, color: '#9ca3af' }}>{activeSectionLabel}</span>
      {bootstrapResume && (
        <button
          type="button"
          onClick={onContinueBootstrap}
          style={{
            display: 'flex', alignItems: 'center', gap: 6,
            padding: '6px 14px', borderRadius: 8,
            background: bootstrapResume.resumableFailed ? '#fef3c7' : '#fff',
            border: '1px solid #f59e0b', color: '#b45309', fontSize: 13,
            fontWeight: 600, cursor: 'pointer',
          }}
          title={bootstrapResume.resumeHint || '从上次进度继续，不重头生成'}
        >
          <Sparkles size={14} />
          继续生成
          <ChevronRight size={14} />
        </button>
      )}
      <button
        type="button"
        onClick={onEnterWorkbench}
        style={{
          display: 'flex', alignItems: 'center', gap: 6,
          padding: '6px 16px', borderRadius: 8,
          background: '#C4873A', border: 'none', color: '#fff', fontSize: 13,
          fontWeight: 600, cursor: 'pointer',
        }}
      >
        <BookOpen size={14} />
        进入工作台
      </button>
    </header>
  )
}

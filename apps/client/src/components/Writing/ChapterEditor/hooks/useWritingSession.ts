/**
 * useWritingSession — 本次写作会话字数增量与耗时
 */
import { useEffect, useRef, useState } from 'react'
import type { Chapter } from '../../../../types'
import type { Editor } from '@tiptap/react'

export function useWritingSession(chapter: Chapter, editor: Editor | null) {
  const sessionStartWords = useRef(chapter.word_count)
  const sessionStartTime = useRef(Date.now())
  const [sessionDelta, setSessionDelta] = useState(0)
  const [sessionElapsed, setSessionElapsed] = useState(0)

  const resetSession = () => {
    sessionStartWords.current = chapter.word_count
    sessionStartTime.current = Date.now()
    setSessionDelta(0)
    setSessionElapsed(0)
  }

  useEffect(() => {
    resetSession()
  }, [chapter.id])

  useEffect(() => {
    const t = setInterval(
      () => setSessionElapsed(Math.floor((Date.now() - sessionStartTime.current) / 1000)),
      15000,
    )
    return () => clearInterval(t)
  }, [])

  const onEditorWordCountChange = (current: number) => {
    setSessionDelta(current - sessionStartWords.current)
  }

  const elapsedMin = Math.floor(sessionElapsed / 60)
  const elapsedLabel = elapsedMin > 0 ? `${elapsedMin}m` : sessionElapsed > 0 ? `${sessionElapsed}s` : ''

  const wordCount = editor?.storage.characterCount?.characters() ?? chapter.word_count

  return {
    sessionDelta,
    sessionElapsed,
    elapsedLabel,
    wordCount,
    onEditorWordCountChange,
    resetSession,
  }
}

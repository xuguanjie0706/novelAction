/**
 * useChapterTiptapEditor — TipTap 实例、选区条、与自动保存节流联动
 */
import { useEffect, useState } from 'react'
import { useEditor } from '@tiptap/react'
import StarterKit from '@tiptap/starter-kit'
import CharacterCount from '@tiptap/extension-character-count'
import Placeholder from '@tiptap/extension-placeholder'
import type { Chapter } from '../../../../types'

interface UseChapterTiptapEditorOptions {
  chapter: Chapter
  /** 与 autosave 共用；外部写入正文时须清空，避免旧稿覆盖新稿 */
  saveTimerRef?: React.MutableRefObject<ReturnType<typeof setTimeout> | undefined>
  onAutoSave: (html: string) => void | Promise<void>
  onWordCountChange: (current: number) => void
}

export function useChapterTiptapEditor({
  chapter,
  saveTimerRef,
  onAutoSave,
  onWordCountChange,
}: UseChapterTiptapEditorOptions) {
  const chapterContentRev = `${chapter.id}:${chapter.updated_at ?? ''}:${chapter.content ?? ''}`
  const [selectionText, setSelectionText] = useState('')
  const [showSelectionBar, setShowSelectionBar] = useState(false)
  const [editorHtmlTick, setEditorHtmlTick] = useState(0)

  const editor = useEditor({
    extensions: [
      StarterKit,
      CharacterCount,
      Placeholder.configure({ placeholder: '从这里落笔，写下这一章的第一个句子……' }),
    ],
    content: chapter.content,
    editorProps: {
      attributes: {
        class: 'prose prose-lg max-w-readable w-full focus:outline-none min-h-[60vh] px-6 sm:px-10 py-8 mx-auto',
      },
    },
    onUpdate: ({ editor: ed }) => {
      if (saveTimerRef?.current) clearTimeout(saveTimerRef.current)
      if (saveTimerRef) saveTimerRef.current = setTimeout(() => void onAutoSave(ed.getHTML()), 2000)
      const current = ed.storage.characterCount?.characters() ?? 0
      onWordCountChange(current)
      setEditorHtmlTick(n => n + 1)
    },
    onSelectionUpdate: ({ editor: ed }) => {
      const { from, to } = ed.state.selection
      if (from === to) {
        setShowSelectionBar(false)
        setSelectionText('')
        return
      }
      const selected = ed.state.doc.textBetween(from, to, ' ').trim()
      if (selected.length >= 6) {
        setSelectionText(selected)
        setShowSelectionBar(true)
      } else {
        setShowSelectionBar(false)
      }
    },
  })

  useEffect(() => {
    if (!editor) return
    const incoming = chapter.content ?? ''
    if (incoming === editor.getHTML()) return
    if (saveTimerRef?.current) {
      clearTimeout(saveTimerRef.current)
      saveTimerRef.current = undefined
    }
    editor.commands.setContent(incoming, false)
  }, [chapterContentRev, editor, saveTimerRef])

  const resetSelectionUi = () => {
    setSelectionText('')
    setShowSelectionBar(false)
  }

  return {
    editor,
    selectionText,
    setSelectionText,
    showSelectionBar,
    setShowSelectionBar,
    editorHtmlTick,
    resetSelectionUi,
  }
}

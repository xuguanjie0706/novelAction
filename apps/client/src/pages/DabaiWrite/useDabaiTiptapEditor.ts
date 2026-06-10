/**
 * useDabaiTiptapEditor — 大白文写作页轻量 TipTap + 自动保存
 */
import { useEffect, useRef } from 'react'
import { useEditor } from '@tiptap/react'
import StarterKit from '@tiptap/starter-kit'
import CharacterCount from '@tiptap/extension-character-count'
import Placeholder from '@tiptap/extension-placeholder'
import toast from 'react-hot-toast'
import { chaptersApi } from '../../api/client'
import type { Chapter } from '../../types'

export function useDabaiTiptapEditor(
  projectId: string,
  chapter: Chapter | undefined,
  upsertChapter: (ch: Chapter) => void,
) {
  const saveTimerRef = useRef<ReturnType<typeof setTimeout>>()
  const chapterId = chapter?.id

  const editor = useEditor({
    extensions: [
      StarterKit,
      CharacterCount,
      Placeholder.configure({ placeholder: '正文将按左侧「章节要素」五拍生成；也可在此直接编辑…' }),
    ],
    content: chapter?.content ?? '',
    editorProps: {
      attributes: {
        class: 'prose prose-lg max-w-readable w-full focus:outline-none min-h-[50vh] px-6 py-6',
      },
    },
    onUpdate: ({ editor: ed }) => {
      if (saveTimerRef.current) clearTimeout(saveTimerRef.current)
      saveTimerRef.current = setTimeout(async () => {
        if (!chapterId) return
        try {
          const res = await chaptersApi.update(projectId, chapterId, { content: ed.getHTML() })
          upsertChapter(res.data)
        } catch {
          toast.error('自动保存失败')
        }
      }, 2000)
    },
  }, [chapterId])

  useEffect(() => {
    if (!editor || !chapter) return
    const html = chapter.content ?? ''
    if (html !== editor.getHTML()) editor.commands.setContent(html, false)
  }, [editor, chapter?.id, chapter?.updated_at, chapter?.content])

  const wordCount = editor?.storage.characterCount?.characters() ?? chapter?.word_count ?? 0

  return { editor, wordCount }
}

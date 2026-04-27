import React, { useEffect, useCallback, useRef } from 'react'
import { useEditor, EditorContent } from '@tiptap/react'
import StarterKit from '@tiptap/starter-kit'
import CharacterCount from '@tiptap/extension-character-count'
import Placeholder from '@tiptap/extension-placeholder'
import { chaptersApi } from '../../api/client'
import { useAppStore } from '../../store'
import type { Chapter } from '../../types'
import toast from 'react-hot-toast'

interface Props {
  projectId: string
  chapter: Chapter
}

export default function ChapterEditor({ projectId, chapter }: Props) {
  const { upsertChapter } = useAppStore()
  const saveTimer = useRef<ReturnType<typeof setTimeout>>()

  const editor = useEditor({
    extensions: [
      StarterKit,
      CharacterCount,
      Placeholder.configure({ placeholder: '开始写作……' }),
    ],
    content: chapter.content,
    editorProps: {
      attributes: {
        class: 'prose prose-lg max-w-none focus:outline-none min-h-[60vh] px-8 py-6',
      },
    },
    onUpdate: ({ editor }) => {
      // 自动保存（防抖 2s）
      clearTimeout(saveTimer.current)
      saveTimer.current = setTimeout(() => {
        autoSave(editor.getHTML())
      }, 2000)
    },
  })

  const autoSave = useCallback(async (content: string) => {
    try {
      const res = await chaptersApi.update(projectId, chapter.id, { content })
      upsertChapter(res.data)
    } catch {
      // 静默失败，下次再试
    }
  }, [projectId, chapter.id])

  const manualSave = async () => {
    if (!editor) return
    try {
      const content = editor.getHTML()
      const res = await chaptersApi.update(projectId, chapter.id, { content })
      upsertChapter(res.data)
      await chaptersApi.snapshot(projectId, chapter.id, '手动保存')
      toast.success('已保存')
    } catch {
      toast.error('保存失败')
    }
  }

  // 切换章节时同步内容
  useEffect(() => {
    if (editor && chapter.content !== editor.getHTML()) {
      editor.commands.setContent(chapter.content)
    }
  }, [chapter.id])

  const wordCount = editor?.storage.characterCount?.characters() ?? chapter.word_count

  return (
    <div className="flex flex-col h-full">
      {/* 章节标题栏 */}
      <div className="flex items-center justify-between px-8 py-3 border-b border-gray-100 bg-white shrink-0">
        <h2 className="font-semibold text-gray-800">{chapter.title}</h2>
        <div className="flex items-center gap-4">
          <span className="text-sm text-gray-400">{wordCount.toLocaleString()} 字</span>
          <button
            onClick={manualSave}
            className="text-sm px-3 py-1.5 bg-amber-500 hover:bg-amber-600 text-white rounded-lg transition-colors"
          >
            保存
          </button>
        </div>
      </div>

      {/* 编辑区 */}
      <div className="flex-1 overflow-auto bg-white">
        <EditorContent editor={editor} />
      </div>
    </div>
  )
}

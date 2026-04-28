import React, { useEffect, useCallback, useRef, useState } from 'react'
import { useEditor, EditorContent } from '@tiptap/react'
import StarterKit from '@tiptap/starter-kit'
import CharacterCount from '@tiptap/extension-character-count'
import Placeholder from '@tiptap/extension-placeholder'
import { chaptersApi } from '../../api/client'
import { useAppStore } from '../../store'
import type { Chapter, OutlineNode } from '../../types'
import toast from 'react-hot-toast'
import { BookOpen, Sparkles, X, Zap, Target, Users, Flag, GitBranch, RefreshCw } from 'lucide-react'
import clsx from 'clsx'

interface Props {
  projectId: string
  chapter: Chapter
  outlineNode?: OutlineNode
}

function escapeHtml(s: string) {
  return s.replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;')
}

/** 将 AI 返回的纯文本变成 TipTap 可用的 HTML 段落 */
function plainTextDraftToHtml(s: string) {
  const blocks = s.split(/\n{2,}/).map(b => b.trim()).filter(Boolean)
  if (blocks.length === 0) return '<p></p>'
  return blocks.map(b => `<p>${escapeHtml(b).replace(/\n/g, '<br>')}</p>`).join('')
}

function parseSseDataLine(line: string): { text?: string; error?: string; done?: boolean } | null {
  const t = line.trim()
  if (!t.startsWith('data:')) return null
  const raw = t.slice(5).trimStart()
  if (raw === '[DONE]') return { done: true }
  try {
    return JSON.parse(raw) as { text?: string; error?: string }
  } catch {
    return null
  }
}

export default function ChapterEditor({ projectId, chapter, outlineNode }: Props) {
  const { upsertChapter } = useAppStore()
  const saveTimer = useRef<ReturnType<typeof setTimeout>>()
  const [contextOpen, setContextOpen] = useState(!!outlineNode)
  const [aiDrafting, setAiDrafting] = useState(false)
  const [draftText, setDraftText] = useState('')
  const [showDraft, setShowDraft] = useState(false)
  const [aiExtraPrompt, setAiExtraPrompt] = useState('')
  const [autoInsertAfterDraft, setAutoInsertAfterDraft] = useState(true)

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
    onUpdate: ({ editor }) => {
      clearTimeout(saveTimer.current)
      saveTimer.current = setTimeout(() => autoSave(editor.getHTML()), 2000)
    },
  })

  const autoSave = useCallback(async (content: string) => {
    try {
      const res = await chaptersApi.update(projectId, chapter.id, { content })
      upsertChapter(res.data)
    } catch { /* 静默失败 */ }
  }, [projectId, chapter.id, upsertChapter])

  const manualSave = async () => {
    if (!editor) return
    try {
      const content = editor.getHTML()
      const res = await chaptersApi.update(projectId, chapter.id, { content })
      upsertChapter(res.data)
      await chaptersApi.snapshot(projectId, chapter.id, '手动保存')
      toast.success('已保存')
    } catch { toast.error('保存失败') }
  }

  useEffect(() => {
    if (!editor) return
    if (chapter.content !== editor.getHTML()) {
      editor.commands.setContent(chapter.content)
    }
  }, [chapter.id, chapter.content, editor])

  useEffect(() => {
    setShowDraft(false)
    setDraftText('')
    setAiDrafting(false)
  }, [chapter.id])

  useEffect(() => { setContextOpen(!!outlineNode) }, [outlineNode?.id])

  const insertDraftToEditorAndSave = useCallback(async (text: string, replace: boolean) => {
    if (!editor || !text.trim()) return
    const html = plainTextDraftToHtml(text.trim())
    if (replace) editor.commands.setContent(html)
    else editor.chain().focus().insertContentAt(editor.state.doc.content.size, html).run()
    const content = editor.getHTML()
    try {
      const res = await chaptersApi.update(projectId, chapter.id, { content })
      upsertChapter(res.data)
      toast.success(replace ? '已用新稿替换正文并保存' : '已插入正文并保存')
      setShowDraft(false)
      setDraftText('')
    } catch {
      toast.error('保存失败，请点顶部「保存」重试')
    }
  }, [editor, projectId, chapter.id, upsertChapter])

  const generateDraft = async (opts?: { replaceExisting?: boolean }) => {
    if (opts?.replaceExisting) {
      if (!window.confirm(
        '「重新生成本章」将按大纲重写：生成结果可替换当前编辑器中的全部正文。\n建议先手动保存或版本快照。确定继续？',
      )) return
    }
    setAiDrafting(true)
    setDraftText('')
    setShowDraft(true)
    let accumulated = ''
    try {
      const res = await fetch(`/api/v1/projects/${projectId}/ai/draft-assist/stream`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          chapter_id: chapter.id,
          model_profile: useAppStore.getState().aiModelProfile,
          user_prompt: aiExtraPrompt.trim() || null,
          replace_existing: !!opts?.replaceExisting,
        }),
      })
      if (!res.ok) {
        const errBody = await res.text().catch(() => '')
        throw new Error(errBody.slice(0, 240) || `请求失败 HTTP ${res.status}`)
      }
      if (!res.body) throw new Error('响应无流式内容')

      const reader = res.body.getReader()
      const dec = new TextDecoder()
      let buf = ''
      while (true) {
        const { done, value } = await reader.read()
        if (done) break
        buf += dec.decode(value, { stream: true })
        const lines = buf.split('\n')
        buf = lines.pop() ?? ''
        for (const line of lines) {
          const payload = parseSseDataLine(line)
          if (!payload) continue
          if (payload.done) break
          if (payload.error) throw new Error(payload.error)
          if (payload.text) {
            accumulated += payload.text
            setDraftText(accumulated)
          }
        }
      }
      for (const line of buf.split('\n')) {
        const payload = parseSseDataLine(line)
        if (!payload) continue
        if (payload.error) throw new Error(payload.error)
        if (payload.text) {
          accumulated += payload.text
          setDraftText(accumulated)
        }
      }

      if (!accumulated.trim()) {
        toast.error('未收到正文内容，请检查模型或稍后重试')
        return
      }
      toast.success('生成完成')
      if (autoInsertAfterDraft) {
        await insertDraftToEditorAndSave(accumulated, !!opts?.replaceExisting)
      }
    } catch (e: unknown) {
      const msg = e instanceof Error ? e.message : 'AI 生成失败'
      toast.error(msg)
    } finally {
      setAiDrafting(false)
    }
  }

  const applyDraftOnly = () => {
    if (!editor || !draftText.trim()) return
    void insertDraftToEditorAndSave(draftText, false)
  }

  const applyDraftReplace = () => {
    if (!editor || !draftText.trim()) return
    if (!window.confirm('用当前草稿替换编辑器中的全部正文？')) return
    void insertDraftToEditorAndSave(draftText, true)
  }

  const wordCount = editor?.storage.characterCount?.characters() ?? chapter.word_count
  const hasOutlineContent = outlineNode && (
    outlineNode.hook || outlineNode.summary || outlineNode.conflict || outlineNode.highlight
  )

  return (
    <div className="flex flex-col h-full bg-novel-shell/40">
      <div className="flex items-center justify-between px-6 sm:px-10 py-3 border-b border-novel-border bg-novel-raised/95 shrink-0">
        <h2 className="font-semibold text-novel-ink truncate max-w-lg">{chapter.title}</h2>
        <div className="flex items-center gap-3">
          <span className="text-sm text-novel-ink-muted">{wordCount.toLocaleString()} 字</span>
          {outlineNode && (
            <button type="button" onClick={() => setContextOpen(v => !v)}
              className={clsx('flex items-center gap-1.5 text-xs px-2.5 py-1.5 rounded-novel border transition-novel',
                contextOpen
                  ? 'bg-novel-panel border-novel-border text-novel-accent'
                  : 'border-novel-border text-novel-ink-muted hover:bg-novel-panel')}>
              <BookOpen size={12} />章节计划
            </button>
          )}
          <button type="button" onClick={manualSave}
            className="text-sm px-3 py-1.5 bg-novel-accent hover:bg-novel-accent-hover text-white rounded-novel transition-novel focus:outline-none focus-visible:ring-2 focus-visible:ring-novel-accent focus-visible:ring-offset-2">
            保存
          </button>
        </div>
      </div>

      <div className="flex flex-1 min-h-0">
        <div className="flex-1 overflow-auto flex flex-col min-h-0">
          <EditorContent editor={editor} className="flex-1" />

          {showDraft && (
            <div className="border-t border-amber-100 bg-amber-50/60 px-6 py-4 shrink-0">
              <div className="flex items-center justify-between mb-2 gap-2 flex-wrap">
                <div className="flex items-center gap-2">
                  <Sparkles size={13} className="text-amber-500" />
                  <span className="text-xs font-medium text-amber-800">
                    {aiDrafting ? 'AI 正在生成…' : 'AI 草稿预览'}
                  </span>
                  {aiDrafting && (
                    <span className="flex gap-0.5 ml-1">
                      {[0, 1, 2].map(i => (
                        <span key={i} className="w-1 h-1 rounded-full bg-amber-400 animate-bounce"
                          style={{ animationDelay: `${i * 0.15}s` }} />
                      ))}
                    </span>
                  )}
                </div>
                <div className="flex items-center gap-2 flex-wrap">
                  {!aiDrafting && draftText.trim() && (
                    <>
                      <button type="button" onClick={applyDraftOnly}
                        className="text-xs px-2.5 py-1 bg-amber-500 hover:bg-amber-600 text-white rounded-novel transition-novel">
                        插入文末并保存
                      </button>
                      <button type="button" onClick={applyDraftReplace}
                        className="text-xs px-2.5 py-1 border border-amber-400 text-amber-800 rounded-novel hover:bg-amber-100 transition-novel">
                        替换全文并保存
                      </button>
                      <button type="button" onClick={() => generateDraft()}
                        className="text-xs px-2.5 py-1 border border-amber-300 text-amber-700 rounded-novel hover:bg-amber-100 transition-novel">
                        重新生成
                      </button>
                    </>
                  )}
                  <button type="button" onClick={() => setShowDraft(false)} className="text-amber-400 hover:text-amber-600 p-1" title="关闭预览">
                    <X size={14} />
                  </button>
                </div>
              </div>
              <div className="text-sm text-gray-800 whitespace-pre-wrap max-h-52 overflow-auto leading-relaxed bg-white rounded-novel px-4 py-3 border border-amber-100">
                {draftText || <span className="text-gray-400 italic">{aiDrafting ? '等待首包…' : '（空）'}</span>}
              </div>
            </div>
          )}

          <div className="border-t border-novel-border bg-novel-panel/90 px-6 py-3 shrink-0 space-y-2">
            <label className="block text-[11px] font-medium text-novel-ink-muted">起笔 / 续写说明（可选）</label>
            <textarea
              value={aiExtraPrompt}
              onChange={e => setAiExtraPrompt(e.target.value)}
              rows={2}
              disabled={aiDrafting}
              placeholder="例如：偏压抑、少对话、突出某某伏笔；或重写时希望的开场氛围…"
              className="w-full text-xs border border-novel-border rounded-novel px-3 py-2 bg-novel-card text-novel-ink placeholder:text-novel-ink-faint focus:outline-none focus-visible:ring-1 focus-visible:ring-novel-accent resize-y min-h-[2.5rem] disabled:opacity-60"
            />
            <label className="flex items-center gap-2 text-[11px] text-novel-ink-muted cursor-pointer select-none">
              <input
                type="checkbox"
                checked={autoInsertAfterDraft}
                onChange={e => setAutoInsertAfterDraft(e.target.checked)}
                disabled={aiDrafting}
                className="rounded border-novel-border"
              />
              生成完成后自动写入正文并保存（续写插文末；「重新生成本章」为替换全文）
            </label>
            <div className="flex flex-wrap items-center gap-2">
              <button type="button" onClick={() => generateDraft()} disabled={aiDrafting}
                className="flex items-center gap-1.5 text-xs px-3 py-2 font-medium bg-novel-accent text-white rounded-novel hover:bg-novel-accent-hover disabled:opacity-60 transition-novel">
                <Sparkles size={13} className={aiDrafting ? 'animate-pulse' : ''} />
                {aiDrafting ? '生成中…' : chapter.word_count > 100 ? 'AI 续写' : 'AI 起笔'}
              </button>
              <button type="button" onClick={() => generateDraft({ replaceExisting: true })} disabled={aiDrafting}
                className="flex items-center gap-1.5 text-xs px-3 py-2 font-medium border border-red-200 text-red-700 bg-red-50/80 rounded-novel hover:bg-red-100 disabled:opacity-60 transition-novel">
                <RefreshCw size={13} />
                重新生成本章
              </button>
              <span className="text-[10px] text-novel-ink-faint">模型在顶部栏选择</span>
            </div>
          </div>
        </div>

        {contextOpen && outlineNode && (
          <div className="w-72 shrink-0 border-l border-novel-border bg-novel-panel flex flex-col overflow-hidden">
            <div className="flex items-center justify-between px-4 py-3 border-b border-novel-border bg-novel-card/80">
              <span className="text-xs font-semibold text-novel-ink-muted uppercase tracking-wider">章节计划</span>
              <button type="button" onClick={() => setContextOpen(false)} className="text-novel-ink-faint hover:text-novel-ink">
                <X size={14} />
              </button>
            </div>

            <div className="flex-1 overflow-auto p-4 space-y-3">
              {outlineNode.hook && (
                <PlanCard icon={<Zap size={12} className="text-amber-500" />}
                  label="开篇钩子" sublabel="第一句话的使命"
                  content={outlineNode.hook} accent="amber" />
              )}
              {outlineNode.summary && (
                <PlanCard icon={<Target size={12} className="text-blue-500" />}
                  label="核心事件" sublabel="删掉会损失什么"
                  content={outlineNode.summary} accent="blue" />
              )}
              {outlineNode.conflict && (
                <PlanCard icon={<Users size={12} className="text-purple-500" />}
                  label="人物变化" sublabel="不可逆的认知或处境转变"
                  content={outlineNode.conflict} accent="purple" />
              )}
              {outlineNode.highlight && (
                <PlanCard icon={<Flag size={12} className="text-red-500" />}
                  label="章末钩子" sublabel="让读者无法放下的最后一句"
                  content={outlineNode.highlight} accent="red" />
              )}
              {(outlineNode.extra as Record<string, string>)?.foreshadow && (
                <PlanCard icon={<GitBranch size={12} className="text-green-500" />}
                  label="伏笔管理" sublabel="埋[…] 收[…]"
                  content={(outlineNode.extra as Record<string, string>).foreshadow} accent="green" />
              )}
              {!hasOutlineContent && (
                <p className="text-xs text-novel-ink-faint text-center py-6 italic leading-relaxed">
                  大纲节点尚未填写计划细节，<br />可在「大纲」页选中本章节点后编辑
                </p>
              )}
            </div>

            <div className="px-4 pb-4 pt-3 border-t border-novel-border">
              <p className="text-[10px] text-novel-ink-faint text-center leading-relaxed">
                AI 生成与提示词在下方编辑区底部，此处仅查看计划
              </p>
            </div>
          </div>
        )}
      </div>
    </div>
  )
}

type AccentColor = 'amber' | 'blue' | 'purple' | 'red' | 'green'
const accentCls: Record<AccentColor, { border: string; label: string; bg: string }> = {
  amber:  { border: 'border-amber-100',  label: 'text-amber-700',  bg: 'bg-amber-50/70' },
  blue:   { border: 'border-blue-100',   label: 'text-blue-700',   bg: 'bg-blue-50/70' },
  purple: { border: 'border-purple-100', label: 'text-purple-700', bg: 'bg-purple-50/70' },
  red:    { border: 'border-red-100',    label: 'text-red-700',    bg: 'bg-red-50/70' },
  green:  { border: 'border-green-100',  label: 'text-green-700',  bg: 'bg-green-50/70' },
}

function PlanCard({ icon, label, sublabel, content, accent }: {
  icon: React.ReactNode; label: string; sublabel?: string; content: string; accent: AccentColor
}) {
  const c = accentCls[accent]
  return (
    <div className={clsx('rounded-novel border p-3', c.border, c.bg)}>
      <div className="flex items-center gap-1.5 mb-1.5">
        {icon}
        <span className={clsx('text-xs font-semibold', c.label)}>{label}</span>
        {sublabel && <span className="text-[10px] text-novel-ink-faint">{sublabel}</span>}
      </div>
      <p className="text-xs text-novel-ink leading-relaxed">{content}</p>
    </div>
  )
}

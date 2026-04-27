import React, { useEffect, useState } from 'react'
import { useParams } from 'react-router-dom'
import { Plus, Map } from 'lucide-react'
import { settingsApi } from '../api/client'
import { useAppStore } from '../store'
import type { WorldSetting } from '../types'
import clsx from 'clsx'
import toast from 'react-hot-toast'

// 根据标题推断分类图标
const CATEGORY_ICON: Record<string, string> = {
  '修炼': '⚡', '境界': '⚡', '体系': '⚡',
  '势力': '🏯', '宗门': '🏯', '门派': '🏯',
  '规则': '📜', '法则': '📜', '世界': '📜',
  '道具': '💎', '资源': '💎', '物品': '💎',
}

function getIcon(title: string) {
  for (const [key, icon] of Object.entries(CATEGORY_ICON)) {
    if (title.includes(key)) return icon
  }
  return '📋'
}

export default function SettingsPage() {
  const { projectId } = useParams<{ projectId: string }>()
  const { settings, setSettings, upsertSetting, removeSetting } = useAppStore()
  const [selected, setSelected] = useState<WorldSetting | null>(null)
  const [creating, setCreating] = useState(false)
  const [newTitle, setNewTitle] = useState('')

  useEffect(() => {
    if (!projectId) return
    settingsApi.list(projectId).then(res => {
      setSettings(res.data)
      if (res.data.length > 0) setSelected(res.data[0])
    })
  }, [projectId])

  const create = async () => {
    if (!newTitle.trim() || !projectId) return
    setCreating(true)
    try {
      const res = await settingsApi.create(projectId, { title: newTitle.trim(), content: '', tags: [] })
      upsertSetting(res.data)
      setSelected(res.data)
      setNewTitle('')
    } catch { toast.error('创建失败') }
    finally { setCreating(false) }
  }

  return (
    <div className="flex h-full">
      {/* 左栏：设定卡列表 */}
      <div className="w-56 border-r border-gray-100 bg-white flex flex-col shrink-0">
        <div className="flex items-center justify-between px-4 py-2.5 border-b border-gray-100 shrink-0">
          <span className="text-xs font-semibold text-gray-500 uppercase tracking-wider">设定卡</span>
          <span className="text-xs text-gray-400">{settings.length} 张</span>
        </div>

        <div className="flex-1 overflow-auto py-2">
          {settings.map(s => (
            <button
              key={s.id}
              onClick={() => setSelected(s)}
              className={clsx(
                'w-full flex items-center gap-3 px-4 py-2.5 text-left transition-colors border-l-2',
                selected?.id === s.id
                  ? 'bg-amber-50 border-l-amber-400'
                  : 'border-l-transparent hover:bg-gray-50'
              )}
            >
              <span className="text-xl shrink-0">{getIcon(s.title)}</span>
              <div className="min-w-0">
                <div className="text-sm font-medium text-gray-800 truncate">{s.title}</div>
                {s.tags.length > 0 && (
                  <div className="text-xs text-gray-400 truncate">{s.tags.join(' · ')}</div>
                )}
              </div>
            </button>
          ))}
          {settings.length === 0 && (
            <p className="text-xs text-gray-400 text-center py-8 px-4">暂无设定卡</p>
          )}
        </div>

        {/* 新建输入 */}
        <div className="border-t border-gray-100 p-3 shrink-0">
          <div className="flex gap-1.5">
            <input
              value={newTitle}
              onChange={e => setNewTitle(e.target.value)}
              onKeyDown={e => e.key === 'Enter' && create()}
              placeholder="新设定卡标题..."
              className="flex-1 border border-gray-200 rounded-lg px-2 py-1.5 text-xs focus:outline-none focus:ring-1 focus:ring-amber-400"
            />
            <button
              onClick={create}
              disabled={creating || !newTitle.trim()}
              className="px-2 py-1.5 bg-amber-500 hover:bg-amber-600 disabled:opacity-40 text-white rounded-lg"
            >
              <Plus size={13} />
            </button>
          </div>
        </div>
      </div>

      {/* 右栏：设定卡详情 */}
      <div className="flex-1 overflow-auto bg-[#FAF8F4]">
        {selected
          ? <SettingDetail setting={selected} projectId={projectId!} onUpdate={upsertSetting} />
          : <div className="flex items-center justify-center h-full text-gray-400 text-sm">选择左侧设定卡查看详情</div>
        }
      </div>
    </div>
  )
}

function SettingDetail({ setting, projectId, onUpdate }: {
  setting: WorldSetting
  projectId: string
  onUpdate: (s: WorldSetting) => void
}) {
  const [form, setForm] = useState({ title: setting.title, content: setting.content ?? '', tags: setting.tags })
  const [saving, setSaving] = useState(false)
  const [tagInput, setTagInput] = useState('')

  // 切换 setting 时同步
  useEffect(() => {
    setForm({ title: setting.title, content: setting.content ?? '', tags: setting.tags })
  }, [setting.id])

  const save = async () => {
    setSaving(true)
    try {
      const res = await settingsApi.update(projectId, setting.id, form)
      onUpdate(res.data)
      toast.success('已保存')
    } catch { toast.error('保存失败') }
    finally { setSaving(false) }
  }

  const addTag = () => {
    const t = tagInput.trim()
    if (!t || form.tags.includes(t)) return
    setForm(f => ({ ...f, tags: [...f.tags, t] }))
    setTagInput('')
  }
  const removeTag = (t: string) => setForm(f => ({ ...f, tags: f.tags.filter(x => x !== t) }))

  return (
    <div className="max-w-2xl mx-auto p-6 space-y-4">
      {/* 标题栏 */}
      <div className="bg-white rounded-xl p-5 border border-gray-100 shadow-sm flex items-center gap-3">
        <span className="text-3xl">{getIcon(setting.title)}</span>
        <input
          value={form.title}
          onChange={e => setForm(f => ({ ...f, title: e.target.value }))}
          className="flex-1 text-xl font-bold text-gray-900 border-none outline-none bg-transparent"
        />
      </div>

      {/* 标签 */}
      <div className="bg-white rounded-xl p-4 border border-gray-100 shadow-sm">
        <div className="text-xs font-semibold text-gray-500 mb-2">标签</div>
        <div className="flex flex-wrap gap-2 mb-3">
          {form.tags.map(t => (
            <span key={t} className="flex items-center gap-1 text-xs px-2 py-1 bg-amber-50 text-amber-700 rounded-full border border-amber-200">
              {t}
              <button onClick={() => removeTag(t)} className="text-amber-400 hover:text-amber-700 leading-none">×</button>
            </span>
          ))}
        </div>
        <div className="flex gap-2">
          <input
            value={tagInput}
            onChange={e => setTagInput(e.target.value)}
            onKeyDown={e => e.key === 'Enter' && addTag()}
            placeholder="添加标签..."
            className="border border-gray-200 rounded-lg px-2 py-1 text-xs focus:outline-none focus:ring-1 focus:ring-amber-400 w-32"
          />
          <button onClick={addTag} className="text-xs text-amber-600 hover:text-amber-700">添加</button>
        </div>
      </div>

      {/* 内容 */}
      <div className="bg-white rounded-xl p-5 border border-gray-100 shadow-sm">
        <div className="text-xs font-semibold text-gray-500 mb-2">详细描述</div>
        <textarea
          value={form.content}
          onChange={e => setForm(f => ({ ...f, content: e.target.value }))}
          rows={12}
          className="w-full border border-gray-200 rounded-lg px-3 py-2 text-sm focus:outline-none focus:ring-1 focus:ring-amber-400 resize-none leading-relaxed"
          placeholder="在这里记录详细的设定描述..."
        />
        <button
          onClick={save}
          disabled={saving}
          className="mt-3 px-4 py-2 bg-amber-500 hover:bg-amber-600 disabled:opacity-50 text-white text-sm rounded-lg transition-colors"
        >
          {saving ? '保存中...' : '保存修改'}
        </button>
      </div>
    </div>
  )
}

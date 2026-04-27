import React, { useEffect, useState } from 'react'
import { useParams } from 'react-router-dom'
import { Plus, User, Shield, Swords, Crown } from 'lucide-react'
import { charactersApi } from '../api/client'
import { useAppStore } from '../store'
import type { Character } from '../types'
import clsx from 'clsx'
import toast from 'react-hot-toast'

const ROLE_META = {
  protagonist: { label: '主角', color: 'bg-amber-100 text-amber-700 border-amber-200', Icon: Crown },
  supporting:  { label: '配角', color: 'bg-blue-100 text-blue-700 border-blue-200',   Icon: User  },
  antagonist:  { label: '反派', color: 'bg-red-100 text-red-700 border-red-200',       Icon: Swords},
} as const

export default function CharactersPage() {
  const { projectId } = useParams<{ projectId: string }>()
  const { characters, setCharacters, upsertCharacter } = useAppStore()
  const [selected, setSelected] = useState<Character | null>(null)
  const [editing, setEditing] = useState(false)

  useEffect(() => {
    if (!projectId) return
    charactersApi.list(projectId).then(res => {
      setCharacters(res.data)
      if (res.data.length > 0) setSelected(res.data[0])
    })
  }, [projectId])

  const protagonist = characters.find(c => c.role === 'protagonist')
  const supporting  = characters.filter(c => c.role === 'supporting')
  const antagonists = characters.filter(c => c.role === 'antagonist')
  const groups = [
    { key: 'protagonist', chars: protagonist ? [protagonist] : [] },
    { key: 'supporting',  chars: supporting },
    { key: 'antagonist',  chars: antagonists },
  ] as const

  return (
    <div className="flex h-full">
      {/* 左栏：人物列表 */}
      <div className="w-56 border-r border-gray-100 bg-white flex flex-col shrink-0 overflow-auto">
        <div className="flex items-center justify-between px-4 py-2.5 border-b border-gray-100 shrink-0">
          <span className="text-xs font-semibold text-gray-500 uppercase tracking-wider">人物库</span>
          <span className="text-xs text-gray-400">{characters.length} 人</span>
        </div>

        <div className="flex-1 overflow-auto py-2">
          {groups.map(({ key, chars }) => chars.length > 0 && (
            <div key={key} className="mb-2">
              <div className="px-4 py-1">
                <span className={clsx('text-xs font-semibold px-2 py-0.5 rounded-full border', ROLE_META[key].color)}>
                  {ROLE_META[key].label}
                </span>
              </div>
              {chars.map(c => (
                <button
                  key={c.id}
                  onClick={() => { setSelected(c); setEditing(false) }}
                  className={clsx(
                    'w-full flex items-center gap-3 px-4 py-2.5 text-left transition-colors border-l-2',
                    selected?.id === c.id
                      ? 'bg-amber-50 border-l-amber-400'
                      : 'border-l-transparent hover:bg-gray-50'
                  )}
                >
                  <div className="w-8 h-8 rounded-full bg-gradient-to-br from-amber-200 to-amber-400 flex items-center justify-center shrink-0">
                    <span className="text-white text-xs font-bold">{c.name[0]}</span>
                  </div>
                  <div className="min-w-0">
                    <div className="text-sm font-medium text-gray-800 truncate">{c.name}</div>
                    <div className="text-xs text-gray-400 truncate">{c.faction ?? c.gender ?? ''}</div>
                  </div>
                </button>
              ))}
            </div>
          ))}
          {characters.length === 0 && (
            <p className="text-xs text-gray-400 text-center py-8 px-4">暂无人物，可通过 AI 生成或手动创建</p>
          )}
        </div>
      </div>

      {/* 右栏：人物详情 */}
      <div className="flex-1 overflow-auto bg-[#FAF8F4]">
        {selected
          ? <CharacterDetail char={selected} projectId={projectId!} onUpdate={upsertCharacter} />
          : <div className="flex items-center justify-center h-full text-gray-400 text-sm">选择左侧人物查看详情</div>
        }
      </div>
    </div>
  )
}

function CharacterDetail({ char, projectId, onUpdate }: {
  char: Character
  projectId: string
  onUpdate: (c: Character) => void
}) {
  const [form, setForm] = useState({ ...char })
  const [saving, setSaving] = useState(false)
  const meta = ROLE_META[char.role] ?? ROLE_META.supporting

  const save = async () => {
    setSaving(true)
    try {
      const res = await charactersApi.update(projectId, char.id, form)
      onUpdate(res.data)
      toast.success('已保存')
    } catch {
      toast.error('保存失败')
    } finally {
      setSaving(false)
    }
  }

  const field = (label: string, key: keyof typeof form, multiline = false) => (
    <div key={key}>
      <label className="text-xs font-medium text-gray-500 block mb-1">{label}</label>
      {multiline ? (
        <textarea
          value={(form[key] as string) ?? ''}
          onChange={e => setForm(f => ({ ...f, [key]: e.target.value }))}
          rows={3}
          className="w-full border border-gray-200 rounded-lg px-3 py-2 text-sm bg-white focus:outline-none focus:ring-1 focus:ring-amber-400 resize-none"
        />
      ) : (
        <input
          value={(form[key] as string) ?? ''}
          onChange={e => setForm(f => ({ ...f, [key]: e.target.value }))}
          className="w-full border border-gray-200 rounded-lg px-3 py-2 text-sm bg-white focus:outline-none focus:ring-1 focus:ring-amber-400"
        />
      )}
    </div>
  )

  return (
    <div className="max-w-2xl mx-auto p-6 space-y-5">
      {/* 人物头部 */}
      <div className="bg-white rounded-xl p-5 flex items-center gap-4 shadow-sm border border-gray-100">
        <div className="w-16 h-16 rounded-full bg-gradient-to-br from-amber-300 to-amber-500 flex items-center justify-center shrink-0">
          <span className="text-white text-2xl font-bold">{char.name[0]}</span>
        </div>
        <div className="flex-1">
          <div className="flex items-center gap-2 mb-1">
            <h2 className="text-xl font-bold text-gray-900">{char.name}</h2>
            <span className={clsx('text-xs px-2 py-0.5 rounded-full border font-medium', meta.color)}>
              {meta.label}
            </span>
          </div>
          <div className="text-sm text-gray-500 flex gap-3">
            {char.gender && <span>{char.gender}</span>}
            {char.age && <span>{char.age}岁</span>}
            {char.faction && <span className="text-amber-600">⚔ {char.faction}</span>}
          </div>
        </div>
      </div>

      {/* 标签列 */}
      {(char.special_traits?.length > 0 || char.strengths?.length > 0) && (
        <div className="bg-white rounded-xl p-4 border border-gray-100 shadow-sm">
          <div className="text-xs font-semibold text-gray-500 mb-2">特征标签</div>
          <div className="flex flex-wrap gap-2">
            {char.special_traits?.map(t => (
              <span key={t} className="text-xs px-2 py-1 bg-amber-50 text-amber-700 rounded-full border border-amber-200">{t}</span>
            ))}
            {char.strengths?.map(t => (
              <span key={t} className="text-xs px-2 py-1 bg-green-50 text-green-700 rounded-full border border-green-200">{t}</span>
            ))}
            {char.weaknesses?.map(t => (
              <span key={t} className="text-xs px-2 py-1 bg-red-50 text-red-600 rounded-full border border-red-200">{t}</span>
            ))}
          </div>
        </div>
      )}

      {/* 编辑表单 */}
      <div className="bg-white rounded-xl p-5 border border-gray-100 shadow-sm space-y-4">
        <div className="text-sm font-semibold text-gray-700">人物设定</div>
        {field('性格', 'personality', true)}
        {field('背景经历', 'background', true)}
        {field('核心动机', 'motivation', true)}
        {field('人物弧线（成长轨迹）', 'arc', true)}
        <button
          onClick={save}
          disabled={saving}
          className="px-4 py-2 bg-amber-500 hover:bg-amber-600 disabled:opacity-50 text-white text-sm rounded-lg transition-colors"
        >
          {saving ? '保存中...' : '保存修改'}
        </button>
      </div>
    </div>
  )
}

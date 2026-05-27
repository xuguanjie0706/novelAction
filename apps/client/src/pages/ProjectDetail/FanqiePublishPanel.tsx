/**
 * FanqiePublishPanel — 书架详情页「发布到番茄」
 *
 * 依赖后端 /api/v1/fanqie/* 代理；凭据通过 ConnectModal 配置。
 */
import React, { useCallback, useEffect, useState } from 'react'
import { Flame, ImagePlus, Loader2, Upload } from 'lucide-react'
import toast from 'react-hot-toast'
import type { Project } from '../../types'
import {
  getFanqieConfigSummary,
  publishProjectToFanqie,
  saveFanqieConfig,
  uploadFanqieCover,
} from '../../api/fanqieApi'
import type { FanqieConfig, FanqieConfigSummary, FanqiePublishResponse } from '../../api/fanqieApi'
import ConnectModal from '../FanqiePage/ConnectModal'

interface Props {
  project: Project
}

const DEFAULT_CATEGORY = '257,758,856,868'
const FANQIE_BOOK_NAME_MAX = 15

export default function FanqiePublishPanel({ project }: Props) {
  const [summary, setSummary] = useState<FanqieConfigSummary | null>(null)
  const [connectOpen, setConnectOpen] = useState(false)
  const [publishing, setPublishing] = useState(false)
  const [result, setResult] = useState<FanqiePublishResponse | null>(null)

  const [mode, setMode] = useState<'create' | 'existing'>('create')
  const [bookName, setBookName] = useState(project.title ?? '')
  const [bookId, setBookId] = useState('')
  const [category, setCategory] = useState(DEFAULT_CATEGORY)
  const [gender, setGender] = useState(1)
  const [thumbUri, setThumbUri] = useState('')
  const [rolesText, setRolesText] = useState('')
  const [freshCreateCurl, setFreshCreateCurl] = useState('')
  const [uploadCover, setUploadCover] = useState(true)
  const [coverUploading, setCoverUploading] = useState(false)
  const coverInputRef = React.useRef<HTMLInputElement>(null)

  const savedFanqieBookId =
    typeof project.extra === 'object' && project.extra && 'fanqie_book_id' in project.extra
      ? String((project.extra as Record<string, unknown>).fanqie_book_id ?? '')
      : ''

  const refreshConfig = useCallback(() => {
    getFanqieConfigSummary()
      .then(setSummary)
      .catch(() => setSummary({ configured: false }))
  }, [])

  useEffect(() => {
    refreshConfig()
  }, [refreshConfig])

  useEffect(() => {
    setBookName(project.title ?? '')
  }, [project.id, project.title])

  useEffect(() => {
    if (savedFanqieBookId) {
      setBookId(savedFanqieBookId)
      setMode('existing')
    }
  }, [savedFanqieBookId])

  async function handleSaveConfig(cfg: FanqieConfig) {
    await saveFanqieConfig(cfg)
    toast.success('番茄凭据已保存')
    refreshConfig()
  }

  async function handleUploadCover(file: File) {
    if (!summary?.configured) {
      setConnectOpen(true)
      toast('请先连接番茄作家账号')
      return
    }
    setCoverUploading(true)
    try {
      const { thumb_uri } = await uploadFanqieCover(file, {
        freshCurl: freshCreateCurl.trim() || undefined,
      })
      setThumbUri(thumb_uri)
      toast.success(`封面已上传：${thumb_uri}`)
    } catch (e: unknown) {
      const err = e as Error
      toast.error(err.message ?? '封面上传失败')
    } finally {
      setCoverUploading(false)
    }
  }

  async function handlePublish() {
    if (!summary?.configured) {
      setConnectOpen(true)
      toast('请先连接番茄作家账号')
      return
    }
    if (mode === 'existing' && !bookId.trim()) {
      toast.error('请填写番茄书籍 ID')
      return
    }
    if (mode === 'create' && !freshCreateCurl.trim()) {
      toast.error('请粘贴 book/create 或 upload_pic cURL（含 msToken、a_bogus）')
      return
    }
    if (mode === 'create' && !bookName.trim()) {
      toast.error('请填写番茄书名')
      return
    }
    if (mode === 'create' && !thumbUri.trim() && !uploadCover) {
      toast.error('请上传封面到番茄，或勾选自动上传项目封面')
      return
    }

    setPublishing(true)
    setResult(null)
    try {
      const roles = rolesText
        .split(/[,，、]/)
        .map(s => s.trim())
        .filter(Boolean)

      const res = await publishProjectToFanqie(project.id, {
        mode,
        book_id: mode === 'existing' ? bookId.trim() : undefined,
        book_name: mode === 'create' ? bookName.trim() : undefined,
        category,
        gender,
        roles: roles.length ? roles : undefined,
        thumb_uri: thumbUri.trim() || undefined,
        fresh_create_curl: mode === 'create' ? freshCreateCurl.trim() || undefined : undefined,
        upload_cover: mode === 'create' ? uploadCover : undefined,
        delay_seconds: 1.5,
      })
      setResult(res)
      const ok = res.uploaded.length
      const fail = res.failed.length
      if (fail === 0) {
        toast.success(`已上传 ${ok} 章到番茄草稿箱`)
      } else {
        toast(`完成：成功 ${ok} 章，失败 ${fail} 章`, { icon: '⚠️' })
      }
    } catch (e: unknown) {
      const err = e as { response?: { data?: { detail?: string } }; message?: string }
      toast.error(err?.response?.data?.detail ?? err?.message ?? '发布失败')
    } finally {
      setPublishing(false)
    }
  }

  const configured = summary?.configured ?? false

  return (
    <section className="mt-8 rounded-2xl border border-red-100 bg-gradient-to-br from-red-50/80 to-orange-50/50 p-6">
      <ConnectModal
        open={connectOpen}
        summary={summary}
        onClose={() => setConnectOpen(false)}
        onSave={handleSaveConfig}
      />

      <div className="flex flex-wrap items-start justify-between gap-4">
        <div className="flex items-center gap-2">
          <Flame size={20} className="text-red-500" fill="currentColor" />
          <h2 className="text-lg font-bold text-gray-900">发布到番茄小说</h2>
        </div>
        {!configured && (
          <button
            type="button"
            onClick={() => setConnectOpen(true)}
            className="rounded-lg border border-red-200 bg-white px-4 py-2 text-sm font-medium text-red-600 hover:bg-red-50"
          >
            连接番茄账号
          </button>
        )}
      </div>

      <p className="mt-2 text-sm leading-relaxed text-gray-600">
        在后端代理你的作家 Cookie，创建番茄新书并批量上传章节草稿。
        创建书籍需粘贴含 <strong>msToken、a_bogus</strong> 的 cURL（book/create 或 upload_pic）；封面须先上传得到 thumb_uri，否则易报 code=-2 参数有误。
      </p>

      {configured && (
        <div className="mt-5 space-y-4">
          <div className="flex flex-wrap gap-4">
            <label className="flex items-center gap-2 text-sm">
              <input
                type="radio"
                checked={mode === 'create'}
                onChange={() => setMode('create')}
              />
              在番茄创建新书
            </label>
            <label className="flex items-center gap-2 text-sm">
              <input
                type="radio"
                checked={mode === 'existing'}
                onChange={() => setMode('existing')}
              />
              上传到已有书籍
            </label>
          </div>

          {mode === 'existing' && (
            <div>
              <label className="mb-1 block text-xs font-medium text-gray-700">番茄书籍 ID</label>
              <input
                value={bookId}
                onChange={e => setBookId(e.target.value)}
                placeholder="7610780431444610073"
                className="w-full max-w-md rounded-lg border border-gray-200 bg-white px-3 py-2 text-sm"
              />
            </div>
          )}

          {mode === 'create' && (
            <div className="grid gap-3 sm:grid-cols-2">
              <div className="sm:col-span-2">
                <label className="mb-1 block text-xs font-medium text-gray-700">
                  番茄书名
                  <span className="ml-1 font-normal text-gray-400">
                    （最多 {FANQIE_BOOK_NAME_MAX} 字，超出将自动截断）
                  </span>
                </label>
                <input
                  value={bookName}
                  onChange={e => setBookName(e.target.value)}
                  maxLength={60}
                  placeholder={project.title}
                  className="w-full max-w-md rounded-lg border border-gray-200 bg-white px-3 py-2 text-sm"
                />
                {bookName.length > FANQIE_BOOK_NAME_MAX && (
                  <p className="mt-1 text-xs text-amber-600">
                    当前 {bookName.length} 字，发布时将截为前 {FANQIE_BOOK_NAME_MAX} 字
                  </p>
                )}
              </div>
              <div className="sm:col-span-2">
                <label className="mb-1 block text-xs font-medium text-gray-700">
                  cURL（必填，book/create 或 upload_pic，含 msToken、a_bogus）
                </label>
                <textarea
                  value={freshCreateCurl}
                  onChange={e => setFreshCreateCurl(e.target.value)}
                  rows={3}
                  placeholder="curl 'https://fanqienovel.com/api/author/data/upload_pic_v1/v0?msToken=...&a_bogus=...' ..."
                  className="w-full resize-none rounded-lg border border-gray-200 bg-white px-3 py-2 text-xs font-mono text-gray-800"
                />
              </div>
              <div className="sm:col-span-2">
                <label className="mb-2 block text-xs font-medium text-gray-700">封面上传（推荐，解决 code=-2）</label>
                <input
                  ref={coverInputRef}
                  type="file"
                  accept="image/png,image/jpeg,image/webp,image/gif"
                  className="hidden"
                  onChange={e => {
                    const f = e.target.files?.[0]
                    if (f) void handleUploadCover(f)
                    e.target.value = ''
                  }}
                />
                <div className="flex flex-wrap items-center gap-3">
                  <button
                    type="button"
                    disabled={coverUploading}
                    onClick={() => coverInputRef.current?.click()}
                    className="flex items-center gap-2 rounded-lg border border-red-200 bg-white px-4 py-2 text-sm font-medium text-red-600 hover:bg-red-50 disabled:opacity-50"
                  >
                    {coverUploading ? (
                      <Loader2 size={15} className="animate-spin" />
                    ) : (
                      <ImagePlus size={15} />
                    )}
                    {coverUploading ? '上传中…' : '选择图片并上传到番茄'}
                  </button>
                  {thumbUri && (
                    <span className="text-xs font-mono text-emerald-700">已就绪：{thumbUri}</span>
                  )}
                </div>
              </div>
              <div>
                <label className="mb-1 block text-xs font-medium text-gray-700">分类 ID（逗号分隔）</label>
                <input
                  value={category}
                  onChange={e => setCategory(e.target.value)}
                  className="w-full rounded-lg border border-gray-200 bg-white px-3 py-2 text-sm font-mono"
                />
              </div>
              <div>
                <label className="mb-1 block text-xs font-medium text-gray-700">频道</label>
                <select
                  value={gender}
                  onChange={e => setGender(Number(e.target.value))}
                  className="w-full rounded-lg border border-gray-200 bg-white px-3 py-2 text-sm"
                >
                  <option value={1}>男频</option>
                  <option value={2}>女频</option>
                </select>
              </div>
              <div className="sm:col-span-2">
                <label className="mb-1 block text-xs font-medium text-gray-700">主角名（可选，逗号分隔；留空用角色表前两名）</label>
                <input
                  value={rolesText}
                  onChange={e => setRolesText(e.target.value)}
                  placeholder="发达撒,发达"
                  className="w-full rounded-lg border border-gray-200 bg-white px-3 py-2 text-sm"
                />
              </div>
              <div className="sm:col-span-2">
                <label className="mb-1 flex items-center gap-2 text-xs font-medium text-gray-700">
                  <input
                    type="checkbox"
                    checked={uploadCover}
                    onChange={e => setUploadCover(e.target.checked)}
                  />
                  自动上传本项目封面（无封面则跳过；也可下方手动填 thumb_uri）
                </label>
              </div>
              <div className="sm:col-span-2">
                <label className="mb-1 block text-xs font-medium text-gray-700">
                  thumb_uri（上传后自动填入，也可手贴 novel-pic-r/…）
                </label>
                <input
                  value={thumbUri}
                  onChange={e => setThumbUri(e.target.value)}
                  placeholder="novel-pic-r/eee3a61c056ff0d0c55308ef3ea03b4f"
                  className="w-full rounded-lg border border-gray-200 bg-white px-3 py-2 text-sm font-mono"
                />
              </div>
            </div>
          )}

          <div className="flex flex-wrap items-center gap-3">
            <button
              type="button"
              disabled={publishing}
              onClick={handlePublish}
              className="flex items-center gap-2 rounded-xl bg-red-500 px-6 py-3 text-sm font-semibold text-white shadow-sm transition-colors hover:bg-red-600 disabled:opacity-50"
            >
              {publishing ? (
                <Loader2 size={16} className="animate-spin" />
              ) : (
                <Upload size={16} />
              )}
              {publishing ? '上传中…' : mode === 'create' ? '创建并上传章节' : '上传章节到草稿箱'}
            </button>
            <button
              type="button"
              onClick={() => setConnectOpen(true)}
              className="text-xs text-gray-500 underline hover:text-gray-700"
            >
              更新凭据 / cURL
            </button>
          </div>
        </div>
      )}

      {result && (
        <div className="mt-4 rounded-xl border border-gray-200 bg-white/90 p-4 text-sm">
          <p className="font-medium text-gray-800">
            番茄书籍 ID：<span className="font-mono text-red-600">{result.book_id}</span>
            {result.created && <span className="ml-2 text-xs text-emerald-600">（新书已创建）</span>}
            {result.cover_uploaded && (
              <span className="ml-2 text-xs text-blue-600">（封面已上传）</span>
            )}
          </p>
          {result.thumb_uri && (
            <p className="mt-1 text-xs font-mono text-gray-500">thumb_uri: {result.thumb_uri}</p>
          )}
          <p className="mt-1 text-gray-600">
            成功 {result.uploaded.length} 章
            {result.failed.length > 0 && `，失败 ${result.failed.length} 章`}
          </p>
          {result.failed.length > 0 && (
            <ul className="mt-2 max-h-32 overflow-y-auto text-xs text-red-600">
              {result.failed.map(f => (
                <li key={f.chapter_id}>{f.title}: {f.message}</li>
              ))}
            </ul>
          )}
        </div>
      )}
    </section>
  )
}

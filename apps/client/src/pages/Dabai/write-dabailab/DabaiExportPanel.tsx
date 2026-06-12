/**
 * dabai 实验书架 — 导出面板（对齐精品文 ExportPanel，无违禁词扫描）。
 */
import { useCallback, useEffect, useState } from 'react'
import {
  X, FileText, ListTree, Package, Loader2, CheckCircle2, AlertTriangle, Info,
} from 'lucide-react'
import toast from 'react-hot-toast'
import { dabaiApi } from '../../../api/dabai'
import type { DabaiExportPreview } from '../../../types/dabai'

interface Props {
  projectId: string
  onClose: () => void
}

type DownloadKind = 'txt' | 'outline' | 'package'

export default function DabaiExportPanel({ projectId, onClose }: Props) {
  const [platform, setPlatform] = useState('general')
  const [preview, setPreview] = useState<DabaiExportPreview | null>(null)
  const [loading, setLoading] = useState(true)
  const [downloading, setDownloading] = useState<DownloadKind | null>(null)

  const loadPreview = useCallback(async (plat: string) => {
    setLoading(true)
    try {
      const res = await dabaiApi.exportPreview(projectId, plat)
      setPreview(res.data)
    } catch {
      toast.error('获取导出预览失败')
    } finally {
      setLoading(false)
    }
  }, [projectId])

  useEffect(() => { void loadPreview(platform) }, [loadPreview, platform])

  const download = async (type: DownloadKind) => {
    setDownloading(type)
    try {
      await dabaiApi.downloadExport(projectId, type)
    } catch (e) {
      toast.error(e instanceof Error ? e.message : '下载失败')
    } finally {
      setDownloading(null)
    }
  }

  const writtenCount = preview
    ? preview.total_chapters - preview.issues.filter(i => i.status === 'empty').length
    : 0

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/40 p-4">
      <div className="flex max-h-[90vh] w-full max-w-lg flex-col overflow-hidden rounded-2xl bg-white shadow-xl">
        <div className="flex shrink-0 items-center justify-between border-b border-gray-100 px-6 py-4">
          <div>
            <h2 className="text-base font-semibold text-gray-800">导出正文</h2>
            <p className="mt-0.5 text-xs text-gray-400">下载已完成章节，空章自动跳过</p>
          </div>
          <button type="button" onClick={onClose} className="rounded-lg p-1.5 text-gray-400 hover:bg-gray-100">
            <X size={18} />
          </button>
        </div>

        <div className="flex-1 space-y-4 overflow-y-auto px-6 py-4">
          <section>
            <label className="mb-1.5 block text-xs font-medium text-gray-500">目标平台（字数预检）</label>
            <select
              value={platform}
              onChange={e => setPlatform(e.target.value)}
              className="w-full rounded-lg border border-gray-200 px-3 py-2 text-sm text-gray-700 focus:border-amber-400 focus:outline-none"
            >
              {Object.entries(preview?.platforms ?? {}).map(([key, rule]) => (
                <option key={key} value={key}>{rule.name}</option>
              ))}
            </select>
          </section>

          <section className="rounded-xl border border-gray-100 bg-gray-50 p-4">
            {loading ? (
              <div className="flex items-center gap-2 text-sm text-gray-400">
                <Loader2 size={16} className="animate-spin" />
                统计中…
              </div>
            ) : preview ? (
              <div className="space-y-3">
                <div className="grid grid-cols-3 gap-3 text-center">
                  <div>
                    <p className="text-lg font-semibold text-gray-800">{writtenCount}</p>
                    <p className="text-[10px] text-gray-400">已写章节</p>
                  </div>
                  <div>
                    <p className="text-lg font-semibold text-gray-800">{preview.total_chapters}</p>
                    <p className="text-[10px] text-gray-400">章纲总数</p>
                  </div>
                  <div>
                    <p className="text-lg font-semibold text-amber-600">{preview.total_words.toLocaleString()}</p>
                    <p className="text-[10px] text-gray-400">总字数</p>
                  </div>
                </div>
                {preview.compliant_chapters > 0 ? (
                  <p className="flex items-center gap-1.5 text-xs text-green-600">
                    <CheckCircle2 size={13} />
                    {preview.compliant_chapters} 章符合 {preview.platform_name} 字数要求
                  </p>
                ) : (
                  <p className="flex items-center gap-1.5 text-xs text-amber-600">
                    <AlertTriangle size={13} />
                    暂无符合平台字数要求的章节
                  </p>
                )}
                {preview.issues.filter(i => i.status === 'empty').length > 0 && (
                  <p className="flex items-center gap-1.5 text-[11px] text-gray-400">
                    <Info size={12} />
                    {preview.issues.filter(i => i.status === 'empty').length} 个空章节将在导出时自动跳过
                  </p>
                )}
              </div>
            ) : null}
          </section>
        </div>

        <div className="flex shrink-0 items-center gap-3 border-t border-gray-100 bg-gray-50 px-6 py-4">
          <button
            type="button"
            onClick={() => download('outline')}
            disabled={downloading !== null || !preview || preview.total_chapters === 0}
            title="导出卷 → 章 + 五拍章纲"
            className="flex flex-1 items-center justify-center gap-2 rounded-xl border border-gray-200 bg-white py-2.5 text-sm font-medium text-gray-700 transition-colors hover:border-amber-300 disabled:cursor-not-allowed disabled:opacity-50"
          >
            {downloading === 'outline' ? <Loader2 size={14} className="animate-spin" /> : <ListTree size={14} />}
            下载章纲
          </button>
          <button
            type="button"
            onClick={() => download('txt')}
            disabled={downloading !== null || !preview || writtenCount === 0}
            className="flex flex-1 items-center justify-center gap-2 rounded-xl bg-amber-500 py-2.5 text-sm font-medium text-white transition-colors hover:bg-amber-600 disabled:cursor-not-allowed disabled:opacity-50"
          >
            {downloading === 'txt' ? <Loader2 size={14} className="animate-spin" /> : <FileText size={14} />}
            下载 TXT
          </button>
          <button
            type="button"
            onClick={() => download('package')}
            disabled={downloading !== null || !preview || writtenCount === 0}
            className="flex flex-1 items-center justify-center gap-2 rounded-xl bg-gray-700 py-2.5 text-sm font-medium text-white transition-colors hover:bg-gray-800 disabled:cursor-not-allowed disabled:opacity-50"
          >
            {downloading === 'package' ? <Loader2 size={14} className="animate-spin" /> : <Package size={14} />}
            ZIP 投稿包
          </button>
        </div>
      </div>
    </div>
  )
}

/** 路由 / 懒加载 chunk 等待时的占位 */
export default function PageSpinner({ label = '加载中…' }: { label?: string }) {
  return (
    <div className="flex h-full min-h-[12rem] items-center justify-center">
      <div className="text-gray-500 text-sm">{label}</div>
    </div>
  )
}

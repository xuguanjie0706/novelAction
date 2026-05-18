/** 星图模式背景：深空渐变 + 静态星点 */
export function StarField() {
  return (
    <div className="pointer-events-none absolute inset-0 overflow-hidden" aria-hidden>
      <div
        className="absolute inset-0"
        style={{
          background:
            'radial-gradient(ellipse 80% 60% at 50% 45%, #1e293b 0%, #0f172a 45%, #020617 100%)',
        }}
      />
      {STAR_POINTS.map((s, i) => (
        <span
          key={i}
          className="absolute rounded-full bg-white"
          style={{
            left: `${s.x}%`,
            top: `${s.y}%`,
            width: s.r,
            height: s.r,
            opacity: s.o,
          }}
        />
      ))}
    </div>
  )
}

const STAR_POINTS = [
  { x: 8, y: 12, r: 1, o: 0.35 },
  { x: 22, y: 8, r: 1.5, o: 0.5 },
  { x: 45, y: 5, r: 1, o: 0.4 },
  { x: 67, y: 15, r: 2, o: 0.25 },
  { x: 88, y: 10, r: 1, o: 0.45 },
  { x: 15, y: 35, r: 1, o: 0.3 },
  { x: 92, y: 42, r: 1.5, o: 0.35 },
  { x: 5, y: 58, r: 2, o: 0.2 },
  { x: 78, y: 68, r: 1, o: 0.5 },
  { x: 35, y: 88, r: 1.5, o: 0.4 },
  { x: 55, y: 92, r: 1, o: 0.35 },
  { x: 12, y: 78, r: 1, o: 0.45 },
]

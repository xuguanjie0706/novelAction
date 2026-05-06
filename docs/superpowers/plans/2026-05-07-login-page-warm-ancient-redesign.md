# Warm Ancient Style Login Page Redesign Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Redesign `LoginPage.tsx` to a left-right split layout featuring a warm ancient Chinese study scene (ink, paper, oil lamp) on the left and a modern frosted-glass form card on the right, using the approved warm ancient color palette while preserving all existing authentication logic and behavior.

**Architecture:** Keep the component as a single focused file (`LoginPage.tsx`). Existing `useState`, `handleSubmit`, and `useAuthStore` calls remain untouched. Only the JSX return value and a few small helper additions (password visibility toggle using `lucide-react`) change. Left panel uses pure Tailwind + inline SVG + CSS animations for the study scene (no new image assets or libraries). Right panel uses `backdrop-blur-2xl` frosted card. Responsive via `md:` breakpoints.

**Tech Stack:** React 18 + TypeScript, Tailwind CSS 3.4 (via Vite), `lucide-react` (Eye/EyeOff icons), `react-router-dom`, `zustand`.

---

## Task 1: Update outer layout container and add left illustration panel (CSS ancient study scene)

**Files:**
- Modify: `apps/client/src/pages/LoginPage.tsx:52-183` (the entire return statement)

- [ ] **Step 1.1: Replace the root div with new split layout structure**

```tsx
return (
  <div className="min-h-screen bg-[#0C111C] flex flex-col md:flex-row overflow-hidden">
    {/* Left: Ancient study illustration (CSS scene) */}
    <div className="relative md:w-[55%] h-[200px] md:h-auto bg-[#121B22] flex items-center justify-center overflow-hidden">
      {/* Background layers for depth */}
      <div className="absolute inset-0 bg-[radial-gradient(#3A2F2A_0.8px,transparent_1px)] bg-[length:4px_4px] opacity-30" />

      {/* Wooden desk surface */}
      <div className="absolute bottom-0 left-0 right-0 h-2/5 bg-[#2C2522] shadow-[inset_0_40px_40px_-20px_#1C2526]" />

      {/* Oil lamp with warm glow */}
      <div className="absolute left-1/3 top-1/3 w-16 h-16">
        <div className="absolute inset-0 bg-[#C9A227] rounded-full blur-2xl opacity-40 animate-[pulse_2.5s_ease-in-out_infinite]" />
        <div className="relative w-16 h-16 flex items-end justify-center">
          {/* Lamp base (simplified) */}
          <div className="w-8 h-6 bg-[#5C5240] rounded-full" />
          {/* Flame */}
          <div className="absolute -top-3 w-3 h-5 bg-[#F5E8C7] rounded-full animate-[pulse_1.8s_ease-in-out_infinite] shadow-[0_0_12px_#C9A227]" />
        </div>
      </div>

      {/* Scattered papers */}
      <div className="absolute right-1/4 top-1/4 w-20 h-24 rotate-[-12deg] border border-[#3A2F2A] bg-[#F5E8C7]/10 rounded-sm shadow-inner" />
      <div className="absolute right-1/3 bottom-1/3 w-16 h-20 rotate-[18deg] border border-[#3A2F2A] bg-[#F5E8C7]/10 rounded-sm" />
      {/* Ink lines on paper */}
      <div className="absolute right-[26%] top-[27%] w-12 h-[1px] bg-[#3A2F2A]/40" />
      <div className="absolute right-[26%] top-[32%] w-10 h-[1px] bg-[#3A2F2A]/40" />

      {/* Subtle bamboo curtain hint (right edge) */}
      <div className="absolute right-0 top-0 bottom-0 w-8 bg-gradient-to-l from-[#1C2526]/60 to-transparent" />
    </div>

    {/* Right: Frosted form card */}
    <div className="md:w-[45%] flex items-center justify-center px-6 py-10 md:py-0">
      <div className="w-full max-w-[420px] bg-[#1C2526]/70 backdrop-blur-2xl border border-[#3A2F2A] rounded-2xl shadow-2xl shadow-black/40 p-10">
        {/* Content will be added in later tasks */}
      </div>
    </div>
  </div>
)
```

- [ ] **Step 1.2: Run the dev server and visually verify the left panel**

Run (in terminal):
```bash
cd apps/client && pnpm dev
```
Expected: At http://localhost:3173/login you see a split screen on desktop. Left side shows dark teal background with visible "desk", yellow glowing "oil lamp" (pulsing), faint paper rectangles, and subtle grid texture. No console errors. Right side shows empty frosted card for now.

- [ ] **Step 1.3: Commit the layout shell**

```bash
git add apps/client/src/pages/LoginPage.tsx
git commit -m "feat(login): add split layout shell with CSS ancient study scene on left"
```

---

## Task 2: Add Logo, title, and Tab switcher inside the card

**Files:**
- Modify: `apps/client/src/pages/LoginPage.tsx` (inside the right card div)

- [ ] **Step 2.1: Insert Logo + title + Tab buttons (replace the placeholder comment)**

```tsx
{/* Logo / Title */}
<div className="text-center mb-8">
  <div className="inline-flex items-center justify-center w-14 h-14 rounded-2xl bg-[#C9A227] mb-4 shadow-lg shadow-[#C9A227]/30">
    <span className="text-2xl">📖</span>
  </div>
  <h1 className="text-2xl font-bold text-[#F5E8C7] tracking-wide">NovelAction</h1>
  <p className="text-[#A8B0B8] text-sm mt-1.5">AI 驱动的古典小说创作空间</p>
</div>

{/* Tab 切换 */}
<div className="flex mb-8 bg-[#121B22] rounded-xl p-1 border border-[#3A2F2A]">
  <button
    type="button"
    onClick={() => { setMode('login'); setError(null) }}
    className={`flex-1 py-2.5 text-sm font-medium rounded-lg transition-all duration-200 ${
      mode === 'login'
        ? 'bg-[#C9A227] text-[#0C111C] shadow'
        : 'text-[#A8B0B8] hover:text-[#F5E8C7]'
    }`}
  >
    登录
  </button>
  <button
    type="button"
    onClick={() => { setMode('register'); setError(null) }}
    className={`flex-1 py-2.5 text-sm font-medium rounded-lg transition-all duration-200 ${
      mode === 'register'
        ? 'bg-[#C9A227] text-[#0C111C] shadow'
        : 'text-[#A8B0B8] hover:text-[#F5E8C7]'
    }`}
  >
    注册
  </button>
</div>
```

- [ ] **Step 2.2: Verify tabs visually and functionally**

After saving, refresh browser at /login.  
Expected: Warm gold logo circle with book emoji, title in warm off-white, subtitle in soft gray-blue. Tabs are pill-shaped, inactive text is soft gray-blue, active tab is warm gold with dark text. Clicking switches mode without error flash. Layout remains balanced on desktop.

- [ ] **Step 2.3: Commit**

```bash
git add apps/client/src/pages/LoginPage.tsx
git commit -m "feat(login): add warm-gold logo, title and tab switcher"
```

---

## Task 3: Port and restyle the form fields (email, password, username)

**Files:**
- Modify: `apps/client/src/pages/LoginPage.tsx` (the form JSX)

- [ ] **Step 3.1: Replace the entire <form> ... </form> block with new styled version (keep logic identical)**

```tsx
<form onSubmit={handleSubmit} className="space-y-5">
  {/* 用户名（仅注册） */}
  {mode === 'register' && (
    <div>
      <label className="block text-sm font-medium text-[#A8B0B8] mb-1.5">
        用户名 <span className="text-[#5C5240] font-normal">（可选）</span>
      </label>
      <input
        type="text"
        value={username}
        onChange={e => setUsername(e.target.value)}
        placeholder="留空则使用邮箱前缀"
        className="w-full bg-[#121B22] border border-[#3A2F2A] rounded-xl px-4 py-3 text-sm text-[#F5E8C7] placeholder:text-[#5C5240] focus:outline-none focus:border-[#C9A227] focus:ring-1 focus:ring-[#C9A227]/30 transition-all"
      />
    </div>
  )}

  {/* 邮箱 */}
  <div>
    <label className="block text-sm font-medium text-[#A8B0B8] mb-1.5">
      邮箱
    </label>
    <input
      type="email"
      value={email}
      onChange={e => setEmail(e.target.value)}
      placeholder="your@email.com"
      required
      autoComplete="email"
      className="w-full bg-[#121B22] border border-[#3A2F2A] rounded-xl px-4 py-3 text-sm text-[#F5E8C7] placeholder:text-[#5C5240] focus:outline-none focus:border-[#C9A227] focus:ring-1 focus:ring-[#C9A227]/30 transition-all"
    />
  </div>

  {/* 密码 + visibility toggle (new) */}
  <div>
    <label className="block text-sm font-medium text-[#A8B0B8] mb-1.5">
      密码 {mode === 'register' && <span className="text-[#5C5240] font-normal">（至少 6 位）</span>}
    </label>
    <div className="relative">
      <input
        type={showPassword ? 'text' : 'password'}
        value={password}
        onChange={e => setPassword(e.target.value)}
        placeholder={mode === 'register' ? '至少 6 位' : '请输入密码'}
        required
        autoComplete={mode === 'login' ? 'current-password' : 'new-password'}
        className="w-full bg-[#121B22] border border-[#3A2F2A] rounded-xl px-4 py-3 pr-12 text-sm text-[#F5E8C7] placeholder:text-[#5C5240] focus:outline-none focus:border-[#C9A227] focus:ring-1 focus:ring-[#C9A227]/30 transition-all"
      />
      <button
        type="button"
        onClick={() => setShowPassword(!showPassword)}
        className="absolute right-4 top-1/2 -translate-y-1/2 text-[#A8B0B8] hover:text-[#C9A227] transition-colors"
        aria-label={showPassword ? '隐藏密码' : '显示密码'}
      >
        {showPassword ? <EyeOff size={18} /> : <Eye size={18} />}
      </button>
    </div>
  </div>

  {/* 错误提示 */}
  {error && (
    <div className="flex items-start gap-2 bg-[#3A2A2A]/60 border border-[#8B4A4A]/40 rounded-xl px-4 py-3 text-sm text-[#D4A5A5]">
      <span className="mt-0.5">✕</span>
      <p>{error}</p>
    </div>
  )}

  {/* 提交按钮 */}
  <button
    type="submit"
    disabled={loading}
    className="w-full bg-[#C9A227] hover:bg-[#D4AF37] active:bg-[#B8971F] disabled:bg-[#5C5240] disabled:text-[#8A7F6A] disabled:cursor-not-allowed text-[#0C111C] font-medium py-3 rounded-xl text-sm transition-all shadow-lg shadow-[#C9A227]/20 mt-2 flex items-center justify-center gap-2"
  >
    {loading ? (
      <>
        <span className="inline-block w-4 h-4 border-2 border-[#0C111C] border-t-transparent rounded-full animate-spin" />
        {mode === 'login' ? '登录中…' : '注册中…'}
      </>
    ) : (
      mode === 'login' ? '登录' : '注册并登录'
    )}
  </button>
</form>
```

Note: Add `const [showPassword, setShowPassword] = useState(false)` near other useState declarations (top of component).

Import at top:
```tsx
import { Eye, EyeOff } from 'lucide-react'
```

- [ ] **Step 3.2: Verify form fields and password toggle**

Refresh page.  
Expected: All inputs have dark ink background, warm off-white text, subtle gold focus ring. Register mode shows optional username field. Password field has clickable eye icon (from lucide) that toggles visibility. Error banner uses soft terracotta colors. Submit button is warm gold with dark text, shows spinner on loading.

- [ ] **Step 3.3: Commit form restyling**

```bash
git add apps/client/src/pages/LoginPage.tsx
git commit -m "feat(login): restyle form inputs, add password visibility toggle with lucide icons"
```

---

## Task 4: Add bottom switch prompt and final responsive polish

**Files:**
- Modify: `apps/client/src/pages/LoginPage.tsx`

- [ ] **Step 4.1: Add the bottom prompt after the form (inside the card)**

```tsx
{/* 底部切换提示 */}
<p className="text-center text-[#5C5240] text-xs mt-8">
  {mode === 'login' ? '还没有账号？' : '已有账号？'}
  <button
    type="button"
    onClick={() => { setMode(mode === 'login' ? 'register' : 'login'); setError(null) }}
    className="text-[#C9A227] hover:text-[#D4AF37] ml-1 transition-colors font-medium"
  >
    {mode === 'login' ? '立即注册' : '去登录'}
  </button>
</p>
```

- [ ] **Step 4.2: Add responsive classes and mobile verification**

Ensure the outer div already has `flex-col md:flex-row`.  
On mobile (<768px): left panel becomes ~200px tall top banner, card is full-width with comfortable padding.

Run dev server again and resize browser window or use devtools mobile view.  
Expected: Smooth reflow, no overflow, all text readable, touch targets comfortable.

- [ ] **Step 4.3: Final visual QA checklist (manual)**

- [ ] Desktop: left illustration occupies ~55%, lamp glow visible, papers subtle, card perfectly centered with good breathing room.
- [ ] Focus states on all inputs and buttons are warm gold and accessible (contrast > 4.5:1).
- [ ] Tab switching feels smooth (200ms transition).
- [ ] Loading state shows spinner + correct Chinese text.
- [ ] No horizontal scroll on any viewport.

- [ ] **Step 4.4: Commit final version**

```bash
git add apps/client/src/pages/LoginPage.tsx
git commit -m "feat(login): add bottom prompt, responsive polish and final visual QA"
```

---

## Task 5: Build verification and cleanup

**Files:**
- (no code change, verification only)

- [ ] **Step 5.1: Run production build to ensure no TypeScript or Tailwind errors**

```bash
cd apps/client && pnpm build
```
Expected output: `✓ built in X ms` with no errors or warnings related to LoginPage.

- [ ] **Step 5.2: Final commit (if any small fix)**

If build passes cleanly:
```bash
git commit --allow-empty -m "chore(login): verify production build passes after redesign"
```

---

## Summary of Changes

- **Single file modified**: `apps/client/src/pages/LoginPage.tsx`
- **New dependency usage**: Only `lucide-react` icons (already in package.json)
- **No new files**, no breaking changes to auth flow or store
- **All existing functionality preserved** (login/register, error handling, navigation)

---

## Post-Implementation Notes (for future iterations)

- Replace CSS study scene with a high-resolution Unsplash ancient study photo (warm tone) if desired — simply swap the left div content.
- Add “忘记密码” link placeholder when backend supports it.
- Consider extracting the illustration into its own `LoginIllustration.tsx` component if the scene becomes more complex.

---

**Plan complete and saved to `docs/superpowers/plans/2026-05-07-login-page-warm-ancient-redesign.md`.**

**Two execution options:**

1. **Subagent-Driven (recommended)** — I dispatch a fresh subagent per task, review between tasks, fast iteration.
2. **Inline Execution** — Execute tasks in this session using executing-plans, batch execution with checkpoints.

**Which approach would you like me to use?** (Reply with 1 or 2, or suggest modifications to the plan first.)
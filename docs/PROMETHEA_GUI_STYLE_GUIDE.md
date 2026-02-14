# 🎨 Arcade Assistant — Promethea GUI Style Guide

**Owner:** Promethea (Stylistic Architect)
**Scope:** All React UI (panels, widgets, overlays)
**Status:** 🛡 Authoritative — this guide overrides prompt logic

---

## 🧭 Purpose

This document defines the **non-negotiable visual and structural rules** for all GUI contributions. It exists to enforce consistency, accessibility, and kiosk-readiness across the Arcade Assistant interface. If a prompt or instruction contradicts this guide, **this guide takes precedence**.

All agents (Claude, Codex, Cursor Copilot, etc.) must read and comply **before generating or modifying any GUI code**. Pull requests that do not comply are automatically rejected.

---

## 0. Non-Negotiables (Must Never Break)

- ❗ The GUI must always render. Never return broken or invisible output.
- ❗ The 3×3 layout grid is fixed. Do not change spans or reorder panels.
- ❗ No thrown errors may bubble to the app root. Use inline fallback states.
- ❗ Panels must be self-contained. No side effects on other panels or layout.
- ❗ Always fail gracefully. If unsure, render `<InlineError />` and continue.

---

## 1. Global Layout & Grid Discipline

Arcade Assistant uses a fixed **3×3 panel grid**. Each panel occupies exactly one grid cell. Layout must never mutate at runtime.

Every panel **must** be wrapped like this:

```jsx
<motion.div className="col-span-1 row-span-1" initial={{opacity:0}} animate={{opacity:1}}>
  {/* Panel Card goes here */}
</motion.div>
```

Panels may not span multiple rows or columns.

## 2. Visual System: Tokens & Design Language

### Typography
- **Title:** `text-xl font-semibold`
- **Section Heading:** `text-lg font-semibold`
- **Body:** `text-sm leading-6`

### Shape & Depth
- **Corners:** `rounded-2xl`
- **Shadow:** `shadow-md` (content), `shadow-lg` (primary cards)
- **Borders:** `border border-white/10` (dark mode surfaces)

### Spacing
- **Card Padding:** `p-4`
- **Inner Gaps:** `gap-3` (tight) / `gap-4` (normal)

### Color by Grid Row
- **Row 1 (Knowledge):** `bg-blue-600 text-white`
- **Row 2 (Control):** `bg-emerald-600 text-white`
- **Row 3 (Hardware):** `bg-purple-600`, `bg-cyan-600`, or `bg-orange-500` — pick one consistently per panel

## 3. Panel Card Anatomy (Required Structure)

Hierarchy:
```
Card
 ├─ Header (Icon + Title + StatusChip)
 ├─ Toolbar (top-right actions)
 └─ Content (lists, visuals, or forms)
```

Header Example:
```jsx
<CardHeader className="flex items-center justify-between">
  <div className="flex items-center gap-2">
    <Icon className="w-5 h-5" />
    <h2 className="text-xl font-semibold">Panel Title</h2>
  </div>
  <StatusChip />
</CardHeader>
```

**Toolbar Rules:**
- Located top-right only
- Contains mic toggle, status, and dropdown actions
- Do not float buttons or scatter actions around the panel

## 4. Microphone & Voice Controls

This has strict placement rules due to recurring issues.

**✅ Must Appear In:**
- Toolbar, top-right only
- As a group: mic toggle + level meter + status chip

**❌ Never Do:**
- Floating mic buttons
- Mic inside content areas
- Runtime repositioning

**Sizing & Behavior:**
- **Mic Button:** `size="sm"` + `variant="secondary"`
- **Icon:** `w-4 h-4`
- **Level Meter:** 80–120px, hide on narrow screens
- **Tooltip:** "Start/Stop Listening"
- **Shortcut:** M to toggle mic (optional)

**States:**
- **Idle:** Default icon
- **Listening:** Pulsing animation (Framer Motion scale/opacity)
- **Muted/Blocked:** Slashed mic + inline warning

**Error Handling:**
If getUserMedia fails:
```jsx
<InlineAlert message="Mic access denied. Click to fix permissions." />
```

## 5. Data States (Always Implement)

Every interactive section must support:

- **Loading** — `<SkeletonRows count={3} />`
- **Empty** — `<EmptyState title="No profiles found" actionLabel="Create Profile" />`
- **Error** — `<InlineError message="Couldn't load mappings." />`

No spinner-only loading. Always use real skeletons. Errors must include next steps.

## 6. Responsiveness & Kiosk Readiness

- Optimized for 1080p; must scale cleanly to 4K.
- Use grid, flex, gap. Avoid absolute positioning.
- Actions collapse into DropdownMenu on narrow viewports.
- No hover-only affordances — kiosk users need always-visible controls.

## 7. Accessibility & Motion

- All icons must include `aria-label` unless label is visible.
- Ensure color contrast passes WCAG AA (test Tailwind colors).
- Support `prefers-reduced-motion` — disable unnecessary animation.

## 8. Error Containment

- Do not throw errors. All failures must be handled inline.
- Use non-blocking `<Dialog />` or `<Toast />` for critical issues.
- If backend is offline:
  - Show "Offline" status in StatusChip
  - Disable only actions that depend on backend
  - Keep the panel interactive

## 9. 🚫 Hard Stops (Do Not Do)

- ❌ Floating mic or action buttons
- ❌ Grid span changes
- ❌ Inline styles or global CSS injection
- ❌ Modal traps for validation errors
- ❌ Magic numbers for positioning
- ❌ Hover-only buttons or invisible controls

## 10. Panel Template (Copy/Paste Safe Stub)

```jsx
import { Card, CardHeader, CardContent } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import { DropdownMenu, DropdownMenuTrigger, DropdownMenuContent, DropdownMenuItem } from "@/components/ui/dropdown-menu";
import { Mic, MoreHorizontal } from "lucide-react";
import { motion } from "framer-motion";

export default function PanelTemplate({ title = "Panel Title", accent = "bg-emerald-600" }) {
  return (
    <motion.div className="col-span-1 row-span-1" initial={{opacity:0}} animate={{opacity:1}}>
      <Card className={`${accent} text-white rounded-2xl shadow-lg`}>
        <CardHeader className="flex items-center justify-between">
          <div className="flex items-center gap-2">
            <span className="w-5 h-5 rounded-full bg-white/20" />
            <h2 className="text-xl font-semibold">{title}</h2>
          </div>

          {/* Toolbar */}
          <div className="flex items-center gap-2">
            <Button size="sm" variant="secondary" aria-label="Toggle microphone">
              <Mic className="w-4 h-4" />
            </Button>
            <Badge className="bg-black/30">Idle</Badge>
            <DropdownMenu>
              <DropdownMenuTrigger asChild>
                <Button size="sm" variant="secondary" aria-label="More actions">
                  <MoreHorizontal className="w-4 h-4" />
                </Button>
              </DropdownMenuTrigger>
              <DropdownMenuContent align="end">
                <DropdownMenuItem>Settings</DropdownMenuItem>
                <DropdownMenuItem>Help</DropdownMenuItem>
              </DropdownMenuContent>
            </DropdownMenu>
          </div>
        </CardHeader>

        <CardContent className="p-4">
          {/* Add content here */}
          <div className="text-sm opacity-90">Content goes here…</div>
        </CardContent>
      </Card>
    </motion.div>
  );
}
```

## 11. Submission Checklist ✅

All pull requests must include:

- ☐ Used Panel Template layout
- ☐ Toolbar includes mic toggle + actions
- ☐ Included loading, empty, and error states
- ☐ No inline styles or global CSS
- ☐ No layout/grid changes
- ☐ Proper accessibility attributes
- ☐ Animation respects motion preferences

## 12. Enforcement

CI will reject PRs with:
- Inline styles
- Floating mic buttons
- Layout span violations
- Global CSS leakage

Reviewers will enforce checklist compliance.
Style violations = auto-fail.

## 13. Change Control

Only Promethea may propose edits to this document.

Changes require:
- Visual before/after diffs
- Approval via visual sign-off
- Update to UNIVERSAL_AGENT_RULES.md → Must Do This → Read Before Any GUI Edits

## 14. Reminder for AI Agents

If you're writing or editing GUI code:

- You must use the provided component template
- You must not alter layout structure
- You must render safely in degraded or error states
- You must prioritize visibility and resilience
- You must not invent styles or frameworks

Your output is part of a visual operating system. Treat it like production-grade software — because it is.
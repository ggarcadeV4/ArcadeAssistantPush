# The Neon Monolith — Design System Specification
## Source: Stitch Project `projects/7252577742218017697` ("LaunchBox LoRa Redesign Contract")

---

## Design Theme
- **Color Mode:** DARK
- **Headline Font:** Space Grotesk
- **Body Font:** Manrope
- **Label Font:** Inter
- **Roundness:** ROUND_FOUR (0.25rem)
- **Color Variant:** VIBRANT
- **Spacing Scale:** 2

---

## Color Palette

### Core Tokens
| Token | Hex | Usage |
|-------|-----|-------|
| `background` | `#0e0e10` | Base canvas |
| `surface` | `#0e0e10` | Main background |
| `surface-container` | `#19191c` | Sidebar, panels |
| `surface-container-low` | `#131315` | Nested backgrounds |
| `surface-container-high` | `#1f1f22` | Elevated cards |
| `surface-container-highest` | `#262528` | Search inputs, active elements |
| `surface-container-lowest` | `#000000` | Deep recesses |
| `surface-bright` | `#2c2c2f` | Bright surfaces |
| `surface-variant` | `#262528` | Alternative surface |

### Primary (Brand Light — Purple)
| Token | Hex |
|-------|-----|
| `primary` | `#cc97ff` |
| `primary-container` | `#c284ff` |
| `primary-dim` | `#9c48ea` |
| `on-primary` | `#47007c` |
| `on-primary-container` | `#360061` |

### Secondary (Action Light — Cyan)
| Token | Hex |
|-------|-----|
| `secondary` | `#3adffa` |
| `secondary-container` | `#006877` |
| `secondary-dim` | `#1ad0eb` |
| `on-secondary` | `#004b56` |
| `on-secondary-container` | `#eafbff` |

### Tertiary (Accent — Pink)
| Token | Hex |
|-------|-----|
| `tertiary` | `#ff96bb` |
| `tertiary-container` | `#fb81ae` |
| `tertiary-dim` | `#ee77a3` |
| `on-tertiary` | `#690939` |

### Text & Outline
| Token | Hex |
|-------|-----|
| `on-background` | `#f6f3f5` |
| `on-surface` | `#f6f3f5` |
| `on-surface-variant` | `#acaaad` |
| `outline` | `#767577` |
| `outline-variant` | `#48474a` |

### Error
| Token | Hex |
|-------|-----|
| `error` | `#ff6e84` |
| `error-container` | `#a70138` |
| `on-error` | `#490013` |

---

## Override Colors (CSS Variables)
```css
--override-primary: #A855F7;
--override-secondary: #22D3EE;
--override-neutral: #121214;
```

---

## Typography System

### Font Scale
- **Display Large:** Space Grotesk, 3.5rem — Hero game titles
- **Headline Large:** Space Grotesk — Section headers
- **Title Medium:** Manrope — Card titles
- **Body Large:** Manrope, 1rem, 1.6 line-height — Descriptions
- **Label Small:** Inter — Badges, status indicators
- **Label Medium:** Inter — Technical metadata

---

## Component Rules

### Game Cards
- No borders. Use `surface-container-lowest` for card base
- **Hover:** Scale 1.02x, apply `primary` outer glow (5px blur, 10% opacity)
- **Badges:** `secondary-container` bg, `on-secondary-container` text, overlapping corner

### PanelShell Sidebar
- Active items: `primary` text + 2px vertical light bar
- Inactive items: `on-surface-variant`
- Chat drawer: nested in `surface-container-low`, no dividers, 12px spacing

### Shader Diff Modal
- Split-pane: Old → `tertiary` accent glow, New → `secondary` accent glow
- Background: Glassmorphism (semi-transparent `surface-bright` + backdrop-blur)

### Buttons
- **Primary:** Gradient `primary` → `primary-dim` at 135°, roundness `md`
- **Filter Chips:** `surface-container-highest` default, `secondary` bg + `on-secondary` text when selected
- **Input Fields:** Ghost borders only, on focus → border opacity 40% using `primary`

---

## Key Rules
1. **No-Line Rule:** Never use 1px solid borders to define sections
2. **Glass & Gradient:** Floating elements use 60% opacity + 20px backdrop-blur
3. **Never use #FFFFFF** — always `on-surface` (#f6f3f5)
4. **Never use divider lines** between chat messages or list items
5. **Error color** is `#ff6e84`, not standard red

---

## Screens in Project
1. Main Game Library (2 variants)
2. Shader Preview Modal (2 variants)
3. LoRa Chat & Voice Interface
4. LoRa Chat Drawer
5. Loading & Error States

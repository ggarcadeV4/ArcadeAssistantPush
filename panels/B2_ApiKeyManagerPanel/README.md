# 🔐 API Key Manager Panel (B2)

**Grid Slot:** Row 2, Column B (`col-span-1 row-span-1`)
**Owner Agent:** Hera
**Managing Agents:** Hermes (key logic), Janus (security enforcement)
**Design Authority:** Promethea
**Render Status:** Optional but recommended for all cloud-enabled builds

---

## 🎯 Purpose

This panel enables users to securely enter, store, test, and manage their API keys for Claude, OpenAI, and Anthropic. It supports encrypted local-only storage, usage status per key, and a global "local-only mode" switch for offline fallback behavior.

---

## 🎨 Visual Blueprint

| Zone     | Elements                                                                     |
|----------|------------------------------------------------------------------------------|
| Header   | `Key` Icon, `"API Keys"` title, `StatusChip` (All Valid / Partial / Invalid) |
| Toolbar  | `[Test All Keys]`, (Optional: `[Clear All]`)                                 |
| Content  | - 3x `<ApiKeyField />` rows (Claude, OpenAI, Anthropic)<br>- `<LocalOnlyToggle />`<br>- Footer: `"Keys are stored locally and never shared."` |

---

## 🧩 Required Components (Hera)

- `ApiKeyField.tsx`
  - Props: `provider`, `value`, `onChange`, `onTest`
  - Shows obfuscated input, provider icon, save/test buttons, key status

- `ApiKeyStatus.tsx`
  - Renders a colored badge: `Valid`, `Invalid`, `Expired`, `Missing`, `Testing`

- `TestAllKeys.tsx`
  - Toolbar button that calls Hermes to validate all available keys

- `LocalOnlyToggle.tsx`
  - Switch UI for `"Use Local AI Only"` mode (blocks all remote calls via Janus)

---

## 🛡️ Connected Agents

| Agent     | Purpose                                       |
|-----------|-----------------------------------------------|
| **Hermes**    | Handles key storage, testing, encryption        |
| **Janus**     | Enforces security (read/write sandbox, fallback) |
| **DebugPanel**| Receives key errors or security violations      |

---

## ⚠️ Rules

- All keys must be stored **locally and securely**
- No remote sync of key material
- Key tests must return results within 3s or fail gracefully
- Local-only mode must override any cloud call attempt
- Save buttons must debounce rapid entry attempts

---

## ✅ Status

- [x] Design approved (Promethea)
- [ ] `index.tsx` scaffolded (in progress)
- [ ] Hermes key store logic integrated
- [ ] Janus fallback enforcement active

---
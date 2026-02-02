# Controller Chuck Diagnostic Report

**Date:** 2025-11-26  
**Issue:** ErrorBoundary fallback UI appears instead of real Chuck panel when navigating via Dewey chip handoff

---

## 1. Exact Crash Location

**File:** `frontend/src/panels/controller/ControllerChuckPanel.jsx`  
**Line:** 1532 (in production build: `index-75c14b7b.js`)  
**Error:** `ReferenceError: Cannot access 'handleSendChatMessage' before initialization`

**Stack Trace Summary:**
```
at ControllerChuckPanel (ControllerChuckPanel.jsx:1532:36)
at renderWithHooks (chunk-VRHMX22Y.js:11568:26)
at mountIndeterminateComponent (chunk-VRHMX22Y.js:14946:21)
at beginWork (chunk-VRHMX22Y.js:15934:22)
```

**Specific Code:**
```javascript
// Line 1532 - useEffect dependency array
}, [speechSupported, addMessage, handleSendChatMessage]);
//                                 ^^^^^^^^^^^^^^^^^^^^^^
//                                 Referenced before defined!
```

The useEffect at line ~1495-1532 includes `handleSendChatMessage` in its dependency array, but the function is defined much later at line 1756.

---

## 2. Why Cold Mount Fails

### Normal Navigation (Works)
When navigating normally (sidebar, direct URL), the component may have been previously mounted and React's reconciliation keeps some state warm. The error might not trigger because:
- React may reuse the component instance
- Hot module replacement (HMR) in dev mode patches the component
- The component tree is already initialized

### Chip Navigation (Fails)
When navigating via Dewey's chip handoff:
1. User clicks chip button in Dewey panel
2. `navigate(/assistants?agent=controller-chuck)` is called
3. React Router unmounts Dewey and mounts a **completely fresh** ControllerChuckPanel
4. **Cold mount** = all hooks execute in order from top to bottom
5. JavaScript parser encounters the useEffect at line 1532
6. Dependency array references `handleSendChatMessage`
7. **JavaScript hoisting rules:** Function expressions (const/let) are NOT hoisted
8. `handleSendChatMessage` doesn't exist yet (defined 224 lines later)
9. **ReferenceError thrown during component initialization**
10. ErrorBoundary catches the error
11. Fallback UI renders instead of Chuck

**Key Difference:** Cold mount forces strict top-to-bottom evaluation, exposing the hoisting error that might be masked in warm mounts.

---

## 3. How ErrorBoundary Gets Triggered

**Location:** `frontend/src/components/ErrorBoundary.tsx`  
**Wrapper:** `frontend/src/components/Assistants.jsx` line 77

```javascript
if (agent === 'chuck' || agent === 'controller-chuck') {
  return <ErrorBoundary><ControllerChuckPanel /></ErrorBoundary>
}
```

**Trigger Mechanism:**
1. ControllerChuckPanel throws ReferenceError during render/mount
2. React's error boundary lifecycle catches it via `componentDidCatch()`
3. ErrorBoundary sets `hasError: true` in state
4. ErrorBoundary renders fallback UI instead of children
5. Fallback shows red alert box with "Panel error" message

**Fallback UI Appearance:**
- Fixed position red alert box (top-left)
- "Panel error" title
- Error message display
- "Try Again" and "Go Home" buttons
- This is what you're seeing instead of Chuck's real interface

---

## 4. Specific Problematic Code

### The Hoisting Error

**useEffect at lines 1495-1532:**
```javascript
useEffect(() => {
  if (!speechSupported || typeof window === 'undefined') return;
  const RecognitionCtor = window.SpeechRecognition || window.webkitSpeechRecognition;
  if (!RecognitionCtor) return;
  const recognition = new RecognitionCtor();
  // ... setup code ...
  
  recognition.onresult = (event) => {
    try {
      const transcript = event?.results?.[0]?.[0]?.transcript;
      if (transcript) {
        handleSendChatMessage(transcript);  // ← USED HERE (line ~1519)
      }
    } catch (err) {
      console.error('Voice capture parsing failed:', err);
    }
  };
  
  return () => { /* cleanup */ };
}, [speechSupported, addMessage, handleSendChatMessage]);
//                                ^^^^^^^^^^^^^^^^^^^^^^
//                                REFERENCED IN DEPS (line 1532)
```

**Function definition at lines 1756-1806:**
```javascript
// Handle sending chat messages to Chuck AI
const handleSendChatMessage = useCallback(async (text) => {
  // ... 50+ lines of implementation ...
}, [board, mapping, consoleControllers, consoleHints, consoleError, addMessage, handleChatIntent, voicePlaybackEnabled]);
```

**The Problem:**
- useEffect dependency array at line 1532 references `handleSendChatMessage`
- JavaScript evaluates this reference during component initialization
- `handleSendChatMessage` is a `const` declaration (not hoisted like `function` declarations)
- At parse time, JavaScript sees the reference before the declaration
- **Temporal Dead Zone (TDZ)** violation → ReferenceError

### Why It Only Crashes on Cold Mount

**Warm Mount (works):**
- Component already exists in React's fiber tree
- HMR patches the component in place
- Function references may be preserved
- React's reconciliation skips some initialization

**Cold Mount (crashes):**
- Fresh component instance
- All hooks execute in strict order
- JavaScript parser enforces TDZ rules
- No previous state to fall back on
- Error is unavoidable

---

## 5. Root Cause Summary

### What Failed
A **JavaScript hoisting error** in ControllerChuckPanel where a useEffect hook references a function (`handleSendChatMessage`) that is defined 224 lines later in the file.

### Why It Failed
- `const` and `let` declarations are **not hoisted** in JavaScript
- The useEffect at line 1532 includes `handleSendChatMessage` in its dependency array
- During component initialization, JavaScript tries to evaluate this reference
- The function doesn't exist yet (Temporal Dead Zone)
- **ReferenceError: Cannot access 'handleSendChatMessage' before initialization**

### Why It Only Fails on Chip Navigation
**Chip navigation triggers a cold mount:**
- Dewey unmounts completely
- ControllerChuckPanel mounts fresh
- All hooks execute in strict top-to-bottom order
- JavaScript parser enforces hoisting rules
- Error is unavoidable

**Normal navigation may avoid the error:**
- Component might be warm (already mounted)
- React reconciliation may reuse instances
- HMR in dev mode patches components
- Previous state masks the hoisting issue

### Why Fallback UI Appears
1. ControllerChuckPanel crashes during mount
2. ErrorBoundary (wrapping Chuck in Assistants.jsx) catches the error
3. ErrorBoundary renders fallback UI instead of Chuck
4. User sees red alert box with "Panel error" message
5. Real Chuck interface never renders

---

## Fix Applied (Already Done)

**Solution:** Use ref pattern to avoid hoisting error

**Changes Made:**
1. Added `handleSendChatMessageRef` at line ~1495
2. Removed `handleSendChatMessage` from useEffect deps
3. Updated `onresult` to use `handleSendChatMessageRef.current`
4. Added useEffect to update ref when function changes

**Status:** Fix is in source code but **NOT in production build**

---

## Action Required

**The fix exists in source but the build is stale!**

You need to rebuild the frontend:
```bash
npm run build:frontend
```

Then refresh the browser to load the new build. The chip navigation should work after that.

---

## Additional Notes

- Same hoisting pattern was found and fixed in Gunner panel earlier
- This is a common React pitfall with useEffect dependency arrays
- Ref pattern is the standard solution for this issue
- Consider adding ESLint rule to catch these errors at dev time

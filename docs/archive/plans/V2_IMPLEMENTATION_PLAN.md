# Arcade Assistant V2 Implementation Plan

**Project Manager:** Claude (Architecture & Strategy)
**Implementation Agent:** Codex (Hands-on Coding)
**Project Lead:** User (Vision & Decisions)

**Timeline:** 2 days (12-16 hours total work)
**Start Date:** 2025-12-01 (tomorrow)
**Feature Count:** 5 features (wake word REMOVED - impractical for noisy arcade environment)

---

## **Day 1: High-Value Features (6-8 hours)**

### **Feature 1: Shader Management (LoRa Integration)** ⏱️ 2-3 hours

**Objective:** Enable LaunchBox LoRa to manage per-game visual shader settings for MAME and RetroArch emulators.

**Why This First:**
- Lowest implementation risk
- Highest user-facing value
- Reuses proven patterns (tool calling, preview/apply/revert)
- If this works, validates entire V2 approach

#### **Task 1.1: Backend Shader Endpoints** (45 min)
**File:** `backend/routers/launchbox.py`

**Add these endpoints:**
```python
@router.get("/shaders/available")
async def get_available_shaders():
    """List all installed shader presets for MAME and RetroArch."""
    # Scan A:\Emulators\MAME\shaders\*.fx
    # Scan A:\Emulators\RetroArch\shaders\*.slangp
    return {
        "mame": [...],  # List of HLSL/BGFX shaders
        "retroarch": [...]  # List of Slang/GLSL shaders
    }

@router.get("/shaders/game/{game_id}")
async def get_game_shader(game_id: str):
    """Get current shader config for specific game."""
    # Check configs/shaders/games/{game_id}.json
    return {"game_id": game_id, "shader": "crt-royale", "emulator": "mame"}

@router.post("/shaders/preview")
async def preview_shader_change(request: ShaderChangeRequest):
    """Preview shader config change with diff."""
    # Generate diff between current and new shader config
    # Return old vs new JSON for DiffPreview component
    return {"old": {...}, "new": {...}, "diff": "..."}

@router.post("/shaders/apply")
async def apply_shader_change(request: ShaderChangeRequest):
    """Apply shader config with automatic backup."""
    # Use existing backup system (logs/changes.jsonl)
    # Write configs/shaders/games/{game_id}.json
    # Log change with backup path
    return {"success": true, "backup_path": "backups/20251201/..."}

@router.post("/shaders/revert")
async def revert_shader_change(backup_path: str):
    """Rollback to previous shader config."""
    # Restore from backup_path
    return {"success": true}
```

**Data Models:**
```python
class ShaderChangeRequest(BaseModel):
    game_id: str
    shader_name: str
    emulator: Literal["mame", "retroarch"]
```

**Storage Location:**
- `configs/shaders/games/{game_id}.json`

**Example Config:**
```json
{
  "game_id": "sf2",
  "shader_name": "crt-royale",
  "emulator": "mame",
  "shader_path": "A:\\Emulators\\MAME\\shaders\\crt-royale.fx",
  "parameters": {
    "scanline_intensity": 0.7,
    "phosphor_glow": 0.5
  }
}
```

---

#### **Task 1.2: Gateway Shader Proxy** (15 min)
**File:** `gateway/routes/launchboxProxy.js`

**Add proxy routes for shader endpoints:**
```javascript
// Forward shader requests to backend with headers
router.get('/api/launchbox/shaders/available', async (req, res) => {
  const response = await fetch(`${BACKEND_URL}/api/launchbox/shaders/available`, {
    headers: {
      'x-scope': req.headers['x-scope'],
      'x-device-id': req.headers['x-device-id']
    }
  })
  res.json(await response.json())
})

// Repeat for other shader endpoints: /game/{id}, /preview, /apply, /revert
```

---

#### **Task 1.3: LoRa AI Tool Integration** (30 min)
**File:** `gateway/routes/launchboxAI.js`

**Location:** Lines 234-241 (existing tools array)

**Add new tool:**
```javascript
{
  name: "set_game_shader",
  description: "Apply visual shader preset to specific game (CRT scanlines, LCD grid, sharp pixels, etc.)",
  parameters: {
    type: "object",
    properties: {
      game_id: { type: "string", description: "LaunchBox game ID" },
      shader_name: {
        type: "string",
        description: "Shader preset name (e.g., 'crt-royale', 'lcd-grid', 'sharp-bilinear')"
      },
      emulator: {
        type: "string",
        enum: ["mame", "retroarch"],
        description: "Target emulator for shader application"
      }
    },
    required: ["game_id", "shader_name", "emulator"]
  }
}
```

**Tool Execution Handler:**
Add to `executeToolCallingLoop()` function (lines 284-420):

```javascript
case 'set_game_shader':
  // Step 1: Get preview
  const previewResponse = await fetch(`${BACKEND_URL}/api/launchbox/shaders/preview`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json', ...req.headers },
    body: JSON.stringify(args)
  })
  const preview = await previewResponse.json()

  // Step 2: Return preview to AI for user confirmation
  toolResults.push({
    tool_use_id: toolUse.id,
    type: "tool_result",
    content: JSON.stringify({
      status: "preview_ready",
      diff: preview.diff,
      message: "Shader preview ready. Ask user to confirm before applying."
    })
  })
  break
```

**System Prompt Update:**
Add to LoRa's system prompt (lines 185-233):

```javascript
SHADER MANAGEMENT:
- You can apply visual shader presets to games using the set_game_shader tool
- Common shaders: crt-royale (CRT scanlines), lcd-grid (LCD matrix), sharp-bilinear (crisp pixels)
- MAME uses HLSL/BGFX shaders (.fx files)
- RetroArch uses Slang/GLSL shaders (.slangp files)
- Always show preview before applying
- Explain what the shader will do visually (e.g., "adds CRT scanlines and phosphor glow")
```

---

#### **Task 1.4: Frontend Shader Preview UI** (60 min)
**File:** `frontend/src/panels/launchbox/LaunchBoxPanel.jsx`

**Step 1: Add State**
```javascript
const [shaderPreview, setShaderPreview] = useState(null)
const [pendingShaderApply, setPendingShaderApply] = useState(null)
```

**Step 2: Import Components**
```javascript
import { DiffPreview } from '../_kit/DiffPreview'
import { ApplyBar } from '../_kit/ApplyBar'
```

**Step 3: Detect Shader Preview in Chat**
When LoRa's response includes shader preview:

```javascript
// In handleSendMessage where you process AI responses
if (loraResponse.includes("Shader preview ready")) {
  // Extract game_id and shader_name from conversation context
  const shaderData = extractShaderData(loraResponse)
  setShaderPreview(shaderData.diff)
  setPendingShaderApply(shaderData)
}
```

**Step 4: Render Preview UI**
```jsx
{shaderPreview && (
  <div className="shader-preview-container">
    <DiffPreview
      title="Shader Configuration Change"
      oldContent={shaderPreview.old}
      newContent={shaderPreview.new}
    />
    <ApplyBar
      onApply={async () => {
        const response = await fetch('/api/launchbox/shaders/apply', {
          method: 'POST',
          headers: {
            'Content-Type': 'application/json',
            'x-scope': 'config',
            'x-device-id': deviceId
          },
          body: JSON.stringify(pendingShaderApply)
        })
        const result = await response.json()

        // Add to chat: "Shader applied! Backup: {backup_path}"
        addMessage(`✅ Shader applied successfully. Backup saved at ${result.backup_path}`, 'assistant')
        setShaderPreview(null)
        setPendingShaderApply(null)
      }}
      onCancel={() => {
        setShaderPreview(null)
        setPendingShaderApply(null)
        addMessage("Shader change cancelled.", 'assistant')
      }}
    />
  </div>
)}
```

---

#### **Task 1.5: Testing Shader Management** (30 min)

**Test Cases:**
1. **Happy Path:**
   - User: "LoRa, add CRT scanlines to Street Fighter 2"
   - LoRa: Shows preview of shader config
   - User: Clicks Apply
   - Result: `configs/shaders/games/sf2.json` created with backup

2. **Shader List:**
   - User: "What shaders are available?"
   - LoRa: Calls `/shaders/available`, lists MAME and RetroArch shaders

3. **Current Shader:**
   - User: "What shader is on Mortal Kombat?"
   - LoRa: Calls `/shaders/game/mk`, returns current shader or "none"

4. **Revert:**
   - User: "I don't like this shader, go back"
   - LoRa: Calls `/shaders/revert` with last backup_path

**Validation:**
- ✅ Preview shows old vs new config
- ✅ Apply creates backup in `backups/YYYYMMDD/`
- ✅ Change logged in `logs/changes.jsonl`
- ✅ Game launches with new shader applied
- ✅ Revert restores previous config

---

### **Feature 2: Hotkey Launcher (F9 Global Overlay)** ⏱️ 3-4 hours

**Objective:** Implement global F9 hotkey that shows Arcade Assistant overlay with auto-activated microphone for hands-free interaction during gameplay.

#### **Task 2.1: Backend Hotkey Service** (90 min)
**New File:** `backend/services/hotkey_manager.py`

**Dependencies:**
```bash
pip install keyboard  # Global hotkey detection
```

**Implementation:**
```python
import keyboard
import asyncio
from typing import Callable, Optional
import logging

logger = logging.getLogger(__name__)

class HotkeyManager:
    """Manages global hotkey registration for F9 overlay activation."""

    def __init__(self):
        self.hotkey = "F9"  # Configurable via .env
        self.callback: Optional[Callable] = None
        self.is_active = False

    def register(self, callback: Callable):
        """Register F9 hotkey with callback function."""
        self.callback = callback

        try:
            keyboard.on_press_key(self.hotkey, self._on_hotkey_pressed)
            self.is_active = True
            logger.info(f"[Hotkey] Registered {self.hotkey} for overlay activation")
        except Exception as e:
            logger.error(f"[Hotkey] Failed to register {self.hotkey}: {e}")
            self.is_active = False

    def _on_hotkey_pressed(self, event):
        """Handle F9 key press."""
        if self.callback and self.is_active:
            logger.info(f"[Hotkey] {self.hotkey} pressed - triggering overlay")
            asyncio.create_task(self.callback())

    def unregister(self):
        """Unregister hotkey on shutdown."""
        if self.is_active:
            keyboard.unhook_key(self.hotkey)
            self.is_active = False
            logger.info(f"[Hotkey] Unregistered {self.hotkey}")

# Global instance
hotkey_manager = HotkeyManager()
```

---

#### **Task 2.2: Backend Hotkey Router** (30 min)
**New File:** `backend/routers/hotkey.py`

```python
from fastapi import APIRouter, WebSocket, WebSocketDisconnect
from backend.services.hotkey_manager import hotkey_manager
import logging

router = APIRouter(prefix="/api/hotkey", tags=["hotkey"])
logger = logging.getLogger(__name__)

# WebSocket connection for real-time hotkey events
active_connections: list[WebSocket] = []

@router.websocket("/ws")
async def hotkey_websocket(websocket: WebSocket):
    """WebSocket endpoint for hotkey event streaming."""
    await websocket.accept()
    active_connections.append(websocket)
    logger.info("[Hotkey WS] Client connected")

    try:
        while True:
            # Keep connection alive
            await websocket.receive_text()
    except WebSocketDisconnect:
        active_connections.remove(websocket)
        logger.info("[Hotkey WS] Client disconnected")

async def broadcast_hotkey_event():
    """Send hotkey event to all connected clients."""
    for connection in active_connections:
        try:
            await connection.send_json({"type": "hotkey_pressed", "key": "F9"})
        except Exception as e:
            logger.error(f"[Hotkey WS] Failed to send event: {e}")

# Register hotkey on startup
@router.on_event("startup")
async def startup_event():
    if os.getenv("V2_HOTKEY_LAUNCHER") == "true":
        hotkey_manager.register(broadcast_hotkey_event)
        logger.info("[Hotkey] F9 launcher enabled")

@router.on_event("shutdown")
async def shutdown_event():
    hotkey_manager.unregister()
```

**Register in `backend/app.py`:**
```python
from backend.routers import hotkey
app.include_router(hotkey.router)
```

---

#### **Task 2.3: Frontend Global Overlay Component** (90 min)
**New File:** `frontend/src/components/GlobalOverlay.jsx`

```jsx
import { useState, useEffect, useRef } from 'react'
import './GlobalOverlay.css'

const SILENCE_THRESHOLD = -50  // Same as Gunner/Sam
const SILENCE_DURATION = 350   // Same as Gunner/Sam

export function GlobalOverlay({ onClose }) {
  const [isRecording, setIsRecording] = useState(false)
  const [transcript, setTranscript] = useState('')
  const [response, setResponse] = useState('')

  const mediaRecorderRef = useRef(null)
  const audioContextRef = useRef(null)
  const analyserRef = useRef(null)
  const silenceTimerRef = useRef(null)

  // Auto-activate mic on mount
  useEffect(() => {
    startRecording()
    return () => cleanup()
  }, [])

  const startRecording = async () => {
    try {
      const stream = await navigator.mediaDevices.getUserMedia({ audio: true })

      // Start MediaRecorder for STT
      const mediaRecorder = new MediaRecorder(stream)
      mediaRecorderRef.current = mediaRecorder

      const chunks = []
      mediaRecorder.ondataavailable = (e) => chunks.push(e.data)
      mediaRecorder.onstop = async () => {
        const audioBlob = new Blob(chunks, { type: 'audio/webm' })
        await sendToSTT(audioBlob)
      }

      mediaRecorder.start()
      setIsRecording(true)

      // Start VAD for auto-stop
      startVAD(stream)
    } catch (err) {
      console.error('[Overlay] Mic access failed:', err)
    }
  }

  const startVAD = (stream) => {
    try {
      const audioContext = new (window.AudioContext || window.webkitAudioContext)()
      const analyser = audioContext.createAnalyser()
      const microphone = audioContext.createMediaStreamSource(stream)

      analyser.fftSize = 512
      analyser.smoothingTimeConstant = 0.8
      microphone.connect(analyser)

      audioContextRef.current = audioContext
      analyserRef.current = analyser

      // Check audio level every 100ms
      silenceTimerRef.current = setInterval(() => {
        const dataArray = new Uint8Array(analyser.frequencyBinCount)
        analyser.getByteFrequencyData(dataArray)

        const average = dataArray.reduce((a, b) => a + b) / dataArray.length
        const dB = 20 * Math.log10(average / 255)

        if (dB < SILENCE_THRESHOLD) {
          const now = Date.now()
          const silenceDuration = now - (window.lastSoundTime || now)

          if (silenceDuration > SILENCE_DURATION) {
            console.log('[Overlay] Silence detected, stopping recording')
            stopRecording()
          }
        } else {
          window.lastSoundTime = Date.now()
        }
      }, 100)
    } catch (err) {
      console.warn('[Overlay] VAD setup failed:', err)
    }
  }

  const stopRecording = () => {
    if (mediaRecorderRef.current && isRecording) {
      mediaRecorderRef.current.stop()
      setIsRecording(false)
      cleanup()
    }
  }

  const cleanup = () => {
    if (silenceTimerRef.current) clearInterval(silenceTimerRef.current)
    if (audioContextRef.current) audioContextRef.current.close()
    if (mediaRecorderRef.current) {
      mediaRecorderRef.current.stream.getTracks().forEach(t => t.stop())
    }
  }

  const sendToSTT = async (audioBlob) => {
    // Send to backend STT (reuse existing Whisper integration)
    const formData = new FormData()
    formData.append('audio', audioBlob)

    const response = await fetch('/api/voice/transcribe', {
      method: 'POST',
      body: formData
    })
    const { text } = await response.json()
    setTranscript(text)

    // Send to Dewey AI
    await sendToDewey(text)
  }

  const sendToDewey = async (text) => {
    const response = await fetch('/api/ai/chat', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        messages: [{ role: 'user', content: text }],
        panel: 'dewey'
      })
    })
    const data = await response.json()
    setResponse(data.response)

    // Speak response with TTS
    speakResponse(data.response)

    // Auto-dismiss after 3 seconds
    setTimeout(() => onClose(), 3000)
  }

  const speakResponse = async (text) => {
    const response = await fetch('/api/voice/tts', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ text, voice_id: 'dewey' })
    })
    const audioBlob = await response.blob()
    const audio = new Audio(URL.createObjectURL(audioBlob))
    audio.play()
  }

  return (
    <div className="global-overlay">
      <div className="overlay-content">
        <img src="/dewey-avatar.jpeg" alt="Dewey" className="overlay-avatar" />

        {isRecording && (
          <div className="overlay-status">
            <div className="waveform">🎤 Listening...</div>
          </div>
        )}

        {transcript && (
          <div className="overlay-transcript">
            <strong>You:</strong> {transcript}
          </div>
        )}

        {response && (
          <div className="overlay-response">
            <strong>Dewey:</strong> {response}
          </div>
        )}

        <button onClick={onClose} className="overlay-close">✕</button>
      </div>
    </div>
  )
}
```

**CSS File:** `frontend/src/components/GlobalOverlay.css`
```css
.global-overlay {
  position: fixed;
  top: 0;
  left: 0;
  right: 0;
  bottom: 0;
  background: rgba(0, 0, 0, 0.8);
  display: flex;
  align-items: center;
  justify-content: center;
  z-index: 9999;
  animation: fadeIn 0.2s ease-in;
}

.overlay-content {
  background: linear-gradient(135deg, #1a1a2e 0%, #16213e 100%);
  border: 2px solid #00e5ff;
  border-radius: 16px;
  padding: 32px;
  max-width: 600px;
  box-shadow: 0 0 40px rgba(0, 229, 255, 0.4);
  position: relative;
}

.overlay-avatar {
  width: 80px;
  height: 80px;
  border-radius: 50%;
  border: 3px solid #00e5ff;
  margin-bottom: 16px;
}

.overlay-status, .overlay-transcript, .overlay-response {
  color: #fff;
  margin: 12px 0;
  font-size: 16px;
}

.waveform {
  color: #c8ff00;
  font-weight: bold;
  animation: pulse 1.5s infinite;
}

.overlay-close {
  position: absolute;
  top: 12px;
  right: 12px;
  background: transparent;
  border: none;
  color: #fff;
  font-size: 24px;
  cursor: pointer;
}

@keyframes fadeIn {
  from { opacity: 0; }
  to { opacity: 1; }
}

@keyframes pulse {
  0%, 100% { opacity: 1; }
  50% { opacity: 0.5; }
}
```

---

#### **Task 2.4: Integrate Overlay into Main App** (30 min)
**File:** `frontend/src/App.jsx`

```jsx
import { useState, useEffect } from 'react'
import { GlobalOverlay } from './components/GlobalOverlay'

function App() {
  const [showOverlay, setShowOverlay] = useState(false)

  useEffect(() => {
    // Connect to hotkey WebSocket
    if (import.meta.env.VITE_V2_HOTKEY_LAUNCHER === 'true') {
      const ws = new WebSocket('ws://localhost:8888/api/hotkey/ws')

      ws.onmessage = (event) => {
        const data = JSON.parse(event.data)
        if (data.type === 'hotkey_pressed') {
          console.log('[App] F9 hotkey pressed, showing overlay')
          setShowOverlay(true)
        }
      }

      return () => ws.close()
    }
  }, [])

  return (
    <>
      {/* Existing app content */}

      {showOverlay && (
        <GlobalOverlay onClose={() => setShowOverlay(false)} />
      )}
    </>
  )
}
```

---

#### **Task 2.5: Testing Hotkey Launcher** (30 min)

**Test Cases:**
1. **F9 Activation:**
   - Start MAME game (Street Fighter 2)
   - Press F9 during gameplay
   - Result: Overlay appears, mic auto-activates, game stays focused

2. **Voice Input:**
   - Overlay visible, mic recording
   - User: "What's my high score on this game?"
   - Result: VAD detects silence, stops recording, transcribes, sends to Dewey

3. **Auto-Dismiss:**
   - Dewey responds with TTS
   - Result: Overlay fades out after 3 seconds, game resumes

4. **Manual Close:**
   - User clicks X button
   - Result: Overlay closes immediately

**Validation:**
- ✅ F9 detected during gameplay
- ✅ Overlay appears within 200ms
- ✅ Mic auto-activates without button press
- ✅ VAD stops recording after 350ms silence
- ✅ Dewey responds with voice
- ✅ Overlay auto-dismisses
- ✅ Game never loses focus

---

### **Feature 3: Cabinet Duplication Documentation** ⏱️ 1 hour

**Objective:** Create comprehensive guide for cloning A: drive to duplicate arcade cabinets.

#### **Task 3.1: Create Duplication Guide** (60 min)
**New File:** `docs/CABINET_DUPLICATION_GUIDE.md`

```markdown
# Cabinet Duplication Guide

## Overview
Duplicate your entire Arcade Assistant system by cloning the A: drive. This enables rapid deployment of multiple arcade cabinets with per-cabinet customization.

## Prerequisites
- Source Cabinet: Fully configured A: drive with tested games/settings
- Target Drive: Empty drive (same size or larger than A:)
- Cloning Tool: Clonezilla, Macrium Reflect, or dd (Linux)

## Step 1: Prepare Source Cabinet

### 1.1 Verify A: Drive Paths
All components should be on A: drive:
- `A:\LaunchBox` - Game metadata and launcher
- `A:\Roms\` - 14,233+ MAME ROMs
- `A:\Bios\system\` - 586 BIOS files
- `A:\Emulators\` - RetroArch, MAME, Dolphin, etc.

**Verify paths:**
```bash
# Check backend constants match
cat backend/constants/a_drive_paths.py

# Expected output:
# AA_DRIVE_ROOT = 'A:\\'
# LAUNCHBOX_ROOT = Path(AA_DRIVE_ROOT) / "LaunchBox"
```

### 1.2 Test All Systems
Before cloning, verify everything works:
- ✅ Launch 5 different games (MAME, RetroArch, Dolphin)
- ✅ Test all 9 AI assistants (Dewey, LoRa, Chuck, etc.)
- ✅ Verify LED Blinky lights work
- ✅ Test light guns (if applicable)
- ✅ Run shader management (if V2 enabled)

### 1.3 Create Baseline Backup
```bash
# Create master backup before cloning
# Location: A:\backups\MASTER_YYYYMMDD\
```

## Step 2: Clone A: Drive

### Option A: Clonezilla (Recommended)
1. Boot from Clonezilla USB
2. Select "device-device" mode
3. Source: A: drive
4. Target: New drive
5. Clone all partitions
6. Verify completion (checksum validation)

### Option B: Macrium Reflect (Windows)
1. Launch Macrium Reflect
2. Select A: drive
3. "Clone this disk..."
4. Target: New drive
5. Run clone operation
6. Verify completion

### Option C: dd (Linux/WSL)
```bash
# Identify drives
lsblk

# Clone (WARNING: verify /dev/sdX paths!)
sudo dd if=/dev/sda of=/dev/sdb bs=4M status=progress

# Verify
sudo cmp /dev/sda /dev/sdb
```

**Duration:** ~30 minutes for typical arcade drive

## Step 3: Per-Cabinet Customization

### 3.1 Swap Drive into New Cabinet
- Remove cloned drive from source machine
- Install in target cabinet
- Boot cabinet, verify A: drive mounts

### 3.2 Update Cabinet Identity
**File:** `A:\configs\cabinet.json`

```json
{
  "cabinet_id": "CABINET_02",
  "cabinet_name": "Street Fighter Cabinet",
  "location": "Game Room - Right Side",
  "supabase_device_id": null,  // Will auto-register on first boot
  "hardware_profile": "standard_4_player"
}
```

### 3.3 Customize LED Profiles
**Directory:** `A:\configs\ledblinky\profiles\`

Cabinet 1 (Fighting Games): Red/Blue aggressive colors
```json
{
  "profile_name": "fighting_theme",
  "p1_button1": "#FF0000",
  "p1_button2": "#0000FF"
}
```

Cabinet 2 (Classic Arcade): Yellow/Green retro colors
```json
{
  "profile_name": "retro_theme",
  "p1_button1": "#C8FF00",
  "p1_button2": "#00FF00"
}
```

### 3.4 Adjust Controller Mappings
**File:** `A:\configs\controllers\controls.json`

If using different encoder boards per cabinet:
```json
{
  "cabinet_id": "CABINET_02",
  "encoder_type": "ultimarc_ipac4",  // vs "ultimarc_ipac2" on Cabinet 1
  "mappings": {
    "p1_button1": { "pin": "1SW1", "device": "ipac4_1" }
  }
}
```

### 3.5 Set Shader Preferences (V2)
**Directory:** `A:\configs\shaders\cabinet_defaults\`

Cabinet 1 (CRT Monitor): Heavy scanlines
```json
{
  "default_shader": "crt-royale",
  "scanline_intensity": 0.9
}
```

Cabinet 2 (LCD Monitor): Light scanlines
```json
{
  "default_shader": "crt-easy",
  "scanline_intensity": 0.3
}
```

### 3.6 Register with Supabase (Optional)
First boot auto-registers cabinet:
```bash
# Backend logs will show:
[Supabase] Registering new cabinet: CABINET_02
[Supabase] Device ID: abc123def456
[Supabase] JWT saved to state/supabase/device.jwt
```

## Step 4: Validation

### 4.1 Verify File Integrity
```bash
# Check critical files exist
dir A:\LaunchBox\LaunchBox.exe
dir A:\Roms\MAME\sf2.zip
dir A:\configs\cabinet.json
```

### 4.2 Test Game Launch
- Launch Street Fighter 2 from LaunchBox
- Verify ROM loads, controls work, LED lights up

### 4.3 Test AI Assistants
- Open Dewey panel: "Hey Dewey, what cabinet am I on?"
- Expected: "You're on CABINET_02 - Street Fighter Cabinet"

### 4.4 Compare Configs
**Tool (Future):** Cabinet Profile Manager
- Side-by-side diff of Cabinet 1 vs Cabinet 2 configs
- Highlight differences in LED profiles, controller mappings, shaders

## Step 5: Labeling & Inventory

### 5.1 Physical Labels
Label drives clearly:
- `A_CABINET_01_MASTER` (source)
- `A_CABINET_02_SF` (clone 1)
- `A_CABINET_03_RACING` (clone 2)

### 5.2 Inventory Spreadsheet
Track all cabinets:

| Cabinet ID | Name | Location | Hardware | Last Clone | Notes |
|-----------|------|----------|----------|-----------|-------|
| CABINET_01 | Master | Workshop | I-PAC2 | 2025-12-01 | Source for all clones |
| CABINET_02 | Street Fighter | Game Room Right | I-PAC4 | 2025-12-01 | Red/Blue LED theme |
| CABINET_03 | Racing | Game Room Left | Ultimarc ServoStik | 2025-12-05 | Steering wheel mounted |

## Troubleshooting

### Issue: Cabinet ID not updating
**Symptom:** New cabinet still thinks it's CABINET_01
**Fix:** Manually edit `A:\configs\cabinet.json`

### Issue: Supabase registration fails
**Symptom:** "Device already registered" error
**Fix:** Delete `state/supabase/device.jwt`, restart backend

### Issue: LED colors wrong for cabinet
**Symptom:** Cabinet 2 using Cabinet 1's LED profile
**Fix:** Check `configs/ledblinky/profiles/active.json` points to correct profile

### Issue: Shaders not loading
**Symptom:** Games launch but no shader applied
**Fix:** Verify `A:\Emulators\MAME\shaders\` and `A:\Emulators\RetroArch\shaders\` copied correctly

## Advanced: Config Drift Prevention

### Baseline Snapshot
After configuring Cabinet 1 (master):
```bash
# Create git repo of configs (optional)
cd A:\configs
git init
git add .
git commit -m "CABINET_01 baseline - 2025-12-01"
```

### Compare Cabinets
```bash
# After customizing Cabinet 2
cd A:\configs
git diff CABINET_01..CABINET_02
```

### Sync Updates
If you improve Cabinet 1's config later:
1. Clone just the `configs/` directory (not entire drive)
2. Apply to Cabinet 2 with merge strategy
3. Preserve Cabinet 2's custom LED/shader preferences

## Future Enhancements

- **GUI Wizard:** Point-and-click cabinet cloning
- **Automated Diff Tool:** Compare configs across cabinets
- **Remote Sync:** Push config updates via Supabase
- **Template System:** Base config + per-cabinet overrides

---

**Last Updated:** 2025-12-01
**Author:** Arcade Assistant Team
**Questions?** See `docs/ARCHITECTURE.md` or ask Dewey!
```

---

## **Day 1 Completion Checklist**

After 6-8 hours, you should have:
- ✅ Shader Management: LoRa can set per-game shaders with preview/apply/revert
- ✅ Hotkey Launcher: F9 shows overlay with auto-mic and VAD
- ✅ Cabinet Duplication Docs: Complete guide for A: drive cloning

**Feature Flags to Enable:**
```bash
# .env
V2_SHADER_MANAGEMENT=true
V2_HOTKEY_LAUNCHER=true
```

**Testing Command:**
```bash
# Start dev stack
npm run dev

# Test shader management
# 1. Open LaunchBox LoRa panel
# 2. Ask: "Add CRT scanlines to Street Fighter 2"
# 3. Verify preview shows, apply works, backup created

# Test hotkey launcher
# 1. Launch MAME game
# 2. Press F9
# 3. Verify overlay appears, mic auto-activates
# 4. Say: "What's my high score?"
# 5. Verify Dewey responds, overlay auto-dismisses
```

---

## **Day 2: Completion + Polish (6-8 hours)**

### **Feature 4: Custom Pause Screen** ⏱️ 4-5 hours

**Objective:** Implement custom pause overlay for direct-launched games (MAME, RetroArch) independent of LaunchBox.

#### **Task 4.1: Backend Process Detection** (120 min)

**New File:** `backend/services/process_monitor.py`

**Dependencies:**
```bash
pip install psutil
```

**Implementation:**
```python
import psutil
import re
from pathlib import Path
from typing import Optional, Dict
import logging

logger = logging.getLogger(__name__)

class ProcessMonitor:
    """Monitor running emulator processes and extract game metadata."""

    EMULATOR_PATTERNS = {
        'mame': r'mame\.exe.*?([a-z0-9_]+)\.zip',
        'retroarch': r'retroarch\.exe.*?"([^"]+)"',
        'dolphin': r'Dolphin\.exe.*?"([^"]+)"',
        'duckstation': r'duckstation-qt-x64\.exe.*?"([^"]+)"'
    }

    def __init__(self, launchbox_cache):
        self.launchbox_cache = launchbox_cache  # Access to game metadata
        self.active_game: Optional[Dict] = None

    def detect_running_game(self) -> Optional[Dict]:
        """Detect currently running game from emulator process."""
        for proc in psutil.process_iter(['name', 'cmdline']):
            try:
                proc_name = proc.info['name'].lower()
                cmdline = ' '.join(proc.info['cmdline'])

                # Check each emulator pattern
                for emulator, pattern in self.EMULATOR_PATTERNS.items():
                    if emulator in proc_name:
                        match = re.search(pattern, cmdline, re.IGNORECASE)
                        if match:
                            rom_name = match.group(1)
                            return self._lookup_game_metadata(rom_name, emulator)

            except (psutil.NoSuchProcess, psutil.AccessDenied):
                continue

        return None

    def _lookup_game_metadata(self, rom_name: str, emulator: str) -> Dict:
        """Lookup game metadata from LaunchBox cache."""
        # Search LaunchBox cache by ROM filename
        game = self.launchbox_cache.find_by_rom(rom_name)

        if game:
            return {
                'id': game['id'],
                'title': game['title'],
                'platform': game['platform'],
                'genre': game['genre'],
                'year': game['year'],
                'emulator': emulator,
                'rom_name': rom_name,
                'box_art': game.get('box_art_url'),
                'play_count': game.get('play_count', 0),
                'last_played': game.get('last_played')
            }
        else:
            # Fallback: basic info from ROM name
            return {
                'id': rom_name,
                'title': rom_name.replace('_', ' ').title(),
                'platform': 'Unknown',
                'genre': 'Unknown',
                'year': 0,
                'emulator': emulator,
                'rom_name': rom_name,
                'box_art': None,
                'play_count': 0,
                'last_played': None
            }

    def is_game_running(self) -> bool:
        """Check if any emulator process is running."""
        return self.detect_running_game() is not None

# Global instance
process_monitor = ProcessMonitor(launchbox_cache=None)  # Inject cache on startup
```

---

#### **Task 4.2: Backend Pause Screen Router** (30 min)

**New File:** `backend/routers/pause_screen.py`

```python
from fastapi import APIRouter
from backend.services.process_monitor import process_monitor
import logging

router = APIRouter(prefix="/api/pause", tags=["pause"])
logger = logging.getLogger(__name__)

@router.get("/current-game")
async def get_current_game():
    """Get metadata for currently running game."""
    game = process_monitor.detect_running_game()

    if game:
        logger.info(f"[Pause] Detected running game: {game['title']}")
        return game
    else:
        logger.info("[Pause] No game currently running")
        return {"error": "No game detected", "status": "idle"}

@router.get("/system-stats")
async def get_system_stats():
    """Get real-time system stats for pause overlay."""
    import psutil

    return {
        "cpu_percent": psutil.cpu_percent(interval=0.1),
        "memory_percent": psutil.virtual_memory().percent,
        "fps": 60,  # TODO: Hook into emulator FPS if available
        "gpu_temp": None  # TODO: GPU monitoring if available
    }
```

**Register in `backend/app.py`:**
```python
from backend.routers import pause_screen
app.include_router(pause_screen.router)
```

---

#### **Task 4.3: Frontend Pause Overlay Component** (120 min)

**New File:** `frontend/src/components/PauseOverlay.jsx`

```jsx
import { useState, useEffect } from 'react'
import './PauseOverlay.css'

export function PauseOverlay({ onResume, onExit }) {
  const [gameData, setGameData] = useState(null)
  const [stats, setStats] = useState(null)
  const [showVoice, setShowVoice] = useState(false)

  useEffect(() => {
    fetchGameData()
    fetchStats()

    // Update stats every 2 seconds
    const interval = setInterval(fetchStats, 2000)
    return () => clearInterval(interval)
  }, [])

  const fetchGameData = async () => {
    const response = await fetch('/api/pause/current-game')
    const data = await response.json()
    setGameData(data)
  }

  const fetchStats = async () => {
    const response = await fetch('/api/pause/system-stats')
    const data = await response.json()
    setStats(data)
  }

  return (
    <div className="pause-overlay">
      <div className="pause-content">
        {/* Game Info */}
        {gameData && (
          <div className="pause-game-info">
            {gameData.box_art && (
              <img src={gameData.box_art} alt={gameData.title} className="pause-box-art" />
            )}
            <div className="pause-game-details">
              <h1>{gameData.title}</h1>
              <p className="pause-platform">{gameData.platform} • {gameData.year}</p>
              <p className="pause-genre">{gameData.genre}</p>
              <p className="pause-stats">
                Played {gameData.play_count} times
                {gameData.last_played && ` • Last: ${new Date(gameData.last_played).toLocaleDateString()}`}
              </p>
            </div>
          </div>
        )}

        {/* System Stats */}
        {stats && (
          <div className="pause-system-stats">
            <div className="stat-item">
              <span className="stat-label">CPU</span>
              <span className="stat-value">{stats.cpu_percent.toFixed(1)}%</span>
            </div>
            <div className="stat-item">
              <span className="stat-label">RAM</span>
              <span className="stat-value">{stats.memory_percent.toFixed(1)}%</span>
            </div>
            <div className="stat-item">
              <span className="stat-label">FPS</span>
              <span className="stat-value">{stats.fps}</span>
            </div>
          </div>
        )}

        {/* Action Buttons */}
        <div className="pause-actions">
          <button onClick={onResume} className="pause-btn pause-btn-primary">
            ▶ Resume Game
          </button>
          <button onClick={() => setShowVoice(true)} className="pause-btn pause-btn-secondary">
            💬 Talk to Dewey
          </button>
          <button onClick={onExit} className="pause-btn pause-btn-danger">
            🚪 Exit Game
          </button>
        </div>

        {/* Voice Panel (if activated) */}
        {showVoice && (
          <div className="pause-voice-panel">
            <button className="pause-voice-mic">🎤</button>
            <p className="pause-voice-hint">Press to ask Dewey a question</p>
          </div>
        )}
      </div>
    </div>
  )
}
```

**CSS File:** `frontend/src/components/PauseOverlay.css`

```css
.pause-overlay {
  position: fixed;
  top: 0;
  left: 0;
  right: 0;
  bottom: 0;
  background: rgba(0, 0, 0, 0.95);
  display: flex;
  align-items: center;
  justify-content: center;
  z-index: 9999;
  animation: fadeIn 0.3s ease-in;
}

.pause-content {
  max-width: 800px;
  background: linear-gradient(135deg, #1a1a2e 0%, #16213e 100%);
  border: 3px solid #00e5ff;
  border-radius: 20px;
  padding: 40px;
  box-shadow: 0 0 60px rgba(0, 229, 255, 0.6);
}

.pause-game-info {
  display: flex;
  gap: 24px;
  margin-bottom: 32px;
}

.pause-box-art {
  width: 200px;
  height: 280px;
  object-fit: cover;
  border-radius: 12px;
  border: 2px solid #00e5ff;
}

.pause-game-details h1 {
  color: #fff;
  font-size: 32px;
  margin-bottom: 8px;
}

.pause-platform, .pause-genre, .pause-stats {
  color: #d1d5db;
  margin: 4px 0;
}

.pause-system-stats {
  display: flex;
  gap: 32px;
  justify-content: center;
  margin-bottom: 32px;
  padding: 16px;
  background: rgba(0, 229, 255, 0.1);
  border-radius: 12px;
}

.stat-item {
  display: flex;
  flex-direction: column;
  align-items: center;
}

.stat-label {
  color: #00e5ff;
  font-size: 14px;
  text-transform: uppercase;
}

.stat-value {
  color: #c8ff00;
  font-size: 28px;
  font-weight: bold;
}

.pause-actions {
  display: flex;
  gap: 16px;
  justify-content: center;
}

.pause-btn {
  padding: 16px 32px;
  font-size: 18px;
  border: none;
  border-radius: 8px;
  cursor: pointer;
  transition: all 0.2s;
}

.pause-btn-primary {
  background: linear-gradient(135deg, #00e5ff 0%, #0099cc 100%);
  color: #000;
}

.pause-btn-secondary {
  background: linear-gradient(135deg, #c8ff00 0%, #99cc00 100%);
  color: #000;
}

.pause-btn-danger {
  background: linear-gradient(135deg, #ff4444 0%, #cc0000 100%);
  color: #fff;
}

.pause-btn:hover {
  transform: translateY(-2px);
  box-shadow: 0 4px 12px rgba(0, 0, 0, 0.3);
}

@keyframes fadeIn {
  from { opacity: 0; }
  to { opacity: 1; }
}
```

---

#### **Task 4.4: Integrate Pause Screen Hotkey** (30 min)

**File:** `backend/services/hotkey_manager.py` (extend existing)

Add pause hotkey alongside F9:

```python
class HotkeyManager:
    def __init__(self):
        self.hotkey_overlay = "F9"   # Existing
        self.hotkey_pause = "P"      # NEW: Pause screen

    def register_pause_hotkey(self, callback: Callable):
        """Register P key for pause screen."""
        try:
            keyboard.on_press_key(self.hotkey_pause, lambda e: callback())
            logger.info(f"[Hotkey] Registered {self.hotkey_pause} for pause screen")
        except Exception as e:
            logger.error(f"[Hotkey] Failed to register {self.hotkey_pause}: {e}")
```

**File:** `frontend/src/App.jsx` (extend existing)

```jsx
const [showPauseOverlay, setShowPauseOverlay] = useState(false)

useEffect(() => {
  // Existing F9 WebSocket...

  // NEW: P key WebSocket for pause
  if (import.meta.env.VITE_V2_CUSTOM_PAUSE === 'true') {
    const pauseWs = new WebSocket('ws://localhost:8888/api/hotkey/pause-ws')

    pauseWs.onmessage = (event) => {
      const data = JSON.parse(event.data)
      if (data.type === 'pause_pressed') {
        setShowPauseOverlay(true)
      }
    }

    return () => pauseWs.close()
  }
}, [])

return (
  <>
    {showOverlay && <GlobalOverlay onClose={() => setShowOverlay(false)} />}
    {showPauseOverlay && (
      <PauseOverlay
        onResume={() => setShowPauseOverlay(false)}
        onExit={() => {
          // TODO: Send exit command to emulator
          setShowPauseOverlay(false)
        }}
      />
    )}
  </>
)
```

---

#### **Task 4.5: Testing Custom Pause Screen** (30 min)

**Test Cases:**
1. **Launch MAME directly** (not via LaunchBox)
   ```bash
   A:\Emulators\MAME\mame.exe sf2
   ```
   - Press P key
   - Result: Pause overlay shows Street Fighter 2 metadata

2. **Launch RetroArch directly**
   ```bash
   A:\Emulators\RetroArch\retroarch.exe -L cores\snes9x_libretro.dll "A:\Roms\SNES\Super Mario World.sfc"
   ```
   - Press P key
   - Result: Pause overlay shows Super Mario World metadata

3. **Resume Game**
   - Click "Resume Game" button
   - Result: Overlay disappears, game continues

4. **Exit Game**
   - Click "Exit Game" button
   - Result: Emulator process terminates, overlay closes

5. **Talk to Dewey**
   - Click "Talk to Dewey" button
   - Result: Voice panel appears in pause overlay

**Validation:**
- ✅ Process detection identifies running game
- ✅ Metadata fetched from LaunchBox cache
- ✅ System stats update every 2 seconds
- ✅ P key triggers overlay (doesn't interfere with gameplay)
- ✅ Resume/Exit actions work correctly

---

### **Feature 5: Testing & Polish** ⏱️ 2-3 hours

#### **Task 5.1: Integration Testing** (90 min)

**Test Suite:**

1. **Shader + Hotkey Integration**
   - Launch Street Fighter 2 with CRT shader
   - Press F9 during gameplay
   - Ask: "Can you change this to sharp pixels?"
   - Verify: Dewey triggers shader change via LoRa tool calling

2. **Pause + Shader Integration**
   - Launch Mortal Kombat directly (not LaunchBox)
   - Press P for pause screen
   - Click "Talk to Dewey"
   - Ask: "Add LCD grid shader to this game"
   - Verify: Shader applied, pause screen updates

3. **Cabinet Duplication Verification**
   - Clone A: drive to USB drive
   - Boot from USB
   - Verify all features work identically
   - Test cabinet_id customization

4. **Feature Flag Verification**
   - Disable all V2 flags in .env
   - Verify V1 system works perfectly (no V2 interference)
   - Enable V2_SHADER_MANAGEMENT only
   - Verify shader tool works, hotkey/pause disabled

---

#### **Task 5.2: Performance Optimization** (30 min)

**Metrics to Check:**

1. **Shader Application Speed**
   - Target: <100ms from LoRa tool call to config written
   - Measure: Add timing logs in backend shader endpoints

2. **Hotkey Response Latency**
   - Target: <200ms from F9 press to overlay visible
   - Measure: Console.time() in frontend WebSocket handler

3. **Pause Screen Load Time**
   - Target: <150ms from P press to overlay visible
   - Measure: Process detection + metadata lookup timing

4. **Memory Footprint**
   - Verify no memory leaks from overlay open/close cycles
   - Test: Open/close overlay 50 times, check RAM usage

---

#### **Task 5.3: Error Handling** (30 min)

**Edge Cases to Handle:**

1. **Shader file missing**
   - User asks for "crt-royale" but file doesn't exist
   - LoRa should: List available shaders, suggest closest match

2. **Hotkey WebSocket disconnect**
   - Backend crashes, WebSocket drops
   - Frontend should: Show warning, fallback to button activation

3. **Process detection fails**
   - Pause screen can't identify running game
   - Overlay should: Show generic "Unknown Game" with stats only

4. **Concurrent overlays**
   - User presses F9 then P (both overlays triggered)
   - App should: Close previous overlay before showing new one

---

#### **Task 5.4: Documentation Updates** (30 min)

**Update these files:**

1. **README.md** - Add V2 feature section
2. **CLAUDE.md** - Document new patterns (hotkey, pause screen)
3. **.env.example** - Add V2 feature flags with comments
4. **package.json** - Update version to 2.0.0

**Example .env.example update:**
```bash
# V2 Features (Optional - defaults to false)
V2_SHADER_MANAGEMENT=false    # Enable per-game shader management via LoRa
V2_HOTKEY_LAUNCHER=false      # Enable F9 global overlay with auto-mic
V2_CUSTOM_PAUSE=false         # Enable P key pause screen for direct launches
```

---

## **Day 2 Completion Checklist**

After 6-8 hours, you should have:
- ✅ Custom Pause Screen: P key shows overlay with game metadata and system stats
- ✅ Integration Testing: All V2 features work together seamlessly
- ✅ Performance Optimization: All latency targets met
- ✅ Error Handling: Edge cases covered with graceful degradation
- ✅ Documentation: README, CLAUDE.md, .env.example updated

**Feature Flags to Enable:**
```bash
# .env (full V2 suite)
V2_SHADER_MANAGEMENT=true
V2_HOTKEY_LAUNCHER=true
V2_CUSTOM_PAUSE=true
```

**Final Testing Command:**
```bash
# Full V2 workflow test
# 1. Start dev stack
npm run dev

# 2. Test shader management
#    - Ask LoRa: "Add CRT scanlines to Street Fighter 2"
#    - Verify preview, apply, backup created

# 3. Test hotkey launcher
#    - Launch Street Fighter 2 in MAME
#    - Press F9 during gameplay
#    - Ask: "What's my high score?"
#    - Verify Dewey responds, overlay auto-dismisses

# 4. Test pause screen
#    - Launch Mortal Kombat directly (bypass LaunchBox)
#    - Press P key
#    - Verify game metadata shown, stats updating
#    - Click "Talk to Dewey", ask about game
#    - Click Resume, verify game continues

# 5. Test cabinet duplication
#    - Clone A: drive to USB
#    - Edit configs/cabinet.json (CABINET_02)
#    - Boot from USB, verify all features work
```

---

## **Post-Implementation: V2 Go-Live**

### **Rollout Strategy**

**Week 1: Single Cabinet Testing**
- Enable all V2 features on primary cabinet
- Test for 7 days with real gameplay
- Log any issues in `logs/v2_issues.log`

**Week 2: Multi-Cabinet Deployment**
- Clone A: drive to 2-3 additional cabinets
- Customize per-cabinet configs (LED, shaders, controller)
- Verify each cabinet registers independently with Supabase

**Week 3: User Feedback Iteration**
- Collect user feedback on V2 features
- Prioritize bugs/enhancements
- Release V2.1 patch if needed

---

## **Success Metrics**

Track these metrics after V2 deployment:

### **Feature Adoption**
- % of games with custom shaders applied
- F9 hotkey usage vs button activation
- Pause screen usage (direct launches vs LaunchBox)
- Cabinet duplication success rate

### **Performance**
- Shader load time (target: <100ms)
- Hotkey latency (target: <200ms)
- Pause screen latency (target: <150ms)
- Memory footprint (target: <50MB overhead)

### **Stability**
- V2 feature crash rate (target: 0% for 30 days)
- Feature flag rollback frequency
- Integration test pass rate (target: 100%)

---

## **Future V3 Considerations**

**Not in V2 scope, but worth planning:**

1. **Advanced Shader Editor** - Visual parameter tweaking UI
2. **Remote Cabinet Sync** - Push config updates via Supabase
3. **Multi-Cabinet Dashboard** - Monitor all cabinets from single interface
4. **Cabinet Profile Manager** - Side-by-side config comparison tool
5. **Voice-Activated Pause** - "Hey Dewey, pause game" instead of P key
6. ~~**Wake Word Detection**~~ - REMOVED (impractical for noisy arcades)

---

**V2 Implementation Plan Last Updated:** 2025-12-01
**Total Estimated Time:** 12-16 hours (2 days)
**Risk Level:** LOW (feature flags + rollback mechanisms)
**Status:** Ready for implementation

---

## **Codex Task Assignment Template**

**When assigning tasks to Codex, use this format:**

```markdown
**Task:** [Feature Name] - [Specific Component]

**Context:**
[1-2 sentences explaining why this task matters]

**Files to Modify:**
- `path/to/file1.py` (lines X-Y)
- `path/to/file2.jsx` (new file)

**Step-by-Step Instructions:**
1. [First step with code example if needed]
2. [Second step]
3. [etc.]

**Expected Outcome:**
[What should work when this task is complete]

**Testing:**
[How to verify this task succeeded]

**Dependencies:**
[Any tasks that must complete first]
```

---

**Ready to start? Begin with Task 1.1: Backend Shader Endpoints**

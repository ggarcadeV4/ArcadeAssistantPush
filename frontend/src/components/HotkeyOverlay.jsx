import React, { useEffect, useState, useCallback, useRef } from 'react'
import { hotkeyClient } from '../services/hotkeyClient'
import './HotkeyOverlay.css'
// import DeweyPanel from '../panels/dewey/DeweyPanel'

// Global overlay that appears when backend hotkey event is received
export default function HotkeyOverlay() {
  const [open, setOpen] = useState(false)
  const [status, setStatus] = useState('')
  const didPauseRef = useRef(false)
  const [emu, setEmu] = useState('unknown')
  const [paused, setPaused] = useState(false)
  const [preflightNeeded, setPreflightNeeded] = useState(false)
  const [saveSlot, setSaveSlot] = useState(1) // Default to slot 1

  useEffect(() => {
    hotkeyClient.connect()
    const onMsg = (msg) => {
      if (msg && msg.type === 'hotkey_pressed') {
        setOpen((prev) => !prev) // toggle overlay on each press
      }
    }
    hotkeyClient.addListener(onMsg)
    return () => hotkeyClient.removeListener(onMsg)
  }, [])

  const resumeIfPaused = useCallback(async () => {
    if (didPauseRef.current) {
      try {
        await fetch('/api/local/emulator/pause_toggle', {
          method: 'POST',
          headers: { 'content-type': 'application/json', 'x-scope': 'state' }
        })
      } catch (e) {
        // best-effort resume
      }
      didPauseRef.current = false
    }
  }, [])

  const handleClose = useCallback(() => {
    resumeIfPaused()
    setOpen(false)
  }, [resumeIfPaused])

  // Listen for ESC key to close overlay (prevent propagation to Pegasus/emulator)
  useEffect(() => {
    const onKey = (e) => {
      if (e.key === 'Escape') {
        e.preventDefault()
        e.stopPropagation()
        handleClose()
      }
    }
    if (open) window.addEventListener('keydown', onKey, true) // capture phase
    return () => window.removeEventListener('keydown', onKey, true)
  }, [open, handleClose])

  // On open, fetch status and auto-pause if needed (RetroArch only)
  useEffect(() => {
    let cancelled = false
    async function maybePause() {
      if (!open) return
      try {
        const s = await fetch('/api/local/emulator/status')
        const sj = await s.json().catch(() => ({}))
        if (!cancelled) {
          setEmu(sj?.emulator || 'unknown')
          setPaused(!!sj?.paused)
        }
      } catch { }
      if (open && !didPauseRef.current) {
        if (emu === 'retroarch') {
          try {
            const res = await fetch('/api/local/emulator/pause_toggle', {
              method: 'POST',
              headers: { 'content-type': 'application/json', 'x-scope': 'state' }
            })
            const data = await res.json().catch(() => ({}))
            if (!cancelled) {
              didPauseRef.current = true
              setPaused(true)
              const ok = data?.status === 'ok'
              setStatus(ok ? 'Game paused' : 'Pause not available')
              if (!ok) setPreflightNeeded(true)
            }
          } catch (e) {
            if (!cancelled) {
              setStatus('Pause not available')
              setPreflightNeeded(true)
            }
          }
        }
      }
    }
    maybePause()
    return () => { cancelled = true }
  }, [open, emu])

  // Emulators that support save states
  const SAVE_STATE_EMULATORS = ['retroarch', 'mame', 'pcsx2', 'dolphin', 'duckstation', 'rpcs3', 'redream']
  const supportsSaveStates = SAVE_STATE_EMULATORS.includes(emu)

  // Save/Load state - handles all supported emulators
  const setSlotAndAction = useCallback(async (action) => {
    try {
      // Emulator-specific endpoints
      const emulatorEndpoints = {
        mame: { save: '/api/local/emulator/mame/save_state', load: '/api/local/emulator/mame/load_state' },
        pcsx2: { save: '/api/local/emulator/pcsx2/save_state', load: '/api/local/emulator/pcsx2/load_state' },
        dolphin: { save: '/api/local/emulator/dolphin/save_state', load: '/api/local/emulator/dolphin/load_state' },
        duckstation: { save: '/api/local/emulator/duckstation/save_state', load: '/api/local/emulator/duckstation/load_state' },
        rpcs3: { save: '/api/local/emulator/rpcs3/save_state', load: '/api/local/emulator/rpcs3/load_state' },
        redream: { save: '/api/local/emulator/redream/save_state', load: '/api/local/emulator/redream/load_state' },
      }

      if (emulatorEndpoints[emu]) {
        // Use emulator-specific endpoint
        const endpoint = action === 'save' ? emulatorEndpoints[emu].save : emulatorEndpoints[emu].load
        const res = await fetch(endpoint, {
          method: 'POST',
          headers: { 'content-type': 'application/json', 'x-scope': 'state' }
        })
        const data = await res.json().catch(() => ({}))
        if (data?.ok || data?.status === 'ok') {
          setStatus(action === 'save' ? `Progress saved (${emu})` : `Progress loaded (${emu})`)
        } else {
          setStatus(`${action === 'save' ? 'Save' : 'Load'} failed: ${data?.error || 'unknown'}`)
        }
      } else {
        // RetroArch: Set slot first, then save/load
        // Note: RetroArch uses 0-indexed slots internally, but we show 1-10 to users
        await fetch('/api/local/emulator/set_slot', {
          method: 'POST',
          headers: { 'content-type': 'application/json', 'x-scope': 'state' },
          body: JSON.stringify({ slot: saveSlot - 1 })
        })

        const endpoint = action === 'save' ? '/api/local/emulator/save_state' : '/api/local/emulator/load_state'
        const res = await fetch(endpoint, {
          method: 'POST',
          headers: { 'content-type': 'application/json', 'x-scope': 'state' }
        })
        const data = await res.json().catch(() => ({}))

        if (data?.status === 'ok') {
          setStatus(action === 'save' ? `Saved to slot ${saveSlot}` : `Loaded slot ${saveSlot}`)
        } else {
          setStatus(`${action === 'save' ? 'Save' : 'Load'} failed`)
        }
      }
    } catch (e) {
      setStatus(`${action === 'save' ? 'Save' : 'Load'} failed: ${e.message}`)
    }
  }, [saveSlot, emu])

  if (!open) return null

  return (
    <div className="hotkey-overlay-backdrop" role="dialog" aria-modal="true">
      <div className="hotkey-overlay-panel">
        <div className="hotkey-overlay-header">
          <div className="hotkey-overlay-title">Pause Menu {emu !== 'unknown' ? `- ${emu}` : ''}</div>
          <button className="hotkey-overlay-close" onClick={handleClose} aria-label="Close overlay">Close</button>
        </div>
        <div className="hotkey-hint">Press ESC to close and resume</div>
        <div className="hotkey-overlay-body">
          {/* Save Slot Selector (RetroArch only) */}
          {emu === 'retroarch' && (
            <div style={{ marginBottom: 12, display: 'flex', alignItems: 'center', gap: 10 }}>
              <label style={{ color: '#9db7d8', fontSize: 13 }}>Save Slot:</label>
              <select
                value={saveSlot}
                onChange={(e) => setSaveSlot(Number(e.target.value))}
                style={{
                  background: '#1a2456',
                  color: '#67e8f9',
                  border: '1px solid rgba(0, 229, 255, 0.3)',
                  borderRadius: 4,
                  padding: '4px 8px',
                  fontSize: 13
                }}
              >
                {[1, 2, 3, 4, 5, 6, 7, 8, 9, 10].map(slot => (
                  <option key={slot} value={slot}>Slot {slot}</option>
                ))}
              </select>
            </div>
          )}

          <div style={{ display: 'flex', gap: 12, flexWrap: 'wrap', marginBottom: 10 }}>
            {/* Save/Load buttons - all emulators that support save states */}
            {supportsSaveStates && (
              <>
                <button className="hotkey-overlay-btn save" onClick={() => setSlotAndAction('save')}>
                  💾 Save Progress
                </button>
                <button className="hotkey-overlay-btn load" onClick={() => setSlotAndAction('load')}>
                  📂 Load Progress
                </button>
              </>
            )}
            <button className="hotkey-overlay-btn resume" onClick={async () => {
              if (emu === 'mame') {
                try {
                  await fetch('/api/local/emulator/mame/pause_toggle', {
                    method: 'POST',
                    headers: { 'x-scope': 'state' }
                  })
                } catch { }
                setStatus('Toggled pause for MAME')
              } else {
                await resumeIfPaused()
              }
              setOpen(false)
            }}>▶️ Resume Game</button>
            <button className="hotkey-overlay-btn exit" onClick={async () => {
              setStatus('Exiting game...')
              try {
                await fetch('/api/local/emulator/exit', {
                  method: 'POST',
                  headers: { 'content-type': 'application/json', 'x-scope': 'state' },
                  body: JSON.stringify({ emulator: emu })
                })
              } catch { }
              setOpen(false)
            }}>🚪 Exit Game</button>
            <button className="hotkey-overlay-btn wizard" onClick={() => {
              try { window.location.href = '/controller-wizard' } catch { }
            }}>🎮 Controller Wizard</button>
          </div>

          {status && <div style={{ fontSize: 13, color: '#c8ff00', marginTop: 8 }}>{status}</div>}
          {emu === 'retroarch' && preflightNeeded && (
            <div style={{ fontSize: 12, color: '#ff6b6b', marginTop: 6 }}>
              RetroArch network commands not available. Run preflight to enable.
            </div>
          )}
        </div>
      </div>
    </div>
  )
}

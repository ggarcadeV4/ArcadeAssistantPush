// frontend/components/GunnerPanel.jsx
import React, { useState, useEffect, useRef, useCallback } from 'react'
import { PanelShell } from '../panels/_kit'

/**
 * Gunner Panel - Light gun calibration with 9-point wizard.
 *
 * Features:
 * - 9-point calibration grid (3x3)
 * - Real-time WebSocket feedback
 * - Visual crosshair on aim
 * - LED flash feedback
 * - Profile save/load
 * - Voice status updates
 */
export default function GunnerPanel({ userId = 'guest' }) {
  // Core state
  const [devices, setDevices] = useState([])
  const [selectedDevice, setSelectedDevice] = useState(null)
  const [calibrationPoints, setCalibrationPoints] = useState(Array(9).fill(null))
  const [currentPoint, setCurrentPoint] = useState(0)
  const [isCalibrating, setIsCalibrating] = useState(false)
  const [voiceStatus, setVoiceStatus] = useState('Ready to calibrate')
  const [crosshairPos, setCrosshairPos] = useState({ x: 0.5, y: 0.5 })
  const [showCrosshair, setShowCrosshair] = useState(false)
  const [flashColor, setFlashColor] = useState(null)
  const [connectionStatus, setConnectionStatus] = useState('offline')

  // Profile state
  const [profileName, setProfileName] = useState('')
  const [profileList, setProfileList] = useState([])

  // Refs
  const wsRef = useRef(null)
  const gridRef = useRef(null)
  const flashTimerRef = useRef(null)

  // 9-point grid positions (3x3, normalized 0-1)
  const gridPositions = [
    { x: 0.1, y: 0.1 }, { x: 0.5, y: 0.1 }, { x: 0.9, y: 0.1 },
    { x: 0.1, y: 0.5 }, { x: 0.5, y: 0.5 }, { x: 0.9, y: 0.5 },
    { x: 0.1, y: 0.9 }, { x: 0.5, y: 0.9 }, { x: 0.9, y: 0.9 }
  ]

  // ============================================================================
  // WebSocket Connection
  // ============================================================================
  useEffect(() => {
    const ws = new WebSocket(`ws://localhost:8787/gunner/ws?user_id=${userId}`)
    wsRef.current = ws

    ws.onopen = () => {
      console.log('[Gunner] WebSocket connected')
      setConnectionStatus('online')
      ws.send(JSON.stringify({ type: 'status' }))
    }

    ws.onmessage = (event) => {
      try {
        const data = JSON.parse(event.data)

        if (data.type === 'point') {
          handlePointCaptured(data)
        } else if (data.type === 'complete') {
          handleCalibrationComplete(data)
        } else if (data.type === 'status') {
          setDevices(data.devices || [])
          if (data.devices?.length > 0) {
            setSelectedDevice(data.devices[0].id)
          }
        } else if (data.type === 'error') {
          console.error('[Gunner] Error:', data.message)
          setVoiceStatus(`Error: ${data.message}`)
        }
      } catch (err) {
        console.error('[Gunner] WebSocket message error:', err)
      }
    }

    ws.onclose = () => {
      console.log('[Gunner] WebSocket disconnected')
      setConnectionStatus('offline')
    }

    ws.onerror = () => {
      setConnectionStatus('degraded')
    }

    return () => {
      ws.close()
      if (flashTimerRef.current) clearTimeout(flashTimerRef.current)
    }
  }, [userId])

  // ============================================================================
  // Calibration Logic
  // ============================================================================
  const startCalibration = useCallback(() => {
    setIsCalibrating(true)
    setCurrentPoint(0)
    setCalibrationPoints(Array(9).fill(null))
    setVoiceStatus('Aim at the top-left point...')
    setShowCrosshair(true)
  }, [])

  const resetCalibration = useCallback(() => {
    setIsCalibrating(false)
    setCurrentPoint(0)
    setCalibrationPoints(Array(9).fill(null))
    setVoiceStatus('Ready to calibrate')
    setShowCrosshair(false)
  }, [])

  const capturePoint = useCallback((x, y) => {
    if (!isCalibrating || selectedDevice === null) return

    wsRef.current?.send(JSON.stringify({
      type: 'capture',
      device_id: selectedDevice,
      x,
      y
    }))
  }, [isCalibrating, selectedDevice])

  const handlePointCaptured = useCallback((data) => {
    const newPoints = [...calibrationPoints]
    newPoints[data.current - 1] = { x: data.x, y: data.y }
    setCalibrationPoints(newPoints)
    setCurrentPoint(data.current)

    // Green flash feedback
    flashLED('#00FF00')

    // Update voice status
    if (data.complete) {
      setVoiceStatus('Calibration complete! 🎯')
      setIsCalibrating(false)
      setShowCrosshair(false)
    } else {
      const positions = ['top-left', 'top-center', 'top-right', 'middle-left', 'center', 'middle-right', 'bottom-left', 'bottom-center', 'bottom-right']
      setVoiceStatus(`Point captured! Aim at ${positions[data.current]}...`)
    }
  }, [calibrationPoints])

  const handleCalibrationComplete = useCallback((data) => {
    // Rainbow pulse feedback
    flashLED('#FF0000', '#00FF00', '#0000FF', '#FFFF00')
    setVoiceStatus('Calibration complete! Save your profile.')
  }, [])

  const flashLED = useCallback((...colors) => {
    let index = 0
    const flash = () => {
      if (index < colors.length) {
        setFlashColor(colors[index])
        index++
        flashTimerRef.current = setTimeout(() => {
          setFlashColor(null)
          if (index < colors.length) {
            setTimeout(flash, 100)
          }
        }, 150)
      }
    }
    flash()
  }, [])

  // ============================================================================
  // Mouse Tracking (for crosshair)
  // ============================================================================
  const handleMouseMove = useCallback((e) => {
    if (!gridRef.current || !isCalibrating) return

    const rect = gridRef.current.getBoundingClientRect()
    const x = (e.clientX - rect.left) / rect.width
    const y = (e.clientY - rect.top) / rect.height

    if (x >= 0 && x <= 1 && y >= 0 && y <= 1) {
      setCrosshairPos({ x, y })
      setShowCrosshair(true)
    }
  }, [isCalibrating])

  const handleGridClick = useCallback((e) => {
    if (!isCalibrating || !gridRef.current) return

    const rect = gridRef.current.getBoundingClientRect()
    const x = (e.clientX - rect.left) / rect.width
    const y = (e.clientY - rect.top) / rect.height

    capturePoint(x, y)
  }, [isCalibrating, capturePoint])

  // ============================================================================
  // Profile Management
  // ============================================================================
  const saveProfile = useCallback(async () => {
    if (!profileName.trim() || calibrationPoints.filter(p => p).length < 9) {
      setVoiceStatus('Complete calibration first!')
      return
    }

    try {
      const res = await fetch('http://localhost:8787/api/gunner/profile/save', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          user_id: userId,
          game: profileName,
          points: calibrationPoints.map(p => ({ x: p.x, y: p.y }))
        })
      })

      if (res.ok) {
        setVoiceStatus(`Profile "${profileName}" saved!`)
        loadProfiles()
      } else {
        setVoiceStatus('Failed to save profile')
      }
    } catch (err) {
      console.error('[Gunner] Save profile failed:', err)
      setVoiceStatus('Save failed')
    }
  }, [profileName, calibrationPoints, userId])

  const loadProfiles = useCallback(async () => {
    try {
      const res = await fetch(`http://localhost:8787/api/gunner/profiles?user_id=${userId}`)
      const data = await res.json()
      setProfileList(data.profiles || [])
    } catch (err) {
      console.error('[Gunner] Load profiles failed:', err)
    }
  }, [userId])

  const loadProfile = useCallback(async (game) => {
    try {
      const res = await fetch('http://localhost:8787/api/gunner/profile/load', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ user_id: userId, game })
      })

      const data = await res.json()
      if (data.points) {
        setCalibrationPoints(data.points)
        setVoiceStatus(`Profile "${game}" loaded`)
      }
    } catch (err) {
      console.error('[Gunner] Load profile failed:', err)
    }
  }, [userId])

  useEffect(() => {
    if (connectionStatus === 'online') {
      loadProfiles()
    }
  }, [connectionStatus, loadProfiles])

  // ============================================================================
  // Render
  // ============================================================================
  return (
    <PanelShell
      title="Gunner - Light Gun Calibration"
      subtitle="9-Point Calibration Wizard"
      icon="🎯"
      status={connectionStatus}
    >
      <div className="gunner-panel">
        {/* Device Info */}
        <div className="gunner-device-info">
          {devices.length > 0 ? (
            <select
              value={selectedDevice ?? ''}
              onChange={(e) => setSelectedDevice(Number(e.target.value))}
              className="gunner-select"
            >
              {devices.map((d) => (
                <option key={d.id} value={d.id}>
                  {d.name} ({d.type})
                </option>
              ))}
            </select>
          ) : (
            <p className="gunner-muted">No guns detected (mock mode)</p>
          )}
        </div>

        {/* Calibration Grid */}
        <div
          ref={gridRef}
          className="gunner-grid"
          onMouseMove={handleMouseMove}
          onClick={handleGridClick}
          style={{ position: 'relative', cursor: isCalibrating ? 'crosshair' : 'default' }}
        >
          {/* Flash overlay */}
          {flashColor && (
            <div
              className="gunner-flash"
              style={{ backgroundColor: flashColor }}
            />
          )}

          {/* 9 calibration points */}
          {gridPositions.map((pos, idx) => (
            <div
              key={idx}
              className={`gunner-point ${idx === currentPoint && isCalibrating ? 'gunner-point-active' : ''} ${calibrationPoints[idx] ? 'gunner-point-captured' : ''}`}
              style={{
                left: `${pos.x * 100}%`,
                top: `${pos.y * 100}%`
              }}
            >
              {idx + 1}
            </div>
          ))}

          {/* Crosshair */}
          {showCrosshair && isCalibrating && (
            <div
              className="gunner-crosshair"
              style={{
                left: `${crosshairPos.x * 100}%`,
                top: `${crosshairPos.y * 100}%`
              }}
            >
              <div className="crosshair-h" />
              <div className="crosshair-v" />
            </div>
          )}
        </div>

        {/* Controls */}
        <div className="gunner-controls">
          <button
            onClick={startCalibration}
            className="gunner-btn gunner-btn-start"
            disabled={isCalibrating || selectedDevice === null}
          >
            Start Calibration
          </button>
          <button
            onClick={resetCalibration}
            className="gunner-btn gunner-btn-reset"
            disabled={!isCalibrating}
          >
            Reset
          </button>
        </div>

        {/* Profile Management */}
        <div className="gunner-profile">
          <h3 className="section-title">Profile Management</h3>
          <div className="gunner-profile-row">
            <input
              type="text"
              value={profileName}
              onChange={(e) => setProfileName(e.target.value)}
              placeholder="Profile name (e.g., Area51)"
              className="gunner-input"
            />
            <button
              onClick={saveProfile}
              className="gunner-btn gunner-btn-save"
              disabled={calibrationPoints.filter(p => p).length < 9}
            >
              Save
            </button>
          </div>
          {profileList.length > 0 && (
            <div className="gunner-profile-list">
              {profileList.map((prof) => (
                <button
                  key={prof}
                  onClick={() => loadProfile(prof)}
                  className="gunner-profile-item"
                >
                  {prof}
                </button>
              ))}
            </div>
          )}
        </div>

        {/* Voice Status Bar */}
        <div className="gunner-status-bar">
          <span className="gunner-status-icon">🎯</span>
          <span className="gunner-status-text">{voiceStatus}</span>
          <span className="gunner-status-progress">
            {calibrationPoints.filter(p => p).length}/9
          </span>
        </div>
      </div>

      <style jsx>{`
        .gunner-panel { display: flex; flex-direction: column; gap: 20px; padding: 20px; }
        .gunner-device-info { padding: 10px; background: rgba(0, 0, 0, 0.6); border-radius: 8px; }
        .gunner-select, .gunner-input { width: 100%; padding: 10px; background: #1a1a1a; color: #fff; border: 1px solid #444; border-radius: 4px; font-size: 14px; }
        .gunner-muted { color: #777; margin: 0; }
        .gunner-grid { width: 100%; height: 400px; background: #0a0a0a; border: 2px solid #444; border-radius: 8px; position: relative; }
        .gunner-flash { position: absolute; inset: 0; opacity: 0.5; pointer-events: none; animation: flash 0.3s; }
        @keyframes flash { 0%, 100% { opacity: 0; } 50% { opacity: 0.5; } }
        .gunner-point { position: absolute; width: 40px; height: 40px; border-radius: 50%; border: 3px solid #555; background: rgba(0, 0, 0, 0.8); display: flex; align-items: center; justify-content: center; color: #888; font-weight: bold; transform: translate(-50%, -50%); transition: all 0.3s; }
        .gunner-point-active { border-color: #c8ff00; color: #c8ff00; animation: pulse-point 1s ease-in-out infinite; }
        @keyframes pulse-point { 0%, 100% { transform: translate(-50%, -50%) scale(1); } 50% { transform: translate(-50%, -50%) scale(1.2); } }
        .gunner-point-captured { border-color: #00ff00; background: rgba(0, 255, 0, 0.2); color: #00ff00; }
        .gunner-crosshair { position: absolute; transform: translate(-50%, -50%); pointer-events: none; }
        .crosshair-h, .crosshair-v { position: absolute; background: #ff0000; }
        .crosshair-h { width: 30px; height: 2px; left: -15px; top: 0; }
        .crosshair-v { width: 2px; height: 30px; left: 0; top: -15px; }
        .gunner-controls { display: flex; gap: 10px; }
        .gunner-btn { padding: 12px 24px; border: none; border-radius: 4px; font-weight: 600; cursor: pointer; transition: transform 0.2s; }
        .gunner-btn:hover:not(:disabled) { transform: scale(1.05); }
        .gunner-btn:disabled { opacity: 0.4; cursor: not-allowed; }
        .gunner-btn-start { background: linear-gradient(135deg, #00e5ff, #c8ff00); color: #000; }
        .gunner-btn-reset { background: #ff4444; color: #fff; }
        .gunner-btn-save { background: linear-gradient(135deg, #00ff00, #00e5ff); color: #000; }
        .gunner-profile { padding: 15px; background: rgba(0, 0, 0, 0.6); border-radius: 8px; }
        .section-title { margin: 0 0 10px 0; color: #c8ff00; font-size: 16px; }
        .gunner-profile-row { display: flex; gap: 10px; margin-bottom: 10px; }
        .gunner-profile-list { display: flex; flex-wrap: wrap; gap: 8px; }
        .gunner-profile-item { padding: 8px 16px; background: rgba(0, 229, 255, 0.2); border: 1px solid #00e5ff; border-radius: 4px; color: #00e5ff; cursor: pointer; transition: all 0.2s; }
        .gunner-profile-item:hover { background: rgba(0, 229, 255, 0.4); transform: scale(1.05); }
        .gunner-status-bar { display: flex; align-items: center; gap: 12px; padding: 15px; background: rgba(200, 255, 0, 0.1); border-radius: 8px; border: 1px solid #c8ff00; }
        .gunner-status-icon { font-size: 20px; }
        .gunner-status-text { flex: 1; font-weight: 600; color: #c8ff00; }
        .gunner-status-progress { color: #888; font-size: 14px; }
      `}</style>
    </PanelShell>
  )
}

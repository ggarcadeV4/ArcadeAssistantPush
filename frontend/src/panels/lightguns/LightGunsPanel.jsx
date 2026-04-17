import React, { useState, useReducer, useCallback, useEffect, useMemo, useRef } from 'react'
import PanelShell from '../_kit/PanelShell'
import { chat as aiChat } from '../../services/aiClient'
import { speak, stopSpeaking } from '../../services/ttsClient'
import GunnerVoiceControls from './GunnerVoiceControls'
// Design Decision (2025-11-29): Gunner voice uses the shared /ws/audio + /api/ai/chat pipeline—no panel-specific STT/TTS layers.
import {
  listDevices as listDevicesApi,
  captureCalibrationPoint,
  saveProfile as saveProfileApi,
  listProfiles as listProfilesApi,
  loadProfile as loadProfileApi,
  applyTendencies as applyTendenciesApi,
  streamCalibration as streamCalibrationApi
} from '../../services/gunnerClient'
import { testLED } from '../../services/ledBlinkyClient'
import { buildStandardHeaders, resolveDeviceId } from '../../utils/identity'

// ============================================================================
// Calibration State Machine (Reducer Pattern)
// ============================================================================

const calibReducer = (state, action) => {
  switch (action.type) {
    case 'START_CALIB':
      return {
        ...state,
        status: 'calibrating',
        device: action.device,
        points: [],
        currentPoint: 0,
        error: null
      }

    case 'ADD_POINT':
      const newPoints = [...state.points, action.point]
      const nextPoint = state.currentPoint + 1

      return {
        ...state,
        points: newPoints,
        currentPoint: nextPoint,
        status: nextPoint >= 9 ? 'complete' : 'calibrating'
      }

    case 'COMPLETE':
      return {
        ...state,
        status: 'done',
        currentPoint: 0
      }

    case 'ERROR':
      return {
        ...state,
        status: 'error',
        error: action.msg
      }

    case 'RESET':
      return {
        status: 'idle',
        points: [],
        device: null,
        currentPoint: 0,
        error: null
      }

    default:
      return state
  }
}

const initialCalibState = {
  status: 'idle', // idle | calibrating | complete | done | error
  points: [],
  device: null,
  currentPoint: 0,
  error: null
}

// ============================================================================
// Custom Hook for Gunner Hardware
// ============================================================================

const useGunner = () => {
  const [devices, setDevices] = useState([])
  const [loading, setLoading] = useState(false)

  const fetchDevices = useCallback(async () => {
    setLoading(true)
    try {
      const data = await listDevicesApi()
      setDevices(data.devices || [])
    } catch (error) {
      console.error('Failed to fetch gun devices:', error)
      // Fallback to mock device
      setDevices([{
        id: 1,
        name: 'Sinden Light Gun (Mock)',
        type: 'mock',
        vid: '0x16c0',
        pid: '0x0f38',
        connected: true
      }])
    } finally {
      setLoading(false)
    }
  }, [])

  const capturePoint = useCallback(async (deviceId, x, y) => {
    return captureCalibrationPoint({ deviceId, x, y })
  }, [])

  const saveProfile = useCallback(async ({ userId, game, points }) => {
    return saveProfileApi({ userId, game, points })
  }, [])

  return { devices, loading, fetchDevices, capturePoint, saveProfile }
}

const formatProfileTimestamp = (value) => {
  if (!value) return 'Never'
  const date = new Date(value)
  if (Number.isNaN(date.getTime())) return 'Unknown'
  return date.toLocaleDateString()
}

// ============================================================================
// Main Component
// ============================================================================

export default function LightGunsPanel({ showProfilesSection = false }) {
  const DEFAULT_USER = 'dad'
  const GUN_TYPES = useMemo(
    () => [
      { value: 'standard', label: 'Sinden Lightgun' },
      { value: 'precision', label: 'Gun4IR' },
      { value: 'arcade', label: 'RetroShooter' }
    ],
    []
  )
  const HAND_OPTIONS = [
    { value: 'right', label: 'Right-handed' },
    { value: 'left', label: 'Left-handed' }
  ]
  const GUNNER_TABS = useMemo(
    () => [
      { id: 'devices', label: '[Devices]' },
      { id: 'calibration', label: '[Calibration]' },
      { id: 'profiles', label: '[Profiles]' },
      { id: 'retro-modes', label: '[Retro Modes]' }
    ],
    []
  )
  const RETRO_ENGINES = useMemo(
    () => [
      {
        id: 'arcade-cabinet',
        name: 'Arcade Cabinet',
        status: 'online',
        description: 'Balanced mode for mixed CRT/LCD cabinets with low-latency sync.'
      },
      {
        id: 'mame-native',
        name: 'MAME Native',
        status: 'stable',
        description: 'Native border and timing presets tuned for classic MAME titles.'
      },
      {
        id: 'batocera-core',
        name: 'Batocera Core',
        status: 'testing',
        description: 'Fast-launch profile for Batocera frontends and mixed emulator stacks.'
      },
      {
        id: 'technoparrot',
        name: 'TeknoParrot',
        status: 'beta',
        description: 'Experimental recoil and sensitivity map for modern arcade shooters.'
      }
    ],
    []
  )
  const AVATAR_CANDIDATES = [
    '/gunner-avatar.jpeg',
    '/lightguns-avatar.png',
    '/lightguns-avatar.jpg',
    '/lightguns-avatar.jpeg'
  ] // place your preferred image under frontend/public
  const [chatOpen, setChatOpen] = useState(true)
  const [activeTab, setActiveTab] = useState(showProfilesSection ? 'profiles' : 'devices')
  const [chatInput, setChatInput] = useState('')
  const [chatMessages, setChatMessages] = useState(() => {
    // Don't show default greeting if coming from Dewey handoff
    const urlParams = new URLSearchParams(window.location.search)
    const hasHandoff = urlParams.get('context')
    if (hasHandoff) return []
    return [
      { type: 'ai', text: "Hi! I'm Gunner, your light gun specialist. I can help you with calibration issues, sensitivity settings, and hardware compatibility. What can I help you with today?" }
    ]
  })
  const [selectedDeviceId, setSelectedDeviceId] = useState('')
  const [gunType, setGunType] = useState(GUN_TYPES[0].value)
  const [handedness, setHandedness] = useState('right')
  const [profileOptions, setProfileOptions] = useState([])
  const [profileSelection, setProfileSelection] = useState('')
  const [customProfileName, setCustomProfileName] = useState('')
  const [profileDetails, setProfileDetails] = useState(null)
  const [profileStatus, setProfileStatus] = useState('idle')
  const [calibrationResult, setCalibrationResult] = useState(null)
  const [statusBanner, setStatusBanner] = useState('')
  const [toast, setToast] = useState(null)
  const [savingProfile, setSavingProfile] = useState(false)
  const [streaming, setStreaming] = useState(false)
  const [selectedRetroEngineId, setSelectedRetroEngineId] = useState('arcade-cabinet')
  const [retroSettings, setRetroSettings] = useState({
    sensitivity: 68,
    smoothing: 42,
    recoil: 55,
    profile: 'crt-15khz'
  })
  const streamAbortRef = useRef(null)
  const targetRef = useRef(null)
  const handoffProcessedRef = useRef(null)
  const profilesSectionRef = useRef(null)
  const profileOwner = DEFAULT_USER
  const deviceId = useMemo(resolveDeviceId, [])

  // Stop any ongoing TTS when this panel unmounts
  useEffect(() => () => { try { stopSpeaking() } catch { } }, [])

  // Auto-scroll to profiles section if requested via URL param
  useEffect(() => {
    if (showProfilesSection && profilesSectionRef.current) {
      setActiveTab('profiles')
      setTimeout(() => {
        profilesSectionRef.current?.scrollIntoView({ behavior: 'smooth', block: 'start' })
      }, 300) // Short delay to allow render
    }
  }, [showProfilesSection])

  useEffect(() => {
    if (activeTab !== 'profiles' || !profilesSectionRef.current) return
    const timer = setTimeout(() => {
      profilesSectionRef.current?.scrollIntoView({ behavior: 'smooth', block: 'start' })
    }, 150)
    return () => clearTimeout(timer)
  }, [activeTab])

  // Calibration state machine
  const [calibState, dispatch] = useReducer(calibReducer, initialCalibState)

  // Hardware integration
  const { devices, loading, fetchDevices, capturePoint, saveProfile } = useGunner()

  // Fetch devices on mount
  useEffect(() => {
    fetchDevices()

    // Check for handoff context from Dewey (URL-based)
    const urlParams = new URLSearchParams(window.location.search)
    const handoffContext = urlParams.get('context')
    const hasHandoff = Boolean((handoffContext || '').trim())
    const noHandoff = urlParams.has('nohandoff')
    const shouldHandoff = hasHandoff && !noHandoff
    if (shouldHandoff && handoffContext !== handoffProcessedRef.current) {
      const welcomeMsg = `Hi! Dewey told me you said: "${handoffContext}"\n\nI'm Gunner, your light gun specialist. I can help with calibration, sensitivity, and hardware issues. What would you like me to do?`
      handoffProcessedRef.current = handoffContext
      setChatMessages([{ type: 'ai', text: welcomeMsg }])
      setChatOpen(true)
      speak(welcomeMsg, { voice_profile: 'gunner' }).catch(err => {
        console.warn('[Gunner] URL handoff TTS failed:', err)
      })
    }

    // Check for JSON handoff from Dewey (only when arriving via Dewey URL context)
    if (shouldHandoff) (async () => {
      try {
        const response = await fetch('/api/local/dewey/handoff/gunner', {
          method: 'GET',
          headers: buildStandardHeaders({
            panel: 'gunner',
            scope: 'state',
            extraHeaders: { 'Content-Type': 'application/json' }
          })
        })
        const text = await response.text()
        let data = null
        if (text) {
          try {
            data = JSON.parse(text)
          } catch {
            data = text
          }
        }

        if (data && data.handoff) {
          const rawSummary = typeof data.handoff.summary === 'string'
            ? data.handoff.summary
            : JSON.stringify(data.handoff)

          const summaryText = (rawSummary || '').trim()
          if (summaryText && summaryText !== handoffProcessedRef.current) {
            handoffProcessedRef.current = summaryText
            const welcomeMsg = `Dewey briefed me: "${summaryText}". I'm Gunner, ready to help with your light gun setup!`
            setChatMessages([{ type: 'ai', text: welcomeMsg }])
            setChatOpen(true)
            speak(welcomeMsg, { voice_profile: 'gunner' }).catch(err => {
              console.warn('[Gunner] JSON handoff TTS failed:', err)
            })
          }
        }
      } catch (err) {
        console.warn('[Gunner] Handoff fetch failed:', err)
      }
    })()
  }, [fetchDevices])

  useEffect(() => {
    if (devices.length > 0 && !selectedDeviceId) {
      const first = devices[0]
      if (first?.id !== undefined) {
        setSelectedDeviceId(String(first.id))
      }
    }
  }, [devices, selectedDeviceId])

  const selectedDevice = useMemo(
    () => devices.find(device => String(device.id) === String(selectedDeviceId)),
    [devices, selectedDeviceId]
  )
  const selectedRetroEngine = useMemo(
    () => RETRO_ENGINES.find(engine => engine.id === selectedRetroEngineId) ?? RETRO_ENGINES[0],
    [RETRO_ENGINES, selectedRetroEngineId]
  )
  const calibrationProgress = Math.round((calibState.points.length / 9) * 100)
  const profileSignal = profileSelection ? 76 : 24

  const fetchProfileList = useCallback(async () => {
    setProfileStatus('loading')
    try {
      const data = await listProfilesApi({ userId: profileOwner })
      const profiles = data?.profiles || []
      setProfileOptions(profiles)
      setProfileSelection(prev => prev || (profiles[0]?.game || ''))
      setProfileStatus('ready')
    } catch (error) {
      console.error('Failed to load profiles', error)
      setProfileStatus('error')
    }
  }, [profileOwner])

  useEffect(() => {
    fetchProfileList()
  }, [fetchProfileList])

  useEffect(() => {
    return () => {
      if (streamAbortRef.current) {
        streamAbortRef.current()
        streamAbortRef.current = null
      }
    }
  }, [])

  useEffect(() => {
    if (!toast) return
    const timer = setTimeout(() => setToast(null), 4000)
    return () => clearTimeout(timer)
  }, [toast])

  const triggerLedPulse = useCallback(() => {
    testLED({ effect: 'pulse', durationMs: 350, color: '#22d3ee' }).catch(() => { })
  }, [])

  const handleReset = useCallback(() => {
    if (streamAbortRef.current) {
      streamAbortRef.current()
      streamAbortRef.current = null
    }
    setStreaming(false)
    setCalibrationResult(null)
    setStatusBanner('')
    dispatch({ type: 'RESET' })
  }, [])

  const runCalibrationStream = useCallback(async (points) => {
    if (!selectedDeviceId || points.length !== 9) return
    setStreaming(true)
    setStatusBanner('Streaming calibration data...')
    setCalibrationResult(null)
    try {
      if (streamAbortRef.current) {
        streamAbortRef.current()
        streamAbortRef.current = null
      }
      const abort = await streamCalibrationApi(
        {
          device_id: selectedDeviceId,
          user_id: profileOwner,
          game_type: gunType,
          points,
          metadata: {
            gun_type: gunType,
            profile: customProfileName || profileSelection || 'default'
          }
        },
        {
          onEvent: event => {
            setCalibrationResult(event)
            if (event.status === 'complete' || event.status === 'done') {
              setStreaming(false)
              setStatusBanner(`Accuracy ${(event.accuracy ?? 0).toFixed(2)}`)
              if (streamAbortRef.current) {
                streamAbortRef.current()
                streamAbortRef.current = null
              }
            }
          }
        }
      )
      streamAbortRef.current = abort
    } catch (error) {
      setStreaming(false)
      setStatusBanner(error.message)
    }
  }, [selectedDeviceId, profileOwner, gunType, customProfileName, profileSelection])

  // Handle calibration flow
  const handleStartCalib = useCallback(() => {
    if (!selectedDevice) {
      dispatch({ type: 'ERROR', msg: 'No devices detected' })
      return
    }
    handleReset()
    dispatch({ type: 'START_CALIB', device: selectedDevice })
    setStatusBanner('Aim at each target and click to capture.')
    triggerLedPulse()
  }, [handleReset, selectedDevice, triggerLedPulse])

  const handleCalibPoint = useCallback(async (x, y) => {
    if (calibState.status !== 'calibrating' || !selectedDeviceId) return
    const nextPoints = [...calibState.points, { x, y }]
    try {
      const result = await capturePoint(selectedDeviceId, x, y)
      dispatch({ type: 'ADD_POINT', point: { x, y } })
      triggerLedPulse()
      if (result.complete || nextPoints.length === 9) {
        dispatch({ type: 'COMPLETE' })
        setStatusBanner('Captured all points, processing...')
        await runCalibrationStream(nextPoints)
      } else {
        setStatusBanner(`Captured point ${nextPoints.length}/9`)
      }
    } catch (error) {
      dispatch({ type: 'ERROR', msg: error.message })
      setToast({ type: 'error', text: error.message })
    }
  }, [calibState.status, calibState.points, selectedDeviceId, capturePoint, triggerLedPulse, runCalibrationStream])

  const handleSkipStep = useCallback(() => {
    if (calibState.status !== 'calibrating') return
    handleCalibPoint(0.5, 0.5)
    setStatusBanner('Skipped point with neutral center, continue aiming at remaining targets.')
  }, [calibState.status, handleCalibPoint])

  const handleSaveProfile = useCallback(async () => {
    if (calibState.points.length !== 9) {
      dispatch({ type: 'ERROR', msg: 'Need 9 calibration points' })
      setToast({ type: 'error', text: 'Capture all 9 points before saving.' })
      return
    }
    const gameName = (customProfileName || profileSelection || 'default').trim() || 'default'
    setSavingProfile(true)
    try {
      await saveProfile({ userId: profileOwner, game: gameName, points: calibState.points })
      await applyTendenciesApi({
        profileId: profileOwner,
        handedness,
        sensitivity: calibrationResult?.adjustments?.sensitivity ?? 85
      })
      setChatMessages(m => [...m, { type: 'ai', text: `Profile "${gameName}" saved successfully.` }])
      setToast({ type: 'success', text: `Saved ${gameName} profile` })
      setCustomProfileName('')
      fetchProfileList()
      handleReset()
    } catch (error) {
      dispatch({ type: 'ERROR', msg: `Save failed: ${error.message}` })
      setToast({ type: 'error', text: error.message })
    } finally {
      setSavingProfile(false)
    }
  }, [
    calibState.points,
    customProfileName,
    profileSelection,
    profileOwner,
    handedness,
    calibrationResult,
    saveProfile,
    fetchProfileList,
    handleReset
  ])

  const handleLoadProfile = useCallback(async () => {
    if (!profileSelection) {
      setToast({ type: 'warning', text: 'Select a profile to load.' })
      return
    }
    setProfileStatus('loading')
    try {
      const data = await loadProfileApi({ userId: profileOwner, game: profileSelection })
      setProfileDetails(data)
      setStatusBanner(`Loaded ${profileSelection} profile`)
    } catch (error) {
      console.error('Failed to load profile', error)
      setToast({ type: 'error', text: error.message })
    } finally {
      setProfileStatus('ready')
    }
  }, [profileSelection, profileOwner])

  const handleTestAccuracy = useCallback(() => {
    const activePoints =
      calibState.points.length === 9
        ? calibState.points
        : (profileDetails?.points && profileDetails.points.length === 9 ? profileDetails.points : null)
    if (!activePoints) {
      setToast({ type: 'warning', text: 'Capture or load 9 points before running accuracy test.' })
      return
    }
    runCalibrationStream(activePoints)
  }, [calibState.points, profileDetails, runCalibrationStream])

  const handleTargetClick = useCallback(
    event => {
      if (calibState.status !== 'calibrating') return
      const rect = targetRef.current?.getBoundingClientRect()
      if (!rect) return
      const x = (event.clientX - rect.left) / rect.width
      const y = (event.clientY - rect.top) / rect.height
      handleCalibPoint(Number(x.toFixed(3)), Number(y.toFixed(3)))
    },
    [calibState.status, handleCalibPoint]
  )

  const handleTargetKeyDown = useCallback(
    event => {
      if (event.key !== 'Enter' && event.key !== ' ') return
      event.preventDefault()
      if (calibState.status === 'calibrating') {
        handleCalibPoint(0.5, 0.5)
      }
    },
    [calibState.status, handleCalibPoint]
  )

  const handleDeviceChange = useCallback(event => {
    setSelectedDeviceId(event.target.value)
  }, [])

  const handleGunTypeChange = useCallback(event => {
    setGunType(event.target.value)
  }, [])

  const handleProfileSelectChange = useCallback(event => {
    setProfileSelection(event.target.value)
  }, [])

  const handleCustomProfileChange = useCallback(event => {
    setCustomProfileName(event.target.value)
  }, [])

  const handleProfileCardSelect = useCallback((game) => {
    setProfileSelection(game)
  }, [])

  const handleRetroSettingChange = useCallback((key, value) => {
    setRetroSettings(prev => ({
      ...prev,
      [key]: value
    }))
  }, [])

  const sendChat = useCallback(async (text) => {
    const trimmed = text.trim()
    if (!trimmed) return
    setChatMessages(m => [...m, { type: 'user', text: trimmed }])
    setChatInput('')
    try {
      const sys = `You are Gunner, a light gun specialist for arcade cabinets. Be concise and actionable.

IMPORTANT CAPABILITIES:
- You CAN modify configuration files through the Arcade Assistant architecture
- Light gun calibration profiles are stored in JSON format at state/gunner/
- You can save/load calibration profiles per-user and per-game
- You can adjust sensitivity, deadzone, X/Y offsets for specific games
- Profiles sync to Supabase cloud when available, with local fallback
- You can preview and apply configuration changes using the standard preview/apply workflow

When users ask about changing settings or configurations:
1. Explain what you can modify (calibration profiles, sensitivity, offsets)
2. Offer to help them adjust specific parameters
3. Mention that changes will be previewed before applying
4. All modifications create automatic backups

Example config you can modify:
- Calibration points (9-point grid for different games)
- Sensitivity percentage (0-100)
- Deadzone in pixels
- X/Y offset adjustments
- Per-game and per-user profiles

You have full access to the Arcade Assistant's safe file modification system.`
      const res = await aiChat({
        provider: 'claude',
        panel: 'gunner',
        deviceId,
        messages: [
          { role: 'system', content: sys },
          { role: 'user', content: trimmed }
        ],
        metadata: { panel: 'gunner', character: 'gunner', intent: 'calibration_chat' },
        scope: 'state'
      })
      const reply = res?.message?.content || '[No response]'
      setChatMessages(m => [...m, { type: 'ai', text: reply }])
      speak(reply, { voice_profile: 'gunner' }).catch(err => console.error('[Gunner] TTS failed:', err))
    } catch (e) {
      const fallbacks = [
        "For CRT displays, start around 85% sensitivity and adjust offsets for geometry.",
        "Increase deadzone to ~3px if you notice drift; recalibrate after.",
        "Ensure emulator border/background is enabled for optical tracking.",
        "Run the 9-point calibration and keep the gun steady at each point.",
        "Use native resolution and avoid scaling for best accuracy."
      ]
      const msg = fallbacks[Math.floor(Math.random() * fallbacks.length)]
      setChatMessages(m => [...m, { type: 'ai', text: msg }])
      speak(msg, { voice_profile: 'gunner' }).catch(err => console.error('[Gunner] TTS failed:', err))
    }
  }, [deviceId])

  // Get calibration prompt for each point
  const getCalibrationPrompt = useCallback((pointNum) => {
    const prompts = {
      1: "Aim at the top-left corner and fire.",
      2: "Now aim at the top-center and fire.",
      3: "Aim at the top-right corner and fire.",
      4: "Aim at the center-left and fire.",
      5: "Aim at the dead center and fire.",
      6: "Aim at the center-right and fire.",
      7: "Aim at the bottom-left corner and fire.",
      8: "Aim at the bottom-center and fire.",
      9: "Finally, aim at the bottom-right corner and fire."
    }
    return prompts[pointNum] || "Aim and fire."
  }, [])

  const handleVoiceTranscript = useCallback(
    (transcript) => {
      const text = (transcript || '').trim()
      if (!text) return
      setChatMessages(m => [...m, { type: 'system', text: `🎙️ Heard: \"${text}\"` }])
      const normalized = text.toLowerCase()
      const speakAck = (phrase) =>
        speak(phrase, { voice_profile: 'gunner' }).catch(err => console.error('[Gunner Voice] TTS failed:', err))

      if (normalized.includes('start') && normalized.includes('calib')) {
        handleStartCalib()
        speakAck('Starting calibration. Aim at the first target and pull the trigger.')
        return
      }

      if (normalized.includes('save')) {
        handleSaveProfile()
        speakAck('Saving your profile now.')
        return
      }

      if (normalized.includes('reset') || normalized.includes('cancel')) {
        handleReset()
        speakAck('Calibration reset. Say start when you are ready again.')
        return
      }

      if (normalized.includes('test') || normalized.includes('accuracy')) {
        if (calibrationResult?.accuracy) {
          speakAck(`Your current accuracy is ${Math.round((calibrationResult.accuracy ?? 0) * 100)} percent.`)
        } else {
          handleTestAccuracy()
          speakAck('Running an accuracy test based on your latest points.')
        }
        return
      }

      sendChat(text)
      speakAck('Let me think about that.')
    },
    [calibrationResult, handleReset, handleSaveProfile, handleStartCalib, handleTestAccuracy, sendChat]
  )

  // Local component to render avatar with fallbacks
  function AvatarImg({ className, alt }) {
    const [idx, setIdx] = useState(0)
    if (idx >= AVATAR_CANDIDATES.length) return null
    return (
      <img
        src={AVATAR_CANDIDATES[idx]}
        alt={alt}
        className={className}
        onError={() => setIdx(i => i + 1)}
      />
    )
  }

  return (
    <PanelShell title="GUNNER: RETRO SHOOTER CONTROL CENTER" status="online">
      <div className="panel-container gunner-retro-shell">
        <div className={`main-panel ${chatOpen ? 'chat-open' : ''}`}>
          <div className="gunner-scanlines" aria-hidden="true" />

          <header className="gunner-retro-header" data-purpose="header">
            <div className="gunner-retro-header-top">
              <h1 className="gunner-retro-title">
                <span>GUNNER:</span>
                <span>RETRO SHOOTER</span>
                <span>CONTROL CENTER</span>
              </h1>
              <div className="gunner-retro-dots" aria-hidden="true">
                <span />
                <span />
                <span />
              </div>
            </div>
            <div className="gunner-retro-meta">
              <span>Cabinet: <strong>{deviceId}</strong></span>
              <span className="divider">|</span>
              <span>
                Fleet Status:{' '}
                <strong className={devices.length > 0 ? 'online' : 'offline'}>
                  {devices.length > 0 ? 'Connected' : 'Offline'}
                </strong>
              </span>
            </div>
          </header>

          <nav className="gunner-retro-nav" data-purpose="navigation" aria-label="Gunner sections">
            {GUNNER_TABS.map(tab => (
              <button
                key={tab.id}
                type="button"
                className={`gunner-retro-nav-btn ${activeTab === tab.id ? 'active' : ''}`}
                onClick={() => setActiveTab(tab.id)}
              >
                {tab.label}
              </button>
            ))}
          </nav>

          <section className="gunner-retro-alert" data-purpose="alert-system" role="status" aria-live="polite">
            <span className="icon">⚠</span>
            <span>Critical Alert: Gun 2P low battery (20%)</span>
          </section>

          <div className="panel-header">
            <div className="panel-title">
              {/* Panel avatar (optional). Put file at frontend/public/lightguns-avatar.(png|jpg|jpeg) */}
              <AvatarImg alt="Light Guns Avatar" className="panel-avatar" />
              <div className="title-text">
                <h1>
                  {activeTab === 'retro-modes'
                    ? 'Retro Engine Selection'
                    : activeTab === 'profiles'
                      ? 'Profiles Management'
                      : 'Calibration Operations'}
                </h1>
                <p>
                  {activeTab === 'retro-modes'
                    ? 'Tune arcade engine profiles, sensitivity curves, and recoil behavior.'
                    : activeTab === 'profiles'
                      ? 'Manage saved shooter profiles, loadouts, and cabinet-specific presets.'
                      : 'Cyber-calibrate your light guns, profiles, and live targeting stack'}
                </p>
              </div>
            </div>
            <div className="panel-header-actions">
              <button className="chat-toggle" onClick={() => setChatOpen(o => !o)} aria-expanded={chatOpen} aria-controls="chat-panel">
                <span>💬</span>
                <span>{chatOpen ? 'Close Chat' : 'Open Chat'}</span>
              </button>
            </div>
          </div>

          {toast && (
            <div className={`toast-banner ${toast.type}`}>
              {toast.text}
            </div>
          )}

          {activeTab === 'retro-modes' ? (
            <div className="gunner-engine-layout" data-purpose="content-grid">
              <section className="calibration-section">
                <div className="section-title">
                  <span>🕹️</span>
                  <span>Engine Matrix</span>
                </div>

                <div className="gunner-engine-grid">
                  {RETRO_ENGINES.map(engine => (
                    <button
                      key={engine.id}
                      type="button"
                      className={`gunner-engine-card ${selectedRetroEngineId === engine.id ? 'active' : ''}`}
                      onClick={() => setSelectedRetroEngineId(engine.id)}
                    >
                      <span className={`engine-dot ${engine.status}`} aria-hidden="true" />
                      <h4>{engine.name}</h4>
                      <p>{engine.description}</p>
                    </button>
                  ))}
                </div>
              </section>

              <section className="calibration-section">
                <div className="section-title">
                  <span>⚙️</span>
                  <span>Mode Controls</span>
                </div>

                <div className="gunner-engine-meta">
                  <h3>{selectedRetroEngine.name}</h3>
                  <span className={`engine-chip ${selectedRetroEngine.status}`}>{selectedRetroEngine.status}</span>
                </div>
                <p className="gunner-engine-description">{selectedRetroEngine.description}</p>

                <label className="gunner-slider-row">
                  <span>Sensitivity</span>
                  <input
                    type="range"
                    min="0"
                    max="100"
                    value={retroSettings.sensitivity}
                    onChange={event => handleRetroSettingChange('sensitivity', Number(event.target.value))}
                  />
                  <strong>{retroSettings.sensitivity}%</strong>
                </label>

                <label className="gunner-slider-row">
                  <span>Smoothing</span>
                  <input
                    type="range"
                    min="0"
                    max="100"
                    value={retroSettings.smoothing}
                    onChange={event => handleRetroSettingChange('smoothing', Number(event.target.value))}
                  />
                  <strong>{retroSettings.smoothing}%</strong>
                </label>

                <label className="gunner-slider-row">
                  <span>Recoil Boost</span>
                  <input
                    type="range"
                    min="0"
                    max="100"
                    value={retroSettings.recoil}
                    onChange={event => handleRetroSettingChange('recoil', Number(event.target.value))}
                  />
                  <strong>{retroSettings.recoil}%</strong>
                </label>

                <div className="gunner-profile-select-row">
                  <span>Display Profile</span>
                  <select
                    className="lightgun-select"
                    value={retroSettings.profile}
                    onChange={event => handleRetroSettingChange('profile', event.target.value)}
                  >
                    <option value="crt-15khz">CRT 15kHz</option>
                    <option value="lcd-low-latency">LCD Low Latency</option>
                    <option value="projector-wide">Projector Wide</option>
                  </select>
                </div>

                <div className="action-buttons" style={{ marginTop: 16 }}>
                  <button
                    className="action-btn primary"
                    onClick={() => setToast({ type: 'success', text: `${selectedRetroEngine.name} mode applied.` })}
                  >
                    Apply Retro Mode
                  </button>
                  <button
                    className="action-btn secondary"
                    onClick={() => {
                      setRetroSettings({ sensitivity: 68, smoothing: 42, recoil: 55, profile: 'crt-15khz' })
                      setToast({ type: 'warning', text: 'Retro mode settings reset to defaults.' })
                    }}
                  >
                    Reset Defaults
                  </button>
                </div>
              </section>
            </div>
          ) : activeTab === 'profiles' ? (
            <div className="gunner-profiles-layout" data-purpose="profiles-grid">
              <aside className="calibration-section gunner-profiles-list-column">
                <div className="section-title" ref={profilesSectionRef}>
                  <span>🎮</span>
                  <span>Profile List</span>
                </div>
                <p className="gunner-profiles-subtitle">Select and stage shooter profiles for your cabinet.</p>

                <div className="gunner-profiles-cards">
                  {profileOptions.length === 0 ? (
                    <div className="gunner-profile-empty">
                      No saved profiles yet. Run calibration and save your first profile.
                    </div>
                  ) : (
                    profileOptions.map(profile => (
                      <button
                        key={profile.game}
                        type="button"
                        className={`gunner-profile-card ${profileSelection === profile.game ? 'active' : ''}`}
                        onClick={() => handleProfileCardSelect(profile.game)}
                      >
                        <span className="gunner-profile-card-icon" aria-hidden="true">🔫</span>
                        <h3>{profile.game}</h3>
                        <p>Last Played: {formatProfileTimestamp(profile.updated_at || profile.created_at)}</p>
                      </button>
                    ))
                  )}
                </div>
              </aside>

              <section className="calibration-section gunner-profiles-manager-column">
                <div className="section-title">
                  <span>🧩</span>
                  <span>Profile Manager</span>
                </div>

                <div className="gunner-profiles-manager-meta">
                  <span>[MAC: {deviceId}]</span>
                  <span>[Fleet Profiles: {profileOptions.length}]</span>
                </div>

                <div className="gunner-profiles-form-row">
                  <label htmlFor="gunner-profile-select">Saved Profile</label>
                  <div className="gunner-profiles-inline-actions">
                    <select
                      id="gunner-profile-select"
                      className="lightgun-select"
                      value={profileSelection}
                      onChange={handleProfileSelectChange}
                      disabled={profileStatus === 'loading'}
                      aria-label="Select saved profile"
                    >
                      <option value="">Select profile</option>
                      {profileOptions.map(profile => (
                        <option key={profile.game} value={profile.game}>
                          {profile.game} {profile.created_at ? `(${new Date(profile.created_at).toLocaleDateString()})` : ''}
                        </option>
                      ))}
                    </select>
                    <button
                      type="button"
                      className="action-btn secondary"
                      onClick={handleLoadProfile}
                      disabled={profileStatus === 'loading' || !profileSelection}
                    >
                      {profileStatus === 'loading' ? 'Loading…' : 'Load'}
                    </button>
                  </div>
                </div>

                <div className="gunner-profiles-form-row">
                  <label htmlFor="gunner-profile-name">New Profile Name</label>
                  <div className="gunner-profiles-inline-actions">
                    <input
                      id="gunner-profile-name"
                      className="lightgun-input"
                      value={customProfileName}
                      onChange={handleCustomProfileChange}
                      placeholder="e.g. time-crisis, house-of-dead"
                      aria-label="New profile name"
                    />
                    <button
                      type="button"
                      className="action-btn secondary"
                      onClick={fetchProfileList}
                      title="Refresh profile list"
                    >
                      Refresh
                    </button>
                  </div>
                </div>

                <div className="gunner-profiles-preview">
                  <h3>Profile Preview</h3>
                  {profileDetails ? (
                    <div className="gunner-profiles-preview-grid">
                      <div>Game: {profileDetails.game}</div>
                      <div>Points: {profileDetails.points?.length || 0}</div>
                      <div>Device: {selectedDevice?.name || 'N/A'}</div>
                      <div>
                        Accuracy: {calibrationResult?.accuracy ? `${(calibrationResult.accuracy * 100).toFixed(1)}%` : '—'}
                      </div>
                    </div>
                  ) : (
                    <p className="gunner-profiles-preview-empty">Load a profile to inspect saved data.</p>
                  )}
                </div>

                <div className="gunner-profiles-status-card">
                  <div>Selected Profile: {profileSelection || 'None'}</div>
                  <div>Live Points Captured: {calibState.points.length}</div>
                  <div>Current Mode: {gunType}</div>
                  <div>Status: {streaming ? 'Streaming' : (statusBanner || 'Idle')}</div>
                </div>

                <div className="action-buttons" style={{ marginTop: 16 }}>
                  <button
                    className="action-btn primary"
                    onClick={handleSaveProfile}
                    disabled={calibState.points.length !== 9 || savingProfile}
                  >
                    {savingProfile ? 'Saving…' : 'Save Profile'}
                  </button>
                  <button
                    className="action-btn secondary"
                    onClick={handleLoadProfile}
                    disabled={profileStatus === 'loading' || !profileSelection}
                  >
                    Apply Selected
                  </button>
                  <button
                    className="action-btn secondary"
                    onClick={handleTestAccuracy}
                    disabled={calibState.points.length !== 9 && !(profileDetails?.points?.length === 9)}
                  >
                    Test Accuracy
                  </button>
                  <button
                    className="action-btn secondary"
                    onClick={handleReset}
                    disabled={calibState.status === 'idle'}
                  >
                    Reset
                  </button>
                </div>
              </section>
            </div>
          ) : (
            <div className="content-grid gunner-calibration-layout">
              <section className="calibration-section gunner-calibration-hud">
                <div className="section-title">
                  <span>🎯</span>
                  <span>Calibration Combat Deck</span>
                </div>

                <div className="gunner-health-grid">
                  <article className="gunner-health-card player-one">
                    <div className="gunner-health-head">
                      <h3>1P Gun: {selectedDevice?.name || 'No Device Detected'}</h3>
                      <span>{calibState.status === 'calibrating' ? 'tracking' : 'stable'}</span>
                    </div>
                    <p>{devices.length > 0 ? 'Online / Active' : 'Offline / Standby'}</p>
                    <div className="gunner-health-meter" role="progressbar" aria-valuemin={0} aria-valuemax={100} aria-valuenow={calibrationProgress}>
                      <span style={{ width: `${Math.max(calibrationProgress, 6)}%` }} />
                    </div>
                    <strong>{calibrationProgress}%</strong>
                  </article>

                  <article className="gunner-health-card player-two">
                    <div className="gunner-health-head">
                      <h3>2P Link: {profileSelection || 'Unassigned'}</h3>
                      <span>{profileSelection ? 'connected' : 'low batt'}</span>
                    </div>
                    <p>{profileSelection ? 'Connected / Ready' : 'Select a profile to sync'}</p>
                    <div className="gunner-health-meter" role="progressbar" aria-valuemin={0} aria-valuemax={100} aria-valuenow={profileSignal}>
                      <span style={{ width: `${profileSignal}%` }} />
                    </div>
                    <strong>{profileSignal}%</strong>
                  </article>
                </div>

                <div className="gunner-calibration-grid">
                  <article className="gunner-mini-panel">
                    <h4>Sensor Grid Analytics</h4>
                    <div className="gunner-mini-stats">
                      <div><span>TL Signal</span><strong>{calibState.points[0] ? 'Locked' : 'Awaiting'}</strong></div>
                      <div><span>TR Signal</span><strong>{calibState.points[2] ? 'Locked' : 'Awaiting'}</strong></div>
                      <div><span>BL Signal</span><strong>{calibState.points[6] ? 'Locked' : 'Awaiting'}</strong></div>
                      <div><span>BR Signal</span><strong>{calibState.points[8] ? 'Locked' : 'Awaiting'}</strong></div>
                    </div>
                    <p className="gunner-mini-footnote">Active Monitoring • Latency: {streaming ? 'Live stream' : 'Idle'}</p>
                  </article>

                  <article className="gunner-mini-panel">
                    <h4>Connection Matrix</h4>
                    <div className="gunner-connection-map">
                      <span className="endpoint">GUN {selectedDeviceId ? '(1P)' : '(--)'}</span>
                      <span className="matrix-node">IR ARRAY</span>
                      <span className="endpoint">{profileSelection ? 'USR + HUD' : 'NO PROFILE'}</span>
                    </div>
                    <button
                      type="button"
                      className="action-btn secondary gunner-scan-btn"
                      onClick={fetchDevices}
                      disabled={loading}
                    >
                      {loading ? 'Scanning…' : 'Scan Hardware'}
                    </button>
                  </article>
                </div>

                <div
                  className="target-display gunner-target-display-hud"
                  ref={targetRef}
                  role="button"
                  tabIndex={0}
                  onClick={handleTargetClick}
                  onKeyDown={handleTargetKeyDown}
                  aria-label="Calibration target area"
                >
                  <div className="crosshair" aria-hidden="true" />
                  <div className="accuracy-text">{statusBanner || 'Click center target to continue'}</div>
                </div>

                <div className="action-buttons" style={{ marginTop: 20 }}>
                  <button
                    className="action-btn primary"
                    onClick={handleStartCalib}
                    disabled={loading || calibState.status === 'calibrating'}
                  >
                    {calibState.status === 'calibrating' ? `Calibrating (${calibState.currentPoint}/9)` : 'Start Calibration'}
                  </button>
                  <button
                    className="action-btn secondary"
                    onClick={handleSkipStep}
                    disabled={calibState.status !== 'calibrating'}
                  >
                    Skip Step
                  </button>
                  <button
                    className="action-btn secondary"
                    onClick={() => dispatch({ type: 'RESET' })}
                    disabled={calibState.status === 'idle'}
                  >
                    Reset
                  </button>
                </div>

                {calibState.error && (
                  <div className="gunner-calibration-error">⚠ {calibState.error}</div>
                )}
              </section>

              <section className="calibration-section gunner-calibration-console">
                <div className="section-title">
                  <span>🧠</span>
                  <span>Command Console</span>
                </div>

                <div className="gunner-console-list">
                  <div className="gunner-console-row">
                    <span>Connection</span>
                    <strong className={devices.length > 0 ? 'online' : 'offline'}>{devices.length > 0 ? 'Online' : 'Offline'}</strong>
                  </div>

                  <div className="gunner-console-row">
                    <span>Device</span>
                    <div className="gunner-console-controls">
                      <select className="lightgun-select" value={selectedDeviceId} onChange={handleDeviceChange} aria-label="Select light gun device">
                        {devices.map(device => (
                          <option key={device.id} value={device.id}>{device.name || device.id}</option>
                        ))}
                      </select>
                      <button type="button" className="inline-refresh" onClick={fetchDevices} disabled={loading} aria-label="Refresh device list">↻</button>
                    </div>
                  </div>

                  <div className="gunner-console-row">
                    <span>Gun Type</span>
                    <select className="lightgun-select" value={gunType} onChange={handleGunTypeChange} aria-label="Select gun type">
                      {GUN_TYPES.map(type => (
                        <option key={type.value} value={type.value}>{type.label}</option>
                      ))}
                    </select>
                  </div>

                  <div className="gunner-console-row">
                    <span>Handedness</span>
                    <select className="lightgun-select" value={handedness} onChange={e => setHandedness(e.target.value)} aria-label="Select handedness">
                      {HAND_OPTIONS.map(option => (
                        <option key={option.value} value={option.value}>{option.label}</option>
                      ))}
                    </select>
                  </div>

                  <div className="gunner-console-row">
                    <span>Calib Status</span>
                    <strong>
                      {calibState.status === 'done'
                        ? 'Complete'
                        : calibState.status === 'calibrating'
                          ? `In Progress (${calibState.currentPoint}/9)`
                          : calibState.status === 'error'
                            ? `Error: ${calibState.error}`
                            : 'Not Started'}
                    </strong>
                  </div>
                </div>

                <div className="section-title gunner-profile-ops-title">
                  <span>🗂️</span>
                  <span>Profile Ops</span>
                </div>
                <div className="gunner-profiles-status-card">
                  <div>Selected Profile: {profileSelection || 'None'}</div>
                  <div>Saved Profiles: {profileOptions.length}</div>
                  <div>Points Captured: {calibState.points.length}</div>
                  <div>Accuracy: {calibrationResult?.accuracy ? `${(calibrationResult.accuracy * 100).toFixed(1)}%` : '—'}</div>
                  <div>Status: {streaming ? 'Streaming' : (statusBanner || 'Idle')}</div>
                </div>
                <div className="action-buttons" style={{ marginTop: 12 }}>
                  <button
                    className="action-btn secondary"
                    onClick={() => setActiveTab('profiles')}
                  >
                    Open Profiles Tab
                  </button>
                  <button
                    className="action-btn secondary"
                    onClick={handleLoadProfile}
                    disabled={profileStatus === 'loading' || !profileSelection}
                  >
                    {profileStatus === 'loading' ? 'Loading…' : 'Load Selected'}
                  </button>
                  <button
                    className="action-btn secondary"
                    onClick={handleTestAccuracy}
                    disabled={calibState.points.length !== 9 && !(profileDetails?.points?.length === 9)}
                  >
                    Test Accuracy
                  </button>
                </div>
              </section>
            </div>
          )}
        </div>

        <aside id="chat-panel" className={`chat-panel ${chatOpen ? 'open' : ''}`} aria-label="Light guns chat">
          <div className="chat-header">
            <div className="gunner-info">
              {/* Chat avatar with fallbacks */}
              <AvatarImg alt="Gunner Avatar" className="gunner-avatar-img" />
              <div className="gunner-details">
                <h3>Gunner</h3>
                <span className="gunner-role-badge">Assistant: Gunner</span>
              </div>
            </div>
            <button
              type="button"
              className="close-chat-icon"
              onClick={() => setChatOpen(false)}
              title="Close Chat"
              aria-label="Close chat panel"
            >
              ×
            </button>
          </div>
          <div className="chat-messages" aria-live="polite" aria-label="Chat conversation">
            {chatMessages.map((m, idx) => (
              <div key={idx} className={`message ${m.type}`}><p>{m.text}</p></div>
            ))}
          </div>
          <div className="chat-input-container">
            <div className="chat-input-row">
              <input
                type="text"
                className="chat-input"
                placeholder="Ask about calibration, sensitivity, hardware..."
                aria-label="Chat with Gunner about light gun calibration"
                value={chatInput}
                onChange={(e) => setChatInput(e.target.value)}
                onKeyDown={(e) => { if (e.key === 'Enter') sendChat(chatInput) }}
              />
              <GunnerVoiceControls onTranscript={handleVoiceTranscript} disabled={streaming} />
              <button
                className="send-btn"
                title="Send message"
                aria-label="Send message"
                onClick={() => sendChat(chatInput)}
                disabled={!chatInput.trim()}
              >
                ➤
              </button>
            </div>
            <div style={{
              fontSize: '12px',
              color: '#cbd5f5',
              padding: '8px 12px',
              background: 'rgba(59, 130, 246, 0.08)',
              borderRadius: '6px',
              marginTop: '8px'
            }}>
              Voice shortcuts: say &quot;start calibration&quot;, &quot;save profile&quot;, &quot;reset&quot;, or ask Gunner a question.
            </div>
          </div>
        </aside>
      </div>
    </PanelShell>
  )
}



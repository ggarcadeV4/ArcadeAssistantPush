import React, { useCallback, useEffect, useMemo, useRef, useState } from 'react'
import { speakAsBlinky } from '../../services/ttsClient'
import useLEDPanelState from '../../hooks/useLEDPanelState'
import { useLEDConnection } from '../../hooks/useLEDConnection'
import { useLEDGameBindings } from '../../hooks/useLEDGameBindings'
// Visual components
import ButtonVisualizer from './ButtonVisualizer'
import UserProfileSelector from './UserProfileSelector'
import ColorPalette from './ColorPalette'
import ArcadePanelPreview from './ArcadePanelPreview'
// Tab components (restored)
import GameProfilesTab from './GameProfilesTab'
import RealtimeControlTab from './RealtimeControlTab'
import HardwareTab from './HardwareTab'
import LEDLayoutTab from './LEDLayoutTab'
import CalibrationTab from './CalibrationTab'
// Chat sidebar
import { EngineeringBaySidebar } from '../../panels/_kit/EngineeringBaySidebar'
import '../../panels/_kit/EngineeringBaySidebar.css'
// Service functions
import {
  applyLEDProfile,
  getLEDProfile,
  listLEDProfiles,
  previewLEDProfile,
  setLEDBrightness,
  testLED,
  testAllLEDs,
  flashLEDCalibration,
  applyGameProfileBinding
} from '../../services/ledBlinkyClient'
import { extractButtonsFromPayload } from '../../utils/buttonMapping'
import './LEDBlinkyPanel.css'

/** Blinky persona config for EngineeringBaySidebar */
const BLINKY_PERSONA = {
  id: 'blinky',
  name: 'BLINKY',
  icon: '💡',
  icon2: '🎮',
  accentColor: '#9333ea',
  accentGlow: 'rgba(147, 51, 234, 0.35)',
  scannerLabel: 'SCANNING PORTS...',
  voiceProfile: 'blinky',
  emptyHint: 'Ask Blinky about LED colors, game profiles, calibration, or wiring.',
  chips: [
    { id: 'status', label: 'LED status', prompt: 'Show me the current LED hardware status.' },
    { id: 'rainbow', label: 'Rainbow test', prompt: 'Run a rainbow test across all LEDs.' },
    { id: 'calibrate', label: 'Start calibration', prompt: 'Start the LED wiring calibration wizard.' },
    { id: 'profile', label: 'Load profile', prompt: 'Show me the available LED profiles I can apply.' },
  ],
}

// ═══════════════════════════════════════════════════════════════════════
//  Utility functions (preserved from stability pass)
// ═══════════════════════════════════════════════════════════════════════

const buildButtons = (colors, playerCount) => {
  const buttons = {}
  Object.entries(colors || {}).forEach(([key, value]) => {
    const match = /^p(\d+)\./i.exec(key)
    if (!match || typeof value !== 'string' || !value) return
    if (playerCount <= 2 && Number(match[1]) > 2) return
    buttons[key] = { color: value }
  })
  return buttons
}

const colorsFromButtons = (buttons = {}) => {
  const colors = {}
  Object.entries(buttons).forEach(([key, value]) => {
    const color = typeof value === 'string' ? value : value?.color
    if (color) colors[key] = color
  })
  return colors
}

const playerCountFromButtons = (buttons = {}) => (
  Object.keys(buttons).some((key) => /^p[34]\./i.test(key)) ? 4 : 2
)

const profileFileStem = (profile = {}) => {
  if (typeof profile?.filename === 'string' && profile.filename.trim()) {
    return profile.filename.replace(/\.json$/i, '')
  }
  if (typeof profile?.profile_name === 'string' && profile.profile_name.trim()) {
    return profile.profile_name.trim()
  }
  return ''
}

const timeLabel = (value) => {
  if (!value) return 'Unknown'
  const stamp = typeof value === 'number' ? value : Date.parse(value)
  if (Number.isFinite(stamp)) {
    const date = new Date(stamp)
    if (!Number.isNaN(date.getTime())) return date.toLocaleTimeString()
  }
  return String(value)
}

const formatTimestampValue = timeLabel

const deviceName = (device = {}) => (
  device.device_id || device.id || device.name || device.board_name || 'unknown-device'
)

const deviceChannels = (device = {}) => {
  if (typeof device.channel_count === 'number') return device.channel_count
  if (typeof device.channels === 'number') return device.channels
  if (Array.isArray(device.channels)) return device.channels.length
  if (typeof device.total_channels === 'number') return device.total_channels
  return null
}

const describeHardware = (connection) => {
  const connectedCount = connection.connectedDevices.length
  const discoveredCount = connection.registryDevices.length
  const lastError =
    connection.hardwareStatus?.backend_error ||
    connection.engineDiagnostics?.last_error ||
    null

  if (lastError) {
    return {
      label: 'Service Error',
      color: '#ef4444',
      detail: typeof lastError === 'string' ? lastError : 'The LED service reported an error.'
    }
  }

  if (connectedCount > 0) {
    return {
      label: 'Hardware Live',
      color: '#22c55e',
      detail: `${connectedCount} LED controller${connectedCount === 1 ? '' : 's'} currently reporting through the engine.`
    }
  }

  if (connection.simulationMode) {
    return {
      label: 'Simulation',
      color: '#f59e0b',
      detail: connection.registryMessage || 'No physical LED controller is attached. Preview and tests stay honest but virtual.'
    }
  }

  if (discoveredCount > 0) {
    return {
      label: 'Discovered',
      color: '#38bdf8',
      detail: `${discoveredCount} device${discoveredCount === 1 ? '' : 's'} discovered, but none are reporting as active LED boards yet.`
    }
  }

  if (connection.connectionStatus === 'connected') {
    return {
      label: 'Gateway Only',
      color: '#94a3b8',
      detail: 'The gateway is connected, but the backend has not reported a usable LED board.'
    }
  }

  if (connection.connectionStatus === 'connecting') {
    return {
      label: 'Connecting',
      color: '#38bdf8',
      detail: 'Connecting to the LED gateway and refreshing cabinet status.'
    }
  }

  return {
    label: 'Offline',
    color: '#94a3b8',
    detail: 'The LED gateway is disconnected. Refresh to pull the latest backend state.'
  }
}

const summarizePreview = (preview) => ({
  targetFile: preview?.target_file || 'Unknown',
  totalChannels: typeof preview?.total_channels === 'number' ? preview.total_channels : 0,
  hasChanges: Boolean(preview?.has_changes),
  missingButtons: Array.isArray(preview?.missing_buttons) ? preview.missing_buttons : [],
  diff: preview?.diff || 'No diff available.'
})

// ═══════════════════════════════════════════════════════════════════════
//  Tab configuration
// ═══════════════════════════════════════════════════════════════════════

const TABS = [
  { id: 'profiles',    label: '🎮 Game Profiles' },
  { id: 'realtime',    label: '⚡ Real-time' },
  { id: 'hardware',    label: '🔧 Hardware' },
  { id: 'layout',      label: '📐 LED Layout' },
  { id: 'calibration', label: '🎯 Calibration' },
  { id: 'design',      label: '🖌️ Design' },
]

// ═══════════════════════════════════════════════════════════════════════
//  WiringWizard bridge component for CalibrationTab
// ═══════════════════════════════════════════════════════════════════════

function WiringWizardBridge({ wizardState, numPlayers, onMapButton, onComplete, onCancel }) {
  if (!wizardState?.isActive) {
    return (
      <div style={{ padding: '20px', background: '#0f0f0f', borderRadius: '12px', border: '1px solid #7c3aed' }}>
        <div style={{ fontSize: '16px', fontWeight: '700', color: '#9333ea', marginBottom: '12px', display: 'flex', alignItems: 'center', gap: '8px' }}>
          <span>🎯</span><span>Wiring Wizard</span>
        </div>
        <p style={{ color: '#9ca3af', fontSize: '13px', margin: 0, lineHeight: 1.6 }}>
          Start calibration from the controls above to begin the guided wiring wizard.
          The wizard will blink each LED port in sequence — click the corresponding button on the panel preview to map it.
        </p>
      </div>
    )
  }

  return (
    <div style={{ padding: '20px', background: '#0f0f0f', borderRadius: '12px', border: '1px solid rgba(234, 179, 8, 0.3)' }}>
      <div style={{ fontSize: '16px', fontWeight: '700', color: '#fde047', marginBottom: '16px', display: 'flex', alignItems: 'center', gap: '8px' }}>
        <span>🎯</span><span>Wiring Wizard Active</span>
      </div>
      <div style={{ color: '#d1d5db', fontSize: '14px', marginBottom: '12px' }}>
        Port {wizardState.currentPort || '?'} of {wizardState.totalPorts || '?'} — Click the button that is blinking on your control panel.
      </div>
      <div style={{ height: '6px', background: '#1f2937', borderRadius: '3px', overflow: 'hidden', marginBottom: '12px' }}>
        <div style={{
          width: `${wizardState.progressPercent || 0}%`,
          height: '100%',
          background: 'linear-gradient(90deg, #eab308, #f59e0b)',
          borderRadius: '3px',
          transition: 'width 0.3s'
        }} />
      </div>
      <div style={{ color: '#9ca3af', fontSize: '12px', marginBottom: '16px' }}>
        {wizardState.mappedCount || 0} mapped · {wizardState.skippedCount || 0} skipped
      </div>
      <div style={{ display: 'flex', gap: '8px' }}>
        <button className="led-panel__preset-btn" onClick={() => onMapButton?.('skip')}>Skip Port</button>
        <button className="led-panel__preset-btn" onClick={onCancel}>Cancel</button>
        {(wizardState.mappedCount || 0) > 0 && (
          <button className="led-panel__preset-btn led-panel__preset-btn--active" onClick={onComplete}>Finish & Save</button>
        )}
      </div>
    </div>
  )
}

// ═══════════════════════════════════════════════════════════════════════
//  Main LED Blinky Panel Orchestrator
// ═══════════════════════════════════════════════════════════════════════

export default function LEDBlinkyPanel() {
  // ─── Core State (kept from stability pass) ──────────────────────────
  const [playerCount, setPlayerCount] = useState(4)
  const [brightness, setBrightness] = useState(75)
  const [testEffect, setTestEffect] = useState('rainbow')
  const [activeProfileId, setActiveProfileId] = useState('bobby')
  const [storedProfiles, setStoredProfiles] = useState([])
  const [selectedStoredProfile, setSelectedStoredProfile] = useState('')
  const [profileName, setProfileName] = useState('operator-layout')
  const [profilePreview, setProfilePreview] = useState(null)
  const [previewSignature, setPreviewSignature] = useState(null)
  const [backupPath, setBackupPath] = useState(null)
  const [panelMessage, setPanelMessage] = useState(null)
  const [isLoadingProfiles, setIsLoadingProfiles] = useState(false)
  const [isPreviewing, setIsPreviewing] = useState(false)
  const [isApplying, setIsApplying] = useState(false)
  const [isRunningEffect, setIsRunningEffect] = useState(false)
  const [isTesting, setIsTesting] = useState(false)
  const lastSpokenPort = useRef(0)

  // ─── Tab State ──────────────────────────────────────────────────────
  const [activeTab, setActiveTab] = useState('profiles')

  // ─── Chat Drawer State ──────────────────────────────────────────────
  const [chatOpen, setChatOpen] = useState(false)

  // ─── Bridge State: HardwareTab ──────────────────────────────────────
  const [channelTestDevice, setChannelTestDevice] = useState('')
  const [channelTestChannel, setChannelTestChannel] = useState('')
  const [isTestingChannel, setIsTestingChannel] = useState(false)
  const [channelTestResult, setChannelTestResult] = useState(null)

  // ─── Bridge State: RealtimeControlTab ───────────────────────────────
  const [demoLastError, setDemoLastError] = useState(null)
  const [demoTestDuration, setDemoTestDuration] = useState(1500)
  const [isTestingAllLEDs, setIsTestingAllLEDs] = useState(false)
  const [demoFlashPlayer, setDemoFlashPlayer] = useState(1)
  const [demoFlashButton, setDemoFlashButton] = useState(1)
  const [demoFlashColor, setDemoFlashColor] = useState('#ff0000')
  const [isFlashingDemo, setIsFlashingDemo] = useState(false)
  const [mappingForm, setMappingForm] = useState({})

  // ─── Bridge State: LEDLayoutTab ─────────────────────────────────────
  const [channelState, setChannelState] = useState({ channels: {}, target_file: '', total_channels: 0, unmapped: 0, unknown: 0 })
  const [isLoadingChannels, setIsLoadingChannels] = useState(false)
  const [channelSelection, setChannelSelection] = useState({ logicalButton: '', deviceId: '', channel: '' })
  const [channelPreview, setChannelPreview] = useState(null)
  const [isChannelPreviewing, setIsChannelPreviewing] = useState(false)
  const [isChannelApplying, setIsChannelApplying] = useState(false)
  const [isDeletingChannel, setIsDeletingChannel] = useState(false)

  // ─── Bridge State: GameProfilesTab profile library ──────────────────
  const [profileSearchTerm, setProfileSearchTerm] = useState('')

  // ─── Toast ──────────────────────────────────────────────────────────
  const showToast = useCallback((message, type = 'success') => {
    setPanelMessage({ message, type })
    console.log(`Toast [${type}]: ${message}`)
  }, [])

  // ─── Hooks (stability layer — unchanged) ────────────────────────────
  const panel = useLEDPanelState({ showToast })
  const connection = useLEDConnection({ showToast })
  const gameBindings = useLEDGameBindings({ showToast, activeMode: activeTab === 'profiles' ? 'profiles' : null })

  // ─── Derived Colors & Buttons ───────────────────────────────────────
  const editorColors = useMemo(() => {
    if (!panel.design.hasChanges) return panel.resolvedColors
    return { ...panel.IDLE_COLORS, ...panel.design.customColors }
  }, [panel.IDLE_COLORS, panel.design.customColors, panel.design.hasChanges, panel.resolvedColors])

  const currentButtons = useMemo(
    () => buildButtons(editorColors, playerCount),
    [editorColors, playerCount]
  )

  // ─── Derived Status ─────────────────────────────────────────────────
  const currentStatus = connection.connectionStatus === 'connected'
    ? 'connected'
    : connection.hardwareStatus?.backend_error
      ? 'error'
      : connection.simulationMode
        ? 'simulated'
        : connection.connectionStatus || 'disconnected'

  const badge = panel.getStatusBadge(currentStatus)
  const hardwareSummary = useMemo(() => describeHardware(connection), [connection])
  const currentProfileSummary = useMemo(() => summarizePreview(profilePreview), [profilePreview])

  const visibleProfiles = useMemo(
    () => storedProfiles.map((profile) => {
      const value = profileFileStem(profile)
      const scope = profile.scope || 'profile'
      const mappingCount = Array.isArray(profile.mapping_keys) ? profile.mapping_keys.length : 0
      const labelName = profile.profile_name || value
      return {
        value,
        label: `${labelName} (${scope}${mappingCount ? `, ${mappingCount} buttons` : ''})`
      }
    }).filter((profile) => profile.value),
    [storedProfiles]
  )

  // ─── Derived: Profile Library (GameProfilesTab) ─────────────────────
  const filteredProfiles = useMemo(() => {
    if (!profileSearchTerm.trim()) return storedProfiles
    const term = profileSearchTerm.toLowerCase()
    return storedProfiles.filter(p =>
      (p.profile_name || p.filename || '').toLowerCase().includes(term)
    )
  }, [storedProfiles, profileSearchTerm])

  const selectedProfileMeta = useMemo(() =>
    storedProfiles.find(p => profileFileStem(p) === selectedStoredProfile) || null,
    [storedProfiles, selectedStoredProfile]
  )

  const selectedProfileDisplayName = selectedProfileMeta?.profile_name || selectedStoredProfile || ''
  const libraryPreviewReady = Boolean(profilePreview)
  const canApplyLibraryProfile = Boolean(selectedStoredProfile && profilePreview)

  // ─── Derived: Channel Entries (LEDLayoutTab) ────────────────────────
  const channelEntries = useMemo(() =>
    Object.entries(channelState.channels || {}).map(([key, value]) => ({
      logicalButton: key,
      ...(typeof value === 'object' ? value : { device_id: '', channel: '' })
    })),
    [channelState]
  )

  const channelOptions = useMemo(() => {
    const options = []
    for (let p = 1; p <= 4; p++) {
      const btnCount = p <= 2 ? 8 : 4
      for (let i = 1; i <= btnCount; i++) options.push(`p${p}.button${i}`)
      options.push(`p${p}.start`, `p${p}.coin`)
    }
    return options
  }, [])

  // ─── Derived: Wizard Bridge State (CalibrationTab) ──────────────────
  const wizardBridgeState = useMemo(() => ({
    isActive: panel.mode === 'calibration',
    currentPort: panel.wizard.currentPort,
    totalPorts: panel.wizard.totalPorts,
    mappedCount: panel.wizard.mappedCount,
    skippedCount: panel.wizard.skippedCount,
    progressPercent: panel.wizard.progressPercent,
    isLoading: panel.wizard.isLoading,
  }), [panel.mode, panel.wizard])

  // ═════════════════════════════════════════════════════════════════════
  //  Core Handlers (kept from stability pass)
  // ═════════════════════════════════════════════════════════════════════

  const loadProfiles = useCallback(async () => {
    setIsLoadingProfiles(true)
    try {
      const response = await listLEDProfiles()
      const profiles = Array.isArray(response?.profiles) ? response.profiles : []
      setStoredProfiles(profiles)
      setSelectedStoredProfile((current) => current || profileFileStem(profiles[0]) || '')
    } catch (err) {
      showToast(err?.error || err?.detail || err?.message || 'Failed to load stored LED profiles', 'error')
    } finally {
      setIsLoadingProfiles(false)
    }
  }, [showToast])

  const loadStoredProfile = useCallback(async () => {
    if (!selectedStoredProfile) {
      showToast('Select a stored profile first', 'error')
      return
    }
    try {
      const response = await getLEDProfile(selectedStoredProfile)
      const buttons = extractButtonsFromPayload(response?.mapping || {})
      const colors = colorsFromButtons(buttons)
      if (Object.keys(colors).length === 0) {
        showToast('Stored profile has no LED colors', 'error')
        return
      }
      panel.design.replaceCustomColors(colors, response?.profile_name || selectedStoredProfile)
      if (panel.mode !== 'design') {
        panel.toggleDesign()
      }
      setProfileName(response?.profile_name || selectedStoredProfile)
      setPlayerCount(playerCountFromButtons(buttons))
      setProfilePreview(null)
      setPreviewSignature(null)
      setBackupPath(null)
    } catch (err) {
      showToast(err?.error || err?.detail || err?.message || 'Failed to load LED profile', 'error')
    }
  }, [panel.design, panel.mode, panel.toggleDesign, selectedStoredProfile, showToast])

  const buildPayload = useCallback(() => {
    if (Object.keys(currentButtons).length === 0) {
      throw new Error('No LED colors are available to preview.')
    }
    return {
      profile_name: (profileName || '').trim() || 'operator-layout',
      scope: 'profile',
      metadata: { source: 'led-blinky-panel', layout_players: playerCount },
      buttons: currentButtons
    }
  }, [currentButtons, playerCount, profileName])

  const previewCurrent = useCallback(async () => {
    let payload
    try {
      payload = buildPayload()
    } catch (err) {
      showToast(err.message, 'error')
      return
    }
    setIsPreviewing(true)
    try {
      const preview = await previewLEDProfile(payload)
      setProfilePreview(preview)
      setPreviewSignature(JSON.stringify(payload))
      setBackupPath(null)
      showToast('LED profile preview ready', 'success')
    } catch (err) {
      showToast(err?.error || err?.detail || err?.message || 'Failed to preview LED profile', 'error')
    } finally {
      setIsPreviewing(false)
    }
  }, [buildPayload, showToast])

  const applyCurrent = useCallback(async () => {
    let payload
    try {
      payload = buildPayload()
    } catch (err) {
      showToast(err.message, 'error')
      return
    }
    const signature = JSON.stringify(payload)
    if (previewSignature !== signature) {
      showToast('Preview the current layout before applying it', 'error')
      return
    }
    setIsApplying(true)
    try {
      const result = await applyLEDProfile({ ...payload, dry_run: false })
      setProfilePreview(result.preview)
      setBackupPath(result.backup_path || null)
      setPreviewSignature(signature)
      await loadProfiles()
      showToast(
        result.status === 'applied'
          ? 'LED profile applied with backup'
          : 'No LED profile changes detected',
        'success'
      )
    } catch (err) {
      showToast(err?.error || err?.detail || err?.message || 'Failed to apply LED profile', 'error')
    } finally {
      setIsApplying(false)
    }
  }, [buildPayload, loadProfiles, previewSignature, showToast])

  const runSafeTest = useCallback(async () => {
    setIsTesting(true)
    try {
      const result = await testAllLEDs({ durationMs: 1500 })
      showToast(result?.message || 'LED test queued', connection.simulationMode ? 'warning' : 'success')
    } catch (err) {
      showToast(err?.error || err?.detail || err?.message || 'Failed to run LED test', 'error')
    } finally {
      setIsTesting(false)
    }
  }, [connection.simulationMode, showToast])

  const runSelectedEffect = useCallback(async () => {
    setIsRunningEffect(true)
    try {
      const result = await testLED({ effect: testEffect, durationMs: 1500 })
      showToast(result?.message || `Effect queued: ${testEffect}`, connection.simulationMode ? 'warning' : 'success')
    } catch (err) {
      showToast(err?.error || err?.detail || err?.message || 'Failed to run LED effect', 'error')
    } finally {
      setIsRunningEffect(false)
    }
  }, [connection.simulationMode, showToast, testEffect])

  // ═════════════════════════════════════════════════════════════════════
  //  Bridge Handlers
  // ═════════════════════════════════════════════════════════════════════

  // ─── HardwareTab: Channel test ──────────────────────────────────────
  const handleChannelTest = useCallback(async () => {
    if (!channelTestDevice || !channelTestChannel) {
      showToast('Select a device and channel number', 'error')
      return
    }
    setIsTestingChannel(true)
    try {
      const result = await testLED({ device_id: channelTestDevice, channel: parseInt(channelTestChannel, 10), durationMs: 1000 })
      setChannelTestResult(result)
      showToast(result?.message || 'Channel test sent', 'success')
    } catch (err) {
      showToast(err?.error || err?.message || 'Channel test failed', 'error')
    } finally {
      setIsTestingChannel(false)
    }
  }, [channelTestDevice, channelTestChannel, showToast])

  const triggerHardwareTest = useCallback(async (effect) => {
    try {
      const result = await testAllLEDs({ effect: effect || 'rainbow', durationMs: 2000 })
      showToast(result?.message || `Hardware test: ${effect || 'rainbow'}`, 'success')
    } catch (err) {
      showToast(err?.error || err?.message || 'Hardware test failed', 'error')
    }
  }, [showToast])

  // ─── LEDLayoutTab: Channel CRUD ─────────────────────────────────────
  const loadChannelData = useCallback(async () => {
    setIsLoadingChannels(true)
    try {
      const result = await panel.loadChannelMappings()
      if (result) setChannelState(result)
    } catch (err) {
      console.error('[LEDBlinky] Failed to load channel mappings:', err)
    } finally {
      setIsLoadingChannels(false)
    }
  }, [panel])

  const handleSelectChannel = useCallback((entry) => {
    setChannelSelection({
      logicalButton: entry?.logicalButton || '',
      deviceId: entry?.device_id || '',
      channel: entry?.channel ?? ''
    })
  }, [])

  const handleChannelFieldChange = useCallback((field, value) => {
    setChannelSelection(prev => ({ ...prev, [field]: value }))
  }, [])

  const previewChannelUpdate = useCallback(async () => {
    if (!channelSelection.logicalButton) { showToast('Select a logical button first', 'error'); return }
    setIsChannelPreviewing(true)
    try {
      if (panel.calibration.calibrationToken) {
        const result = await panel.calibration.flashCalibrationHelper({ logicalButton: channelSelection.logicalButton })
        setChannelPreview(result)
        showToast('Channel flash sent', 'success')
      } else {
        showToast('Start a calibration session to preview channels', 'info')
      }
    } catch (err) {
      showToast(err?.error || err?.message || 'Channel preview failed', 'error')
    } finally {
      setIsChannelPreviewing(false)
    }
  }, [channelSelection, panel.calibration, showToast])

  const applyChannelUpdate = useCallback(async () => {
    if (!channelSelection.logicalButton || !channelSelection.deviceId || !channelSelection.channel) {
      showToast('Fill all channel fields before applying', 'error')
      return
    }
    setIsChannelApplying(true)
    try {
      await panel.calibration.assignCalibrationMapping({
        logicalButton: channelSelection.logicalButton,
        deviceId: channelSelection.deviceId,
        channel: parseInt(channelSelection.channel, 10)
      })
      await loadChannelData()
      setChannelPreview(null)
      showToast('Channel mapping saved', 'success')
    } catch (err) {
      showToast(err?.error || err?.message || 'Failed to save channel mapping', 'error')
    } finally {
      setIsChannelApplying(false)
    }
  }, [channelSelection, panel.calibration, loadChannelData, showToast])

  const removeChannelMapping = useCallback(async () => {
    if (!channelSelection.logicalButton) { showToast('Select a channel to remove', 'error'); return }
    setIsDeletingChannel(true)
    try {
      showToast('Channel removal: re-map to override the existing assignment', 'info')
    } finally {
      setIsDeletingChannel(false)
    }
  }, [channelSelection, showToast])

  // ─── CalibrationTab: Wizard bridge ──────────────────────────────────
  const handleWizardMapButton = useCallback((buttonKey) => {
    if (buttonKey === 'skip') {
      panel.skipPort()
      return
    }
    const match = /^p(\d+)\.(.+)$/i.exec(buttonKey)
    if (match) {
      panel.handleButtonClick(parseInt(match[1], 10), match[2])
    }
  }, [panel])

  const toggleLED = useCallback((player, button) => {
    testLED({ logical_button: `p${player}.${button}`, durationMs: 500 }).catch(() => {})
  }, [])

  // ─── GameProfilesTab: Profile Library ───────────────────────────────
  const previewProfileFromLibrary = useCallback(async (profileName) => {
    const target = profileName || selectedStoredProfile
    if (!target) { showToast('Select a profile first', 'error'); return }
    setIsPreviewing(true)
    try {
      const response = await getLEDProfile(target)
      const buttons = extractButtonsFromPayload(response?.mapping || {})
      if (Object.keys(buttons).length === 0) {
        showToast('Profile has no LED mappings', 'error')
        setIsPreviewing(false)
        return
      }
      const payload = {
        profile_name: response?.profile_name || target,
        scope: 'profile',
        metadata: { source: 'led-blinky-panel', layout_players: playerCount },
        buttons
      }
      const preview = await previewLEDProfile(payload)
      setProfilePreview(preview)
      setPreviewSignature(JSON.stringify(payload))
      showToast('Profile preview ready', 'success')
    } catch (err) {
      showToast(err?.error || err?.message || 'Failed to preview profile', 'error')
    } finally {
      setIsPreviewing(false)
    }
  }, [selectedStoredProfile, playerCount, showToast])

  const applyProfileFromLibrary = useCallback(async (profileName) => {
    const target = profileName || selectedStoredProfile
    if (!target) { showToast('Select a profile first', 'error'); return }
    setIsApplying(true)
    try {
      const response = await getLEDProfile(target)
      const buttons = extractButtonsFromPayload(response?.mapping || {})
      const payload = {
        profile_name: response?.profile_name || target,
        scope: 'profile',
        metadata: { source: 'led-blinky-panel', layout_players: playerCount },
        buttons
      }
      const result = await applyLEDProfile({ ...payload, dry_run: false })
      setProfilePreview(result.preview)
      setBackupPath(result.backup_path || null)
      await loadProfiles()
      showToast('Profile applied with backup', 'success')
    } catch (err) {
      showToast(err?.error || err?.message || 'Failed to apply profile', 'error')
    } finally {
      setIsApplying(false)
    }
  }, [selectedStoredProfile, playerCount, loadProfiles, showToast])

  const editProfileInDesigner = useCallback((profileName) => {
    if (profileName) setSelectedStoredProfile(profileName)
    setActiveTab('design')
  }, [])

  // ─── RealtimeControlTab: Utilities ──────────────────────────────────
  const buildButtonsFromForm = useCallback((form) => {
    const buttons = {}
    Object.entries(form || {}).forEach(([key, value]) => {
      if (typeof value === 'string') buttons[key] = { color: value }
      else if (value?.color) buttons[key] = value
    })
    return buttons
  }, [])

  const buildFormFromButtons = useCallback((buttons) => {
    const form = {}
    Object.entries(buttons || {}).forEach(([key, value]) => {
      form[key] = typeof value === 'string' ? { color: value, label: key } : { ...value, label: key }
    })
    return form
  }, [])

  // ═════════════════════════════════════════════════════════════════════
  //  Effects
  // ═════════════════════════════════════════════════════════════════════

  useEffect(() => { loadProfiles() }, [loadProfiles])

  useEffect(() => {
    if (selectedStoredProfile) {
      gameBindings.setSelectedGameProfileName(selectedStoredProfile)
    }
  }, [gameBindings, selectedStoredProfile])

  useEffect(() => {
    const timer = setTimeout(() => {
      setLEDBrightness(brightness).catch(() => {})
    }, 200)
    return () => clearTimeout(timer)
  }, [brightness])

  useEffect(() => {
    if (panel.mode !== 'calibration') {
      lastSpokenPort.current = 0
      return
    }
    const port = panel.wizard.currentPort
    if (port && port !== lastSpokenPort.current) {
      lastSpokenPort.current = port
      speakAsBlinky(
        port === 1
          ? `Calibration started. Port 1 of ${panel.wizard.totalPorts}. Click the button that is lit.`
          : `Port ${port} of ${panel.wizard.totalPorts}. Click the button that is blinking.`
      )
    }
  }, [panel.mode, panel.wizard.currentPort, panel.wizard.totalPorts])

  // Load channel data when layout or calibration tab is active
  useEffect(() => {
    if (activeTab === 'layout' || activeTab === 'calibration') {
      loadChannelData()
    }
  }, [activeTab, loadChannelData])

  // Sync mapping form from current button state
  useEffect(() => {
    setMappingForm(buildFormFromButtons(currentButtons))
  }, [currentButtons, buildFormFromButtons])

  // ═════════════════════════════════════════════════════════════════════
  //  Render
  // ═════════════════════════════════════════════════════════════════════

  return (
    <div className="led-panel">

          {/* ─── Header ───────────────────────────────────── */}
          <div className="led-panel__header">
            <div className="led-panel__title-group">
              <h1 className="led-panel__title">LED Blinky</h1>
              <div className={`led-panel__status-badge ${badge.className}`}>
                <span className={`led-panel__status-dot ${badge.dotClass}`} />
                {badge.text}
              </div>
            </div>
            <UserProfileSelector activeProfileId={activeProfileId} onProfileChange={setActiveProfileId} />
          </div>

          {/* ─── Toast Banner ──────────────────────────────── */}
          {panelMessage && (
            <div className={`led-panel__ops-banner led-panel__ops-banner--${panelMessage.type || 'info'}`}>
              {panelMessage.message}
            </div>
          )}

          {/* ─── Controls Row ─────────────────────────────── */}
          <div className="led-panel__controls">
            <div className="led-panel__control-group">
              <span className="led-panel__control-label">Layout:</span>
              <select
                className="led-panel__select"
                value={playerCount}
                onChange={(event) => setPlayerCount(Number(event.target.value))}
              >
                <option value={4}>4-Player</option>
                <option value={2}>2-Player</option>
              </select>
            </div>
            <div className="led-panel__control-group">
              <button
                className={`led-panel__preset-btn ${panel.mode === 'calibration' ? 'led-panel__preset-btn--active' : ''}`}
                onClick={panel.toggleCalibration}
                disabled={panel.wizard.isLoading}
              >
                {panel.wizard.isLoading ? 'Working...' : panel.mode === 'calibration' ? 'Stop Calibration' : 'Calibrate'}
              </button>
            </div>
            <div className="led-panel__control-group">
              <button
                className={`led-panel__preset-btn ${panel.mode === 'design' ? 'led-panel__preset-btn--active' : ''}`}
                onClick={panel.toggleDesign}
              >
                {panel.mode === 'design' ? 'Exit Design' : 'Design'}
              </button>
            </div>
            <div className="led-panel__control-group">
              <span className="led-panel__control-label">Effect:</span>
              <select
                className="led-panel__select"
                value={testEffect}
                onChange={(event) => setTestEffect(event.target.value)}
              >
                <option value="rainbow">Rainbow</option>
                <option value="pulse">Pulse</option>
                <option value="chase">Chase</option>
                <option value="solid">Solid</option>
              </select>
            </div>
            <div className="led-panel__control-group">
              <button className="led-panel__preset-btn" onClick={runSelectedEffect} disabled={isRunningEffect}>
                {isRunningEffect ? 'Running...' : 'Run Effect'}
              </button>
            </div>
            <div className="led-panel__control-group">
              <button className="led-panel__preset-btn" onClick={runSafeTest} disabled={isTesting}>
                {isTesting ? 'Testing...' : 'All Channels'}
              </button>
            </div>
            <div className="led-panel__control-group led-panel__brightness">
              <span className="led-panel__control-label">Brightness</span>
              <input
                type="range"
                className="led-panel__slider"
                min={10}
                max={100}
                value={brightness}
                onChange={(event) => setBrightness(Number(event.target.value))}
              />
              <span className="led-panel__brightness-value">{brightness}%</span>
            </div>

          </div>

          {/* ─── Calibration Bar (visible during calibration) ─ */}
          {panel.mode === 'calibration' && (
            <div className="led-panel__calibration-bar">
              <div style={{ display: 'flex', alignItems: 'center', gap: 12, width: '100%' }}>
                <span className="led-panel__calibration-text">
                  Port {panel.wizard.currentPort} of {panel.wizard.totalPorts}
                </span>
                <div className="led-panel__calibration-progress" style={{ flex: 1 }}>
                  <div
                    className="led-panel__calibration-fill"
                    style={{ width: `${panel.wizard.progressPercent}%` }}
                  />
                </div>
                <span className="led-panel__calibration-text" style={{ fontSize: 11, opacity: 0.7, whiteSpace: 'nowrap' }}>
                  {panel.wizard.mappedCount} mapped · {panel.wizard.skippedCount} skipped
                </span>
              </div>
            </div>
          )}

          {/* ─── ButtonVisualizer (always visible) ─────────── */}
          <ButtonVisualizer
            playerCount={playerCount}
            buttonColors={editorColors}
            mode={panel.mode}
            blinkingButton={null}
            onButtonClick={panel.handleButtonClick}
          />

          {/* ─── ColorPalette (visible in design mode) ────── */}
          {panel.mode === 'design' && (
            <ColorPalette
              colors={panel.design.PALETTE_COLORS}
              selectedColor={panel.design.selectedColor}
              onColorSelect={panel.design.setSelectedColor}
              onFillAll={() => panel.design.fillAll(playerCount)}
              onClearAll={panel.design.clearAll}
              onSaveProfile={panel.design.saveProfile}
              onLoadProfile={panel.design.loadProfile}
              onDeleteProfile={panel.design.deleteProfile}
              profileNames={panel.design.profileNames}
              activeProfileName={panel.design.activeProfileName}
              hasChanges={panel.design.hasChanges}
            />
          )}

          {/* ─── Tab Bar ──────────────────────────────────── */}
          <div className="led-panel__tab-bar">
            {TABS.map(tab => (
              <button
                key={tab.id}
                className={`led-panel__tab ${activeTab === tab.id ? 'led-panel__tab--active' : ''}`}
                onClick={() => setActiveTab(tab.id)}
              >
                {tab.label}
              </button>
            ))}
            <button
              className={`led-panel__chat-toggle${chatOpen ? ' led-panel__chat-toggle--open' : ''}`}
              onClick={() => setChatOpen(prev => !prev)}
              aria-label={chatOpen ? 'Close Blinky chat' : 'Open Blinky chat'}
            >
              💬 {chatOpen ? 'Close' : 'Chat'}
            </button>
          </div>

          {/* ─── Tab Content ──────────────────────────────── */}
          <div className="led-panel__tab-content">

            {/* Game Profiles Tab */}
            {activeTab === 'profiles' && (
              <GameProfilesTab
                ArcadePanelPreview={ArcadePanelPreview}
                mappingForm={mappingForm}
                currentActiveButtons={currentButtons}
                cabinetPlayerCount={playerCount}
                wizardState={wizardBridgeState}
                toggleLED={toggleLED}
                handleWizardMapButton={handleWizardMapButton}
                gameSearchTerm={gameBindings.gameSearchTerm}
                setGameSearchTerm={gameBindings.setGameSearchTerm}
                handleGameSearchKeyDown={gameBindings.handleGameSearchKeyDown}
                handleSearchGames={gameBindings.handleSearchGames}
                isLoadingGames={gameBindings.isLoadingGames}
                loadGameResults={gameBindings.loadGameResults}
                gameResults={gameBindings.gameResults}
                selectedGame={gameBindings.selectedGame}
                handleSelectGame={gameBindings.handleSelectGame}
                selectedGameBinding={gameBindings.selectedGameBinding}
                selectedGameProfileName={gameBindings.selectedGameProfileName}
                setSelectedGameProfileName={gameBindings.setSelectedGameProfileName}
                isLoadingBinding={gameBindings.isLoadingBinding}
                availableProfiles={visibleProfiles}
                canPreviewBinding={gameBindings.canPreviewBinding}
                canApplyBinding={gameBindings.canApplyBinding}
                canClearBinding={gameBindings.canClearBinding}
                isPreviewingBinding={gameBindings.isPreviewingBinding}
                isApplyingBinding={gameBindings.isApplyingBinding}
                isClearingBinding={gameBindings.isClearingBinding}
                handlePreviewGameProfile={gameBindings.handlePreviewGameProfile}
                handleApplyGameProfile={gameBindings.handleApplyGameProfile}
                handleClearGameProfile={gameBindings.handleClearGameProfile}
                bindingPreview={gameBindings.bindingPreview}
                profileSearchTerm={profileSearchTerm}
                setProfileSearchTerm={setProfileSearchTerm}
                filteredProfiles={filteredProfiles}
                isLoadingProfiles={isLoadingProfiles}
                refreshProfiles={loadProfiles}
                selectedProfile={selectedProfileMeta}
                canApplyLibraryProfile={canApplyLibraryProfile}
                previewProfileFromLibrary={previewProfileFromLibrary}
                applyProfileFromLibrary={applyProfileFromLibrary}
                editProfileInDesigner={editProfileInDesigner}
                libraryPreviewReady={libraryPreviewReady}
                profilePreview={profilePreview}
                selectedProfileDisplayName={selectedProfileDisplayName}
              />
            )}

            {/* Real-time Control Tab */}
            {activeTab === 'realtime' && (
              <RealtimeControlTab
                connectedDevices={connection.connectedDevices}
                simulationMode={connection.simulationMode}
                connectionStatus={connection.connectionStatus}
                channelState={channelState}
                demoLastError={demoLastError}
                setDemoLastError={setDemoLastError}
                refreshHardwareStatus={connection.refreshHardwareStatus}
                isRefreshingStatus={connection.isRefreshingStatus}
                demoTestDuration={demoTestDuration}
                setDemoTestDuration={setDemoTestDuration}
                isTestingAllLEDs={isTestingAllLEDs}
                setIsTestingAllLEDs={setIsTestingAllLEDs}
                testAllLEDs={testAllLEDs}
                showToast={showToast}
                demoFlashPlayer={demoFlashPlayer}
                setDemoFlashPlayer={setDemoFlashPlayer}
                demoFlashButton={demoFlashButton}
                setDemoFlashButton={setDemoFlashButton}
                demoFlashColor={demoFlashColor}
                setDemoFlashColor={setDemoFlashColor}
                isFlashingDemo={isFlashingDemo}
                setIsFlashingDemo={setIsFlashingDemo}
                flashLEDCalibration={flashLEDCalibration}
                calibrationToken={panel.calibration.calibrationToken}
                testLED={testLED}
                mappingForm={mappingForm}
                setMappingForm={setMappingForm}
                buildButtonsFromForm={buildButtonsFromForm}
                applyLEDProfile={applyLEDProfile}
                selectedGame={gameBindings.selectedGame}
                selectedProfile={selectedStoredProfile}
                selectedGameProfileName={gameBindings.selectedGameProfileName}
                selectedProfileMeta={selectedProfileMeta}
                availableProfiles={storedProfiles}
                setAvailableProfiles={setStoredProfiles}
                listLEDProfiles={listLEDProfiles}
                applyGameProfileBinding={applyGameProfileBinding}
                buildFormFromButtons={buildFormFromButtons}
                getLEDProfile={getLEDProfile}
              />
            )}

            {/* Hardware Tab */}
            {activeTab === 'hardware' && (
              <HardwareTab
                connectionStatus={connection.connectionStatus}
                toggleWebSocketConnection={connection.toggleWebSocketConnection}
                isRefreshingStatus={connection.isRefreshingStatus}
                gatewaySocketUrl={connection.gatewaySocketUrl}
                hardwareStatus={connection.hardwareStatus}
                refreshHardwareStatus={connection.refreshHardwareStatus}
                connectionLog={connection.connectionLog}
                engineDiagnostics={connection.engineDiagnostics}
                simulationMode={connection.simulationMode}
                queueDepth={connection.queueDepth}
                pendingCommands={connection.pendingCommands}
                wsConnectionCount={connection.wsConnectionCount}
                activePatternName={connection.activePatternName}
                registryMessage={connection.registryMessage}
                engineEvents={connection.engineEvents}
                formatTimestampValue={formatTimestampValue}
                connectedDevices={connection.connectedDevices}
                registryDevices={connection.registryDevices}
                channelTestDevice={channelTestDevice}
                setChannelTestDevice={setChannelTestDevice}
                channelTestChannel={channelTestChannel}
                setChannelTestChannel={setChannelTestChannel}
                handleChannelTest={handleChannelTest}
                isTestingChannel={isTestingChannel}
                channelTestResult={channelTestResult}
                triggerHardwareTest={triggerHardwareTest}
              />
            )}

            {/* LED Layout Tab */}
            {activeTab === 'layout' && (
              <LEDLayoutTab
                channelState={channelState}
                isLoadingChannels={isLoadingChannels}
                channelEntries={channelEntries}
                calibrationToken={panel.calibration.calibrationToken}
                isStartingCalibration={panel.calibration.isStartingCalibration}
                isFlashingChannel={panel.calibration.isFlashingChannel}
                isStoppingCalibration={panel.calibration.isStoppingCalibration}
                startCalibrationSession={panel.calibration.startCalibrationSession}
                flashSelectedChannel={panel.calibration.flashSelectedChannel}
                stopCalibrationSession={panel.calibration.stopCalibrationSession}
                channelSelection={channelSelection}
                channelOptions={channelOptions}
                handleSelectChannel={handleSelectChannel}
                handleChannelFieldChange={handleChannelFieldChange}
                isChannelPreviewing={isChannelPreviewing}
                isChannelApplying={isChannelApplying}
                isDeletingChannel={isDeletingChannel}
                previewChannelUpdate={previewChannelUpdate}
                applyChannelUpdate={applyChannelUpdate}
                removeChannelMapping={removeChannelMapping}
                channelPreview={channelPreview}
              />
            )}

            {/* Calibration Tab */}
            {activeTab === 'calibration' && (
              <CalibrationTab
                WiringWizard={WiringWizardBridge}
                wizardState={wizardBridgeState}
                setWizardState={() => {}}
                cabinetPlayerCount={playerCount}
                handleWizardMapButton={handleWizardMapButton}
                showToast={showToast}
                channelState={channelState}
                ArcadePanelPreview={ArcadePanelPreview}
                mappingForm={mappingForm}
                currentActiveButtons={currentButtons}
                toggleLED={toggleLED}
              />
            )}

            {/* Design Tab (inline) */}
            {activeTab === 'design' && (
              <div style={{ padding: '24px', display: 'flex', flexDirection: 'column', gap: '20px' }}>
                {/* Design mode instructions */}
                <div style={{ padding: '20px', background: '#0f0f0f', borderRadius: '12px', border: '1px solid #10b98140' }}>
                  <div style={{ fontSize: '16px', fontWeight: '700', color: '#10b981', marginBottom: '12px', display: 'flex', alignItems: 'center', gap: '8px' }}>
                    <span>🖌️</span><span>Design Mode</span>
                  </div>
                  <p style={{ color: '#9ca3af', fontSize: '13px', margin: '0 0 12px 0', lineHeight: 1.6 }}>
                    {panel.mode === 'design'
                      ? 'Design mode is active. Click any button on the panel above to paint it with the selected color from the palette.'
                      : 'Enter design mode to paint individual button colors. Click "Design" in the controls bar above or button below.'}
                  </p>
                  {panel.mode !== 'design' && (
                    <button className="led-panel__preset-btn led-panel__preset-btn--active" onClick={panel.toggleDesign}>
                      Enter Design Mode
                    </button>
                  )}
                </div>

                {/* Profile Preview & Apply */}
                <div style={{ padding: '20px', background: '#0f0f0f', borderRadius: '12px', border: '1px solid #7c3aed' }}>
                  <div style={{ fontSize: '16px', fontWeight: '700', color: '#9333ea', marginBottom: '16px', display: 'flex', alignItems: 'center', gap: '8px' }}>
                    <span>💾</span><span>Profile Preview & Apply</span>
                  </div>
                  <p style={{ color: '#9ca3af', fontSize: '13px', margin: '0 0 16px 0' }}>
                    Stored profiles come from the backend profile directory. Design-mode drafts remain browser-local unless you preview and apply them here.
                  </p>
                  <div style={{ display: 'flex', flexDirection: 'column', gap: '12px' }}>
                    <div>
                      <label style={{ color: '#9ca3af', fontSize: '12px', fontWeight: '600', display: 'block', marginBottom: '6px' }}>Stored profile</label>
                      <div style={{ display: 'flex', gap: '8px', flexWrap: 'wrap' }}>
                        <select
                          className="led-panel__select"
                          value={selectedStoredProfile}
                          onChange={(event) => setSelectedStoredProfile(event.target.value)}
                          style={{ flex: 1, minWidth: '180px' }}
                        >
                          <option value="">Select a stored profile</option>
                          {visibleProfiles.map((profile) => (
                            <option key={profile.value} value={profile.value}>{profile.label}</option>
                          ))}
                        </select>
                        <button className="led-panel__preset-btn" onClick={loadProfiles} disabled={isLoadingProfiles}>
                          {isLoadingProfiles ? 'Loading...' : 'Reload'}
                        </button>
                        <button className="led-panel__preset-btn" onClick={loadStoredProfile} disabled={!selectedStoredProfile}>
                          Load to Designer
                        </button>
                      </div>
                    </div>
                    <div>
                      <label style={{ color: '#9ca3af', fontSize: '12px', fontWeight: '600', display: 'block', marginBottom: '6px' }}>Current profile name</label>
                      <input
                        className="led-panel__ops-input"
                        value={profileName}
                        onChange={(event) => setProfileName(event.target.value)}
                        placeholder="operator-layout"
                        style={{ width: '100%', background: '#111827', border: '1px solid #374151', borderRadius: '8px', color: '#e5e7eb', fontSize: '13px', padding: '8px 12px', outline: 'none' }}
                      />
                    </div>
                  </div>
                  <div style={{ display: 'flex', gap: '8px', marginTop: '16px' }}>
                    <button className="led-panel__preset-btn" onClick={previewCurrent} disabled={isPreviewing}>
                      {isPreviewing ? 'Previewing...' : 'Preview Current Layout'}
                    </button>
                    <button
                      className="led-panel__preset-btn led-panel__preset-btn--active"
                      onClick={applyCurrent}
                      disabled={isApplying || !profilePreview || currentProfileSummary.missingButtons.length > 0}
                    >
                      {isApplying ? 'Applying...' : 'Apply and Save'}
                    </button>
                  </div>

                  {/* Preview Diff */}
                  {profilePreview ? (
                    <div style={{ marginTop: '16px', padding: '14px', background: '#0a0b14', borderRadius: '10px', border: '1px solid #1f2937' }}>
                      <div style={{ display: 'flex', flexWrap: 'wrap', gap: '12px', fontSize: '12px', color: '#9ca3af', marginBottom: '8px' }}>
                        <span>Target: {currentProfileSummary.targetFile}</span>
                        <span>Resolved channels: {currentProfileSummary.totalChannels}</span>
                        <span>{currentProfileSummary.hasChanges ? 'Changes detected' : 'No diff'}</span>
                      </div>
                      <div style={{ fontSize: '12px', color: currentProfileSummary.missingButtons.length > 0 ? '#f59e0b' : '#6ee7b7', marginBottom: '8px' }}>
                        {currentProfileSummary.missingButtons.length > 0
                          ? `Missing hardware mappings: ${currentProfileSummary.missingButtons.join(', ')}`
                          : 'All logical buttons in this preview resolve to a hardware channel.'}
                      </div>
                      {backupPath && <div style={{ fontSize: '12px', color: '#9ca3af' }}>Backup created: {backupPath}</div>}
                      <pre style={{ margin: '8px 0 0', padding: '10px', background: '#000', borderRadius: '6px', color: '#d1d5db', fontSize: '11px', overflow: 'auto', maxHeight: '200px', whiteSpace: 'pre-wrap' }}>
                        {currentProfileSummary.diff}
                      </pre>
                    </div>
                  ) : (
                    <div style={{ marginTop: '16px', padding: '14px', background: '#0a0b14', borderRadius: '10px', border: '1px solid #1f2937', color: '#6b7280', fontSize: '13px' }}>
                      Preview the current layout to see the exact file target, diff, and missing wiring before applying it.
                    </div>
                  )}
                </div>
              </div>
            )}

          </div>

          {/* ─── Chat Drawer Overlay ─────────────────────── */}
          <div
            className={`blinky-sidebar-backdrop${chatOpen ? ' blinky-sidebar-backdrop--visible' : ''}`}
            onClick={() => setChatOpen(false)}
          />
          <div className={`blinky-drawer${chatOpen ? ' blinky-drawer--open' : ''}`}>
            <button
              className="blinky-drawer__close"
              onClick={() => setChatOpen(false)}
              aria-label="Close Blinky chat"
            >
              ✕
            </button>
            <EngineeringBaySidebar persona={BLINKY_PERSONA} />
          </div>

    </div>
  )
}

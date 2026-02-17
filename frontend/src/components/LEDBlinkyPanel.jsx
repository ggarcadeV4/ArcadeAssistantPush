import React, { useState, useEffect, useRef, useCallback, useMemo } from 'react'
import ChatBox from '../panels/led-blinky/ChatBox.jsx'
import { useNavigate } from 'react-router-dom'
import { speakAsBlinky, stopSpeaking } from '../services/ttsClient'
import { useBlinkyChat } from '../panels/led-blinky/useBlinkyChat'
import { executeLEDCommands } from '../panels/led-blinky/commandExecutor'
import ArcadePanelPreview from './led-blinky/ArcadePanelPreview'
import './led-blinky/ArcadePanelPreview.css'
import { useLEDLearnWizard } from '../hooks/useLEDLearnWizard'
import { useLEDCalibrationWizard } from '../hooks/useLEDCalibrationWizard'
import WiringWizard from './WiringWizard'

import {
  testLED,
  testAllLEDs,
  listLEDProfiles,
  getLEDProfile,
  previewLEDProfile,
  applyLEDProfile,
  getLEDStatus,
  refreshLEDHardware,
  closeLEDConnection,
  buildGatewayWebSocketUrl,
  runLEDPattern,
  setLEDBrightness,
  searchLaunchBoxGames,
  fetchGameProfile,
  fetchAllGameProfiles,
  previewGameProfileBinding,
  applyGameProfileBinding,
  deleteGameProfileBinding,
  listLEDChannelMappings,
  previewLEDChannels,
  applyLEDChannels,
  deleteLEDChannelMapping,
  startLEDCalibration,
  assignLEDCalibration,
  flashLEDCalibration,
  stopLEDCalibration,
  getLEDEngineHealth,
  runLEDChannelTest
} from '../services/ledBlinkyClient'

// WebSocket Manager Class - Moved outside component to prevent recreation
class LEDWebSocketManager {
  constructor() {
    this.ws = null
    this.url = ''
    this.reconnectAttempts = 0
    this.maxReconnectAttempts = 5
    this.reconnectDelay = 2000
    this.isConnecting = false
    this.connectionLog = []
    this.autoReconnectEnabled = false
    this.setConnectionStatus = null
    this.setConnectionLog = null
    this.showToast = null
    this.refreshStatus = null
    this.gatewayConnectionId = null
  }

  // Initialize callbacks from component
  init(setConnectionStatus, setConnectionLog, showToast, refreshStatus) {
    this.setConnectionStatus = setConnectionStatus
    this.setConnectionLog = setConnectionLog
    this.showToast = showToast
    this.refreshStatus = refreshStatus
  }

  async syncStatus() {
    if (typeof this.refreshStatus === 'function') {
      try {
        await this.refreshStatus()
      } catch (err) {
        console.warn('LED status refresh failed', err?.message || err)
      }
    }
  }

  connect(url) {
    if (!url) {
      this.log('Gateway WebSocket URL is missing', 'error')
      this.showToast?.('Gateway WebSocket unavailable', 'error')
      this.setConnectionStatus?.('error')
      return
    }

    if (this.isConnecting) {
      this.log('Connection already in progress...', 'warning')
      return
    }

    this.url = url
    this.gatewayConnectionId = null
    this.isConnecting = true
    this.log(`Attempting to connect to ${url}...`, 'info')
    this.setConnectionStatus?.('connecting')

    try {
      this.ws = new WebSocket(url)

      this.ws.onopen = () => {
        this.isConnecting = false
        this.reconnectAttempts = 0
        this.log('WebSocket connected successfully!', 'success')
        this.setConnectionStatus?.('connected')
        this.showToast?.('Hardware connected via WebSocket', 'websocket')
        this.syncStatus()

        this.send({
          type: 'handshake',
          client: 'led-blinky-panel',
          version: '2.0.0'
        })
      }

      this.ws.onmessage = (event) => {
        try {
          const data = JSON.parse(event.data)
          this.handleMessage(data)
        } catch (error) {
          this.log(`Invalid message received: ${event.data}`, 'error')
        }
      }

      this.ws.onclose = (event) => {
        this.isConnecting = false
        this.log(`Connection closed (Code: ${event.code})`, 'error')
        this.setConnectionStatus?.('disconnected')
        this.gatewayConnectionId = null
        this.syncStatus()

        // Only auto-reconnect if enabled and not a manual disconnect
        if (this.autoReconnectEnabled && event.code !== 1000 && this.reconnectAttempts < this.maxReconnectAttempts) {
          this.scheduleReconnect()
        }
      }

      this.ws.onerror = (error) => {
        this.isConnecting = false
        this.log('WebSocket error occurred', 'error')
        this.setConnectionStatus?.('error')
        this.syncStatus()
      }

      setTimeout(() => {
        if (this.isConnecting) {
          this.ws.close()
          this.log('Connection timeout', 'error')
          this.setConnectionStatus?.('disconnected')
        }
      }, 10000)

    } catch (error) {
      this.isConnecting = false
      this.log(`Failed to create WebSocket: ${error.message}`, 'error')
      this.setConnectionStatus?.('error')
    }
  }

  disconnect() {
    if (this.gatewayConnectionId) {
      closeLEDConnection(this.gatewayConnectionId).catch(() => {
        this.log('Failed to notify gateway about disconnect', 'warning')
      })
    }
    this.gatewayConnectionId = null
    if (this.ws) {
      this.ws.close(1000, 'User disconnected')
      this.ws = null
    }
    this.log('Disconnected by user', 'info')
    this.setConnectionStatus?.('disconnected')
    this.syncStatus()
  }

  send(data) {
    if (this.ws && this.ws.readyState === WebSocket.OPEN) {
      this.ws.send(JSON.stringify(data))
      return true
    } else {
      this.log('Cannot send data: WebSocket not connected', 'warning')
      return false
    }
  }

  handleMessage(data) {
    this.log(`Received: ${data.type}`, 'info')

    switch (data.type) {
      case 'handshake_response':
        this.log(`Server: ${data.server} v${data.version}`, 'success')
        break
      case 'led_state':
        // Will be handled by component callback
        break
      case 'pattern_complete':
        this.log(`Pattern '${data.pattern}' completed`, 'info')
        break
      case 'error':
        this.log(`Server error: ${data.message}`, 'error')
        this.showToast?.(`Hardware error: ${data.message}`, 'error')
        break
      case 'gateway_status':
        this.gatewayConnectionId = data.connectionId || null
        this.log(`Gateway bridge ready (${data.mode || 'proxy'})`, 'success')
        break
      case 'gateway_notice':
        this.log(`Gateway notice: ${data.status || data.message}`, data.status === 'mock_mode' ? 'warning' : 'info')
        break
      case 'gateway_error':
        this.log(`Gateway error: ${data.message}`, 'error')
        this.showToast?.(`Gateway error: ${data.message}`, 'error')
        break
      case 'mock_ack':
        this.log(`Gateway ack (${data.received_bytes ?? 0} bytes)`, 'info')
        break
      default:
        this.log(`Unknown message type: ${data.type}`, 'warning')
    }
  }

  log(message, type = 'info') {
    const timestamp = new Date().toLocaleTimeString()
    const logEntry = { timestamp, message, type }
    this.setConnectionLog?.(prev => [...prev.slice(-49), logEntry])
  }

  sendLEDCommand(player, button, state, color = null) {
    const command = {
      type: 'led_command',
      player: parseInt(player),
      button: button,
      state: state,
      timestamp: Date.now()
    }

    if (color) {
      command.color = color
    }

    if (this.send(command)) {
      this.log(`LED P${player}-${button}: ${state ? 'ON' : 'OFF'}`, 'info')
    }
  }

  sendPattern(patternName, params = {}) {
    const command = {
      type: 'pattern',
      pattern: patternName,
      params: params,
      timestamp: Date.now()
    }

    if (this.send(command)) {
      this.log(`Pattern sent: ${patternName}`, 'info')
    }
  }

  scheduleReconnect() {
    this.reconnectAttempts++
    const delay = Math.min(this.reconnectDelay * Math.pow(2, this.reconnectAttempts - 1), 30000) // Exponential backoff, max 30s
    this.log(`Auto-reconnecting in ${delay / 1000}s (Attempt ${this.reconnectAttempts}/${this.maxReconnectAttempts})`, 'warning')

    setTimeout(() => {
      if (this.reconnectAttempts <= this.maxReconnectAttempts) {
        this.log('Auto-reconnect attempt...', 'info')
        this.connect(this.url)
      } else {
        this.log('Auto-reconnect failed: Maximum attempts reached', 'error')
        this.showToast?.('Connection failed: Auto-reconnect exhausted', 'error')
      }
    }, delay)
  }

  enableAutoReconnect() {
    this.autoReconnectEnabled = true
    this.log('Auto-reconnect enabled', 'info')
  }

  disableAutoReconnect() {
    this.autoReconnectEnabled = false
    this.reconnectAttempts = 0
    this.log('Auto-reconnect disabled', 'info')
  }
}

const DEFAULT_MAPPING_FORM = Object.freeze({
  p1_button1: '#FF0000',
  p1_button2: '#00FF00',
  p1_button3: '#0000FF',
  p1_button4: '#FFFF00',
  p2_button1: '#FF00FF',
  p2_button2: '#00FFFF',
  p2_button3: '#FF8800',
  p2_button4: '#8800FF'
})

const PLAYER_KEYS = ['player1', 'player2', 'player3', 'player4']
const FORM_KEY_REGEX = /^p(\d+)_button(\d+)$/i
const LOGICAL_KEY_REGEX = /^p(\d+)\.(button\d+)$/i

const normalizeButtonValue = (value) => {
  if (value && typeof value === 'object' && !Array.isArray(value)) {
    return { ...value }
  }
  if (typeof value === 'string' && value.trim()) {
    return { color: value.trim() }
  }
  if (value === null || value === undefined) {
    return {}
  }
  return { color: String(value) }
}

const extractButtonsFromPayload = (payload = {}) => {
  const buttons = {}
  const register = (key, value) => {
    if (!key) return
    const normalizedKey = key.trim()
    if (!normalizedKey) return
    buttons[normalizedKey] = normalizeButtonValue(value)
  }

  if (payload.buttons && typeof payload.buttons === 'object') {
    Object.entries(payload.buttons).forEach(([logicalKey, value]) => register(logicalKey, value))
  }

  PLAYER_KEYS.forEach((playerKey, playerIndex) => {
    const playerSection = payload[playerKey]
    if (playerSection && typeof playerSection === 'object') {
      Object.entries(playerSection).forEach(([buttonKey, value]) => {
        register(`p${playerIndex + 1}.${buttonKey}`, value)
      })
    }
  })

  Object.entries(payload).forEach(([key, value]) => {
    if (LOGICAL_KEY_REGEX.test(key)) {
      register(key, value)
    }
  })

  return buttons
}

const buildFormFromButtons = (buttons = {}) => {
  const form = { ...DEFAULT_MAPPING_FORM }
  Object.entries(buttons).forEach(([logicalKey, value]) => {
    const match = logicalKey.match(LOGICAL_KEY_REGEX)
    if (!match) return
    const [, player, buttonKey] = match
    const formKey = `p${player}_${buttonKey.toLowerCase()}`
    const color = typeof value === 'string' ? value : value?.color
    if (form[formKey] && color) {
      form[formKey] = color
    }
  })
  return form
}

const buildButtonsFromForm = (form = {}) => {
  const buttons = {}
  Object.entries(form).forEach(([formKey, color]) => {
    const match = formKey.match(FORM_KEY_REGEX)
    if (!match) return
    const [, player, buttonIndex] = match
    buttons[`p${player}.button${buttonIndex}`] = { color }
  })
  return buttons
}

const ComingSoonTag = ({ text = 'Coming soon' }) => (
  <span
    style={{
      display: 'inline-flex',
      alignItems: 'center',
      justifyContent: 'center',
      padding: '2px 8px',
      borderRadius: '999px',
      border: '1px solid #9333ea',
      background: '#0a0a0a',
      color: '#d1d5db',
      fontSize: '10px',
      textTransform: 'uppercase',
      letterSpacing: '0.5px'
    }}
  >
    {text}
  </span>
)

const LEDBlinkyPanel = () => {
  const navigate = useNavigate()

  // Toast helper — must be declared before any hooks that reference it
  const showToast = useCallback((message, type = 'success') => {
    console.log(`Toast [${type}]: ${message}`)
  }, [])

  // Initialize Blinky chat hook for voice-guided calibration
  const blinkyChat = useBlinkyChat()

  // LED Learn Wizard hook for button-to-LED channel mapping
  const ledWizard = useLEDLearnWizard({ onToast: (msg, type) => showToast(msg, type) })

  // LED Calibration Wizard hook for 4-player port-to-button mapping
  const calibrationWizard = useLEDCalibrationWizard({ onToast: (msg, type) => showToast(msg, type) })

  const [currentActiveButtons, setCurrentActiveButtons] = useState(new Set())
  const [customButtonColors, setCustomButtonColors] = useState(new Map())
  const [connectionStatus, setConnectionStatus] = useState('disconnected')
  const [chatOpen, setChatOpen] = useState(false)
  const [chatMessages, setChatMessages] = useState(() => {
    // Don't show default greeting if coming from Dewey handoff
    const urlParams = new URLSearchParams(window.location.search)
    const hasHandoff = urlParams.get('context')
    if (hasHandoff) return []
    return [
      {
        type: 'ai',
        message: "Hello! I'm your LED panel assistant. I can help you configure LED layouts, create animations, troubleshoot hardware connections, and answer questions about your arcade setup. What would you like to work on today?"
      }
    ]
  })
  const [chatInput, setChatInput] = useState('')
  const [activeMode, setActiveMode] = useState('profiles')
  const defaultWebsocketUrl = buildGatewayWebSocketUrl('/api/local/led/ws')
  const [gatewaySocketUrl, setGatewaySocketUrl] = useState(defaultWebsocketUrl)
  const [connectionLog, setConnectionLog] = useState([])
  const [hardwareStatus, setHardwareStatus] = useState(null)
  const [isRefreshingStatus, setIsRefreshingStatus] = useState(false)
  const [channelState, setChannelState] = useState({
    channels: {},
    unmapped: [],
    unknown_logical: [],
    total_channels: 0,
    target_file: ''
  })
  const [isLoadingChannels, setIsLoadingChannels] = useState(false)
  const [channelSelection, setChannelSelection] = useState({
    logicalButton: '',
    deviceId: '',
    channel: ''
  })
  const [channelPreview, setChannelPreview] = useState(null)
  const [isChannelPreviewing, setIsChannelPreviewing] = useState(false)
  const [isChannelApplying, setIsChannelApplying] = useState(false)
  const [isDeletingChannel, setIsDeletingChannel] = useState(false)
  const [calibrationToken, setCalibrationToken] = useState(null)
  const [isStartingCalibration, setIsStartingCalibration] = useState(false)
  const [isStoppingCalibration, setIsStoppingCalibration] = useState(false)
  const [isFlashingChannel, setIsFlashingChannel] = useState(false)
  const [isVoiceRecording, setIsVoiceRecording] = useState(false)
  const [ledBrightness, setLedBrightness] = useState(85)
  const [engineHealth, setEngineHealth] = useState(null)
  const [channelTestDevice, setChannelTestDevice] = useState('')
  const [channelTestChannel, setChannelTestChannel] = useState('0')
  const [isTestingChannel, setIsTestingChannel] = useState(false)
  const [channelTestResult, setChannelTestResult] = useState(null)

  // Camera Demo Controls State
  const [demoTestDuration, setDemoTestDuration] = useState(2000)
  const [isTestingAllLEDs, setIsTestingAllLEDs] = useState(false)
  const [demoFlashPlayer, setDemoFlashPlayer] = useState('1')
  const [demoFlashButton, setDemoFlashButton] = useState('1')
  const [demoFlashColor, setDemoFlashColor] = useState('#00FF00')
  const [isFlashingDemo, setIsFlashingDemo] = useState(false)
  const [demoColorPickerControl, setDemoColorPickerControl] = useState(null) // { player, button }
  const [demoLastError, setDemoLastError] = useState(null)

  // Cabinet configuration state - fetched from backend
  const [cabinetPlayerCount, setCabinetPlayerCount] = useState(2)  // Default to 2, fetched from /api/cabinet/config

  // Phase 6.5: Shared Wiring Wizard state (hoisted for ArcadePanelPreview access)
  const [wizardState, setWizardState] = useState({
    isActive: false,
    sessionId: null,
    currentPort: null,
    currentStep: 0,
    totalPorts: 0,
    mappedCount: 0,
    buttonToPortMap: {}
  })

  // Fetch cabinet config on mount (Phase 6: Dynamic Player Count)
  useEffect(() => {
    const fetchCabinetConfig = async () => {
      try {
        const res = await fetch('/api/cabinet/config')
        const data = await res.json()
        if (data.success && data.config?.num_players) {
          setCabinetPlayerCount(data.config.num_players)
          console.log('[LEDBlinkyPanel] Cabinet config loaded, num_players:', data.config.num_players)
        }
        // Check if wizard is active from backend
        if (data.led?.wizard_active) {
          setWizardState(prev => ({ ...prev, isActive: true }))
        }
      } catch (e) {
        console.warn('[LEDBlinkyPanel] Failed to fetch cabinet config:', e.message)
      }
    }
    fetchCabinetConfig()
  }, [])

  // Phase 6.5: Hoisted handleMapButton - shared between WiringWizard and ArcadePanelPreview
  const handleWizardMapButton = useCallback(async (buttonId) => {
    if (!wizardState.isActive) {
      console.log('[LEDBlinkyPanel] Wizard not active, skipping map')
      return { success: false, error: 'Wizard not active' }
    }

    console.log('[LEDBlinkyPanel] Mapping button:', buttonId)

    try {
      const res = await fetch('/api/cabinet/wizard/map', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ buttonId })
      })

      const data = await res.json()

      if (data.complete) {
        showToast(`All ports mapped! ${buttonId} was last.`, 'success')
        return { success: true, complete: true }
      }

      if (data.success) {
        showToast(`Mapped ${buttonId} to port ${data.port || wizardState.currentPort}`, 'success')
        // Trigger next blink
        await fetch('/api/cabinet/wizard/blink', { method: 'POST' })
      }

      return data

    } catch (e) {
      console.error('[LEDBlinkyPanel] Map failed:', e)
      showToast('Failed to map button: ' + e.message, 'error')
      return { success: false, error: e.message }
    }
  }, [wizardState.isActive, wizardState.currentPort, showToast])

  // LED Learn Wizard state
  const [ledLearnWizardActive, setLedLearnWizardActive] = useState(false)
  const [ledLearnWizardStep, setLedLearnWizardStep] = useState(0)
  const [ledLearnWizardProgress, setLedLearnWizardProgress] = useState([])
  const [trackballDevice, setTrackballDevice] = useState(null)
  const [clickToMapChannel, setClickToMapChannel] = useState(1)
  const [clickToMapTotal, setClickToMapTotal] = useState(32)

  // LED Mapping state
  const [mappingData, setMappingData] = useState(() =>
    JSON.stringify({ buttons: buildButtonsFromForm(DEFAULT_MAPPING_FORM) }, null, 2)
  )
  const [profilePreview, setProfilePreview] = useState(null)
  const [availableProfiles, setAvailableProfiles] = useState([])
  const [profileSearchTerm, setProfileSearchTerm] = useState('')
  const [selectedProfile, setSelectedProfile] = useState('')
  const [selectedProfileMeta, setSelectedProfileMeta] = useState(null)
  const [isLoadingProfiles, setIsLoadingProfiles] = useState(false)
  const [isApplyingMapping, setIsApplyingMapping] = useState(false)
  const [lastPreviewPayload, setLastPreviewPayload] = useState(null)
  const [lastPreviewProfileKey, setLastPreviewProfileKey] = useState(null)
  const [gameSearchTerm, setGameSearchTerm] = useState('')
  const [gameResults, setGameResults] = useState([])
  const [isLoadingGames, setIsLoadingGames] = useState(false)
  const [selectedGame, setSelectedGame] = useState(null)
  const [selectedGameBinding, setSelectedGameBinding] = useState(null)
  const [selectedGameProfileName, setSelectedGameProfileName] = useState('')
  const [gameBindingsIndex, setGameBindingsIndex] = useState({})
  const [bindingPreview, setBindingPreview] = useState(null)
  const [lastBindingPreviewKey, setLastBindingPreviewKey] = useState(null)
  const [isPreviewingBinding, setIsPreviewingBinding] = useState(false)
  const [isApplyingBinding, setIsApplyingBinding] = useState(false)
  const [isClearingBinding, setIsClearingBinding] = useState(false)
  const [isLoadingBinding, setIsLoadingBinding] = useState(false)

  // Parse mapping data for color pickers (default colors if no mapping)
  const [mappingForm, setMappingForm] = useState(() => ({ ...DEFAULT_MAPPING_FORM }))

  const wsManagerRef = useRef(null)
  const activeButtonsRef = useRef(currentActiveButtons)
  const brightnessDebounceRef = useRef(null)
  const gameSearchQueryRef = useRef('')
  const recognitionRef = useRef(null)
  const handoffProcessedRef = useRef(null)
  const channelOptions = useMemo(() => {
    const mappedKeys = Object.keys(channelState.channels || {})
    const extras = [
      ...(Array.isArray(channelState.unmapped) ? channelState.unmapped : []),
      ...(Array.isArray(channelState.unknown_logical) ? channelState.unknown_logical : [])
    ]
    const combined = Array.from(new Set([...mappedKeys, ...extras]))
    combined.sort()
    return combined
  }, [channelState])
  const channelEntries = useMemo(() => Object.entries(channelState.channels || {}), [channelState.channels])

  const runtimeStatus = hardwareStatus?.runtime || null

  const registryDevices = useMemo(() => {
    if (runtimeStatus?.registry && Array.isArray(runtimeStatus.registry.all_devices)) {
      return runtimeStatus.registry.all_devices
    }
    return []
  }, [runtimeStatus])

  useEffect(() => {
    if (!registryDevices.length) {
      return
    }
    if (!channelTestDevice || !registryDevices.some((device) => device.device_id === channelTestDevice)) {
      setChannelTestDevice(registryDevices[0].device_id)
    }
  }, [registryDevices, channelTestDevice])
  const engineDiagnostics = engineHealth || hardwareStatus?.engine || runtimeStatus?.engine || null
  const engineEvents = useMemo(() => {
    if (engineHealth && Array.isArray(engineHealth.events)) {
      return engineHealth.events
    }
    if (runtimeStatus && Array.isArray(runtimeStatus.events)) {
      return runtimeStatus.events
    }
    if (runtimeStatus && Array.isArray(runtimeStatus.log)) {
      return runtimeStatus.log
    }
    return []
  }, [engineHealth, runtimeStatus])
  const connectedDevices = useMemo(() => {
    if (runtimeStatus && Array.isArray(runtimeStatus.devices)) {
      return runtimeStatus.devices
    }
    return []
  }, [runtimeStatus])
  const simulationMode = Boolean(
    runtimeStatus?.registry?.simulation_mode ||
    (engineDiagnostics ? engineDiagnostics.simulation_mode : false)
  )
  const wsConnectionCount =
    typeof engineHealth?.ws_client_count === 'number'
      ? engineHealth.ws_client_count
      : typeof hardwareStatus?.connections === 'number'
        ? hardwareStatus.connections
        : 0
  const queueDepth = typeof engineHealth?.queue_depth === 'number' ? engineHealth.queue_depth : 0
  const pendingCommands =
    typeof engineHealth?.pending_commands === 'number' ? engineHealth.pending_commands : queueDepth
  const activePatternName = engineHealth?.active_pattern || engineDiagnostics?.active_pattern || null
  const registryMessage = runtimeStatus?.registry?.message

  // showToast is now declared at top of component (before hooks that depend on it)

  const formatTimestampValue = (value) => {
    if (!value) return 'Never'
    try {
      if (typeof value === 'number') {
        return new Date(value * 1000).toLocaleString()
      }
      const parsed = new Date(value)
      if (Number.isNaN(parsed.getTime())) {
        return 'Unknown'
      }
      return parsed.toLocaleString()
    } catch {
      return 'Unknown'
    }
  }

  const refreshHardwareStatus = useCallback(async () => {
    try {
      setIsRefreshingStatus(true)
      // First trigger a hardware rescan, then fetch updated status
      try {
        await refreshLEDHardware()
      } catch (refreshErr) {
        console.warn('Hardware refresh failed (continuing with status fetch)', refreshErr)
      }
      const status = await getLEDStatus()
      setHardwareStatus(status)
      if (Array.isArray(status?.log)) {
        setConnectionLog(status.log)
      }
      const wsPath = status?.ws?.url || '/api/local/led/ws'
      setGatewaySocketUrl(buildGatewayWebSocketUrl(wsPath))
      try {
        const health = await getLEDEngineHealth()
        setEngineHealth(health)
      } catch (healthErr) {
        console.warn('Failed to load LED engine health', healthErr)
        setEngineHealth(null)
      }
      return status
    } catch (err) {
      const message = err?.error || err?.message || 'Failed to load hardware status'
      showToast(message, 'error')
      return null
    } finally {
      setIsRefreshingStatus(false)
    }
  }, [showToast])

  const loadChannelMappings = useCallback(async () => {
    setIsLoadingChannels(true)
    try {
      const data = await listLEDChannelMappings()
      setChannelState(data)
      setChannelPreview(null)
      setChannelSelection((prev) => {
        const docChannels = data.channels || {}
        if (prev.logicalButton) {
          const entry = docChannels[prev.logicalButton]
          if (entry) {
            return {
              ...prev,
              deviceId: entry.device_id || '',
              channel: entry.channel ? String(entry.channel) : ''
            }
          }
        }
        const available = Object.keys(docChannels)
        const fallbackCandidates = [
          ...available,
          ...(Array.isArray(data.unmapped) ? data.unmapped : []),
          ...(Array.isArray(data.unknown_logical) ? data.unknown_logical : [])
        ].filter(Boolean)
        const fallback = fallbackCandidates[0] || ''
        if (!fallback) {
          return {
            logicalButton: '',
            deviceId: '',
            channel: ''
          }
        }
        const entry = docChannels[fallback]
        return {
          logicalButton: fallback,
          deviceId: entry?.device_id || '',
          channel: entry?.channel ? String(entry.channel) : ''
        }
      })
      return data
    } catch (err) {
      const message = err?.error || err?.message || 'Failed to load LED wiring'
      showToast(message, 'error')
      throw err
    } finally {
      setIsLoadingChannels(false)
    }
  }, [showToast])

  const handleSelectChannel = useCallback(
    (logicalButton) => {
      const mapping = channelState.channels?.[logicalButton]
      setChannelSelection({
        logicalButton,
        deviceId: mapping?.device_id || '',
        channel: mapping?.channel ? String(mapping.channel) : ''
      })
      setChannelPreview(null)
    },
    [channelState.channels]
  )

  const handleChannelFieldChange = useCallback((field, value) => {
    setChannelSelection((prev) => ({ ...prev, [field]: value }))
    setChannelPreview(null)
  }, [])

  const buildChannelUpdatePayload = useCallback(() => {
    const logicalButton = (channelSelection.logicalButton || '').trim()
    if (!logicalButton) {
      throw new Error('Select a logical button to calibrate.')
    }
    const deviceId = (channelSelection.deviceId || '').trim()
    if (!deviceId) {
      throw new Error('Device ID is required.')
    }
    const channelNumber = Number(channelSelection.channel)
    if (!Number.isFinite(channelNumber) || !Number.isInteger(channelNumber) || channelNumber < 1) {
      throw new Error('Channel must be a positive integer.')
    }
    return {
      updates: [
        {
          logical_button: logicalButton,
          device_id: deviceId,
          channel: channelNumber
        }
      ]
    }
  }, [channelSelection])

  const previewChannelUpdate = useCallback(async () => {
    let payload
    try {
      payload = buildChannelUpdatePayload()
    } catch (err) {
      showToast(err?.message || 'Invalid LED wiring payload', 'error')
      return
    }
    setIsChannelPreviewing(true)
    try {
      const preview = await previewLEDChannels(payload)
      setChannelPreview(preview)
      showToast('LED wiring preview ready', 'success')
    } catch (err) {
      const message = err?.error || err?.detail || err?.message || 'LED wiring preview failed'
      showToast(message, 'error')
    } finally {
      setIsChannelPreviewing(false)
    }
  }, [buildChannelUpdatePayload, showToast])

  const applyChannelUpdate = useCallback(async () => {
    let payload
    try {
      payload = buildChannelUpdatePayload()
    } catch (err) {
      showToast(err?.message || 'Invalid LED wiring payload', 'error')
      return
    }
    setIsChannelApplying(true)
    try {
      const result = await applyLEDChannels({ ...payload, dry_run: false })
      setChannelPreview(result.preview)
      try {
        await loadChannelMappings()
      } catch (refreshErr) {
        console.warn('LED channel reload failed', refreshErr)
      }
      const status = result.status === 'applied' ? 'success' : result.status === 'dry_run' ? 'info' : 'info'
      const message =
        result.status === 'applied'
          ? 'LED wiring updated with backup.'
          : result.status === 'dry_run'
            ? 'LED wiring dry-run completed.'
            : 'No LED wiring changes detected.'
      showToast(message, status)
    } catch (err) {
      const message = err?.error || err?.detail || err?.message || 'LED wiring apply failed'
      showToast(message, 'error')
    } finally {
      setIsChannelApplying(false)
    }
  }, [buildChannelUpdatePayload, loadChannelMappings, showToast])

  const startCalibrationSession = useCallback(async () => {
    setIsStartingCalibration(true)
    try {
      const data = await startLEDCalibration()
      setCalibrationToken(data.token)
      showToast('Calibration mode active', 'success')
      return data
    } catch (err) {
      const message = err?.error || err?.message || 'Failed to start calibration'
      showToast(message, 'error')
      throw err
    } finally {
      setIsStartingCalibration(false)
    }
  }, [showToast])

  const stopCalibrationSession = useCallback(
    async (tokenOverride) => {
      const token = tokenOverride || calibrationToken
      if (!token) {
        showToast('No calibration session to stop.', 'error')
        return null
      }
      setIsStoppingCalibration(true)
      try {
        const data = await stopLEDCalibration({ token })
        if (!tokenOverride) {
          setCalibrationToken(null)
        }
        showToast('Calibration mode ended', 'success')
        return data
      } catch (err) {
        const message = err?.error || err?.message || 'Failed to stop calibration'
        showToast(message, 'error')
        throw err
      } finally {
        setIsStoppingCalibration(false)
      }
    },
    [calibrationToken, showToast]
  )

  const flashCalibrationHelper = useCallback(
    async ({ token, logicalButton, deviceId, channel, durationMs, color } = {}) => {
      const activeToken = token || calibrationToken
      if (!activeToken) {
        throw new Error('Calibration token is required to flash LEDs.')
      }
      if (!logicalButton && (!deviceId || !channel)) {
        throw new Error('Provide logicalButton or both deviceId and channel.')
      }
      const payload = {
        token: activeToken,
        logical_button: logicalButton,
        device_id: deviceId,
        channel,
        duration_ms: durationMs,
        color
      }
      return await flashLEDCalibration(payload)
    },
    [calibrationToken]
  )

  const flashSelectedChannel = useCallback(async () => {
    if (!calibrationToken) {
      showToast('Start calibration before flashing a channel.', 'error')
      return
    }
    if (!channelSelection.logicalButton) {
      showToast('Select a logical button first.', 'error')
      return
    }
    setIsFlashingChannel(true)
    try {
      await flashCalibrationHelper({ logicalButton: channelSelection.logicalButton })
      showToast(`Flashing ${channelSelection.logicalButton}`, 'success')
    } catch (err) {
      const message = err?.error || err?.detail || err?.message || 'Failed to flash LED'
      showToast(message, 'error')
    } finally {
      setIsFlashingChannel(false)
    }
  }, [calibrationToken, channelSelection.logicalButton, flashCalibrationHelper, showToast])

  const assignCalibrationMapping = useCallback(
    async ({ token, logicalButton, deviceId, channel, dryRun } = {}) => {
      const activeToken = token || calibrationToken
      if (!activeToken) {
        throw new Error('Calibration token is required to assign wiring.')
      }
      if (!logicalButton || !deviceId || !channel) {
        throw new Error('logicalButton, deviceId, and channel are required.')
      }
      const payload = {
        token: activeToken,
        logical_button: logicalButton,
        device_id: deviceId,
        channel,
        dry_run: dryRun
      }
      const result = await assignLEDCalibration(payload)
      await loadChannelMappings()
      return result
    },
    [calibrationToken, loadChannelMappings]
  )

  useEffect(() => {
    const helpers = {
      startCalibration: () => startCalibrationSession(),
      assignCalibration: (params) => assignCalibrationMapping(params),
      flashCalibration: (params) => flashCalibrationHelper(params),
      stopCalibration: (token) => stopCalibrationSession(token),
      fetchChannels: () => loadChannelMappings()
    }
    window.AA_LED_CALIBRATION = helpers
    return () => {
      if (window.AA_LED_CALIBRATION === helpers) {
        delete window.AA_LED_CALIBRATION
      }
    }
  }, [
    assignCalibrationMapping,
    flashCalibrationHelper,
    loadChannelMappings,
    startCalibrationSession,
    stopCalibrationSession
  ])

  const removeChannelMapping = useCallback(async () => {
    const logicalButton = channelSelection.logicalButton
    if (!logicalButton) {
      showToast('Select a logical button to delete.', 'error')
      return
    }
    setIsDeletingChannel(true)
    try {
      await deleteLEDChannelMapping(logicalButton, { dryRun: false })
      await loadChannelMappings()
      showToast(`Removed wiring for ${logicalButton}`, 'success')
    } catch (err) {
      const message = err?.error || err?.detail || err?.message || 'Failed to delete channel'
      showToast(message, 'error')
    } finally {
      setIsDeletingChannel(false)
    }
  }, [channelSelection.logicalButton, loadChannelMappings, showToast])


  // Keep ref of currentActiveButtons in sync for stable callbacks
  useEffect(() => { activeButtonsRef.current = currentActiveButtons }, [currentActiveButtons])

  useEffect(() => {
    refreshHardwareStatus()
  }, [refreshHardwareStatus])

  useEffect(() => {
    if (activeMode === 'hardware') {
      refreshHardwareStatus()
    }
  }, [activeMode, refreshHardwareStatus])

  useEffect(() => {
    loadChannelMappings()
  }, [loadChannelMappings])

  useEffect(() => {
    if (activeMode === 'layout') {
      loadChannelMappings()
    }
  }, [activeMode, loadChannelMappings])

  useEffect(() => {
    setGameResults(prev =>
      prev.map(game => ({
        ...game,
        assigned_profile: gameBindingsIndex[game.id] || null
      }))
    )
  }, [gameBindingsIndex])

  useEffect(() => {
    return () => {
      if (brightnessDebounceRef.current) {
        clearTimeout(brightnessDebounceRef.current)
      }
    }
  }, [])

  // Sync mappingForm to mappingData (JSON string)
  useEffect(() => {
    if (Object.keys(mappingForm).length > 0) {
      const buttons = buildButtonsFromForm(mappingForm)
      setMappingData(JSON.stringify({ buttons }, null, 2))
    }
  }, [mappingForm])

  useEffect(() => {
    setProfilePreview(null)
    setLastPreviewPayload(null)
    setLastPreviewProfileKey(null)
  }, [mappingData])

  // Helper function to update individual button colors
  const setButtonColor = useCallback((key, value) => {
    setMappingForm(prev => ({ ...prev, [key]: value }))
  }, [])

  const loadAvailableProfiles = useCallback(async () => {
    setIsLoadingProfiles(true)
    try {
      const data = await listLEDProfiles()
      const profiles = Array.isArray(data?.profiles) ? data.profiles : []
      const normalizedProfiles = profiles.map(profile => {
        if (typeof profile === 'string') {
          return {
            value: profile,
            label: profile,
            metadata: { filename: profile }
          }
        }

        const value = profile.profile_name || profile.filename || profile.game || profile.scope || 'profile'
        const filename = profile.filename || `${value}.json`

        const labelParts = []
        if (profile.game) {
          labelParts.push(profile.game)
        } else if (filename) {
          labelParts.push(filename)
        } else {
          labelParts.push(value)
        }

        if (profile.scope) {
          const scopeLabel = profile.scope === 'default' ? 'Default' : profile.scope
          labelParts.push(scopeLabel)
        }

        if (Array.isArray(profile.mapping_keys) && profile.mapping_keys.length > 0) {
          labelParts.push(`${profile.mapping_keys.length} keys`)
        }

        return {
          value,
          label: labelParts.join(' • '),
          metadata: profile
        }
      })

      setAvailableProfiles(normalizedProfiles)
    } catch (err) {
      console.error('Failed to load LED profiles:', err)
      showToast('Failed to load LED profiles', 'error')
    } finally {
      setIsLoadingProfiles(false)
    }
  }, [showToast])

  const refreshProfiles = useCallback(() => {
    if (!isLoadingProfiles) {
      loadAvailableProfiles()
    }
  }, [isLoadingProfiles, loadAvailableProfiles])

  useEffect(() => {
    if ((activeMode === 'animation' || activeMode === 'profiles') && availableProfiles.length === 0 && !isLoadingProfiles) {
      loadAvailableProfiles()
    }
  }, [activeMode, availableProfiles.length, isLoadingProfiles, loadAvailableProfiles])

  const loadGameBindings = useCallback(async () => {
    try {
      const response = await fetchAllGameProfiles()
      const bindings = Array.isArray(response?.bindings) ? response.bindings : []
      const index = {}
      bindings.forEach(binding => {
        if (binding?.game_id) {
          index[binding.game_id] = binding
        }
      })
      setGameBindingsIndex(index)
    } catch (err) {
      const message = err?.error || err?.message || 'Failed to load LED game profiles'
      showToast(message, 'error')
    }
  }, [showToast])

  useEffect(() => {
    loadGameBindings()
  }, [loadGameBindings])

  useEffect(() => {
    setBindingPreview(null)
    setLastBindingPreviewKey(null)
  }, [selectedGame?.id, selectedGameProfileName])

  const loadGameResults = useCallback(
    async (query = '') => {
      setIsLoadingGames(true)
      gameSearchQueryRef.current = query
      try {
        const response = await searchLaunchBoxGames({ query, limit: 50 })
        const games = Array.isArray(response?.games) ? response.games : []
        const augmented = games.map((game) => ({
          ...game,
          assigned_profile: gameBindingsIndex[game.id] || null
        }))
        setGameResults(augmented)
        if (selectedGame) {
          const updatedSelection = augmented.find(game => game.id === selectedGame.id)
          if (updatedSelection) {
            setSelectedGame(updatedSelection)
          }
        }
      } catch (err) {
        const message = err?.error || err?.message || 'Failed to load LaunchBox games'
        showToast(message, 'error')
      } finally {
        setIsLoadingGames(false)
      }
    },
    [gameBindingsIndex, selectedGame, showToast]
  )

  useEffect(() => {
    if (activeMode === 'profiles' && !isLoadingGames && gameResults.length === 0) {
      loadGameResults('')
    }
  }, [activeMode, gameResults.length, isLoadingGames, loadGameResults])

  const handleSearchGames = useCallback(() => {
    loadGameResults(gameSearchTerm.trim())
  }, [gameSearchTerm, loadGameResults])

  const handleGameSearchKeyDown = useCallback(
    (event) => {
      if (event.key === 'Enter') {
        event.preventDefault()
        handleSearchGames()
      }
    },
    [handleSearchGames]
  )

  const handleSelectGame = useCallback(
    async (game) => {
      setSelectedGame(game)
      setSelectedGameBinding(null)
      setBindingPreview(null)
      setLastBindingPreviewKey(null)
      setIsLoadingBinding(true)
      try {
        const response = await fetchGameProfile(game.id)
        if (response?.game) {
          setSelectedGame(response.game)
        }
        const binding = response?.binding || null
        setSelectedGameBinding(binding)
        setSelectedGameProfileName(binding?.profile_name || gameBindingsIndex[game.id]?.profile_name || '')
      } catch (err) {
        const message = err?.error || err?.message || 'Failed to load game profile'
        showToast(message, 'error')
      } finally {
        setIsLoadingBinding(false)
      }
    },
    [gameBindingsIndex, showToast]
  )

  const handlePreviewGameProfile = useCallback(async () => {
    if (!selectedGame) {
      showToast('Select a LaunchBox game first', 'error')
      return
    }
    if (!selectedGameProfileName) {
      showToast('Choose a profile to preview', 'error')
      return
    }
    setIsPreviewingBinding(true)
    try {
      const response = await previewGameProfileBinding({
        gameId: selectedGame.id,
        profileName: selectedGameProfileName
      })
      setBindingPreview(response?.preview || null)
      setLastBindingPreviewKey(`${selectedGame.id}:${selectedGameProfileName}`)
      showToast('Binding preview ready', 'success')
    } catch (err) {
      const message = err?.error || err?.message || 'Failed to preview binding'
      showToast(message, 'error')
    } finally {
      setIsPreviewingBinding(false)
    }
  }, [selectedGame, selectedGameProfileName, showToast])

  const handleApplyGameProfile = useCallback(async () => {
    if (!selectedGame) {
      showToast('Select a LaunchBox game first', 'error')
      return
    }
    if (!selectedGameProfileName) {
      showToast('Choose a profile to assign', 'error')
      return
    }
    const previewKey = `${selectedGame.id}:${selectedGameProfileName}`
    if (lastBindingPreviewKey !== previewKey) {
      showToast('Preview the binding before applying', 'error')
      return
    }
    setIsApplyingBinding(true)
    try {
      const response = await applyGameProfileBinding({
        gameId: selectedGame.id,
        profileName: selectedGameProfileName
      })
      const binding = response?.binding || null
      setBindingPreview(response?.preview || null)
      setSelectedGameBinding(binding)
      setGameBindingsIndex(prev => ({ ...prev, [selectedGame.id]: binding }))
      setLastBindingPreviewKey(previewKey)
      showToast(`Assigned ${selectedGameProfileName} to ${selectedGame.title}`, 'success')
    } catch (err) {
      const message = err?.error || err?.message || 'Failed to assign LED profile'
      showToast(message, 'error')
    } finally {
      setIsApplyingBinding(false)
    }
  }, [lastBindingPreviewKey, selectedGame, selectedGameProfileName, showToast])

  const handleClearGameProfile = useCallback(async () => {
    if (!selectedGame) {
      showToast('Select a LaunchBox game first', 'error')
      return
    }
    if (!selectedGameBinding) {
      showToast('This game is not assigned to a profile', 'error')
      return
    }
    setIsClearingBinding(true)
    try {
      await deleteGameProfileBinding(selectedGame.id)
      setGameBindingsIndex(prev => {
        const next = { ...prev }
        delete next[selectedGame.id]
        return next
      })
      setSelectedGameBinding(null)
      setSelectedGameProfileName('')
      setBindingPreview(null)
      setLastBindingPreviewKey(null)
      showToast(`Cleared LED profile for ${selectedGame.title}`, 'success')
    } catch (err) {
      const message = err?.error || err?.message || 'Failed to remove assignment'
      showToast(message, 'error')
    } finally {
      setIsClearingBinding(false)
    }
  }, [selectedGame, selectedGameBinding, showToast])

  // Initialize WebSocket manager
  useEffect(() => {
    wsManagerRef.current = new LEDWebSocketManager()
    wsManagerRef.current.init(setConnectionStatus, setConnectionLog, showToast, refreshHardwareStatus)
    wsManagerRef.current.autoReconnectEnabled = true // Enable auto-reconnect by default

    // Check for handoff context from Dewey (URL-based)
    const urlParams = new URLSearchParams(window.location.search)
    const handoffContext = urlParams.get('context')
    const hasHandoff = Boolean((handoffContext || '').trim())
    const noHandoff = urlParams.has('nohandoff')
    const shouldHandoff = hasHandoff && !noHandoff
    if (shouldHandoff && handoffContext !== handoffProcessedRef.current) {
      const welcomeMsg = `Hi! Dewey told me you said: "${handoffContext}"\n\nI'm LED Blinky, your lighting specialist. I can help with button lights, colors, and LED scenes. What would you like me to do?`
      handoffProcessedRef.current = handoffContext
      setChatMessages([{ type: 'ai', message: welcomeMsg }])
      setChatOpen(true)
      speakAsBlinky(welcomeMsg).catch(err => {
        console.warn('[LEDBlinky] URL handoff TTS failed:', err)
      })
    }

    // Check for JSON handoff from Dewey (only when arriving via Dewey URL context)
    if (shouldHandoff) (async () => {
      try {
        const response = await fetch('/api/local/dewey/handoff/led-blinky', {
          method: 'GET',
          headers: {
            'Content-Type': 'application/json',
            'x-device-id': window?.AA_DEVICE_ID ?? 'cabinet-001',
            'x-panel': 'led-blinky',
            'x-scope': 'state'
          }
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
            const welcomeMsg = `Dewey mentioned you're working on: "${summaryText}". I'm LED Blinky, ready to help with your lighting setup!`
            setChatMessages([{ type: 'ai', message: welcomeMsg }])
            setChatOpen(true)
            speakAsBlinky(welcomeMsg).catch(err => {
              console.warn('[LEDBlinky] Handoff TTS failed:', err)
            })
          }
        }
      } catch (err) {
        console.warn('[LEDBlinky] Handoff fetch failed:', err)
      }
    })()

    return () => {
      if (wsManagerRef.current?.ws) {
        wsManagerRef.current.disableAutoReconnect()
        wsManagerRef.current.disconnect()
      }
      // Ensure any ongoing TTS is stopped when leaving this panel
      try { stopSpeaking() } catch { }
    }
  }, [refreshHardwareStatus, showToast])

  // Also stop any ongoing TTS if this component unmounts outside of the main effect
  useEffect(() => () => { try { stopSpeaking() } catch { } }, [])

  // Keyboard shortcuts are initialized after handlers are defined to avoid TDZ errors
  // Memoize button configurations to prevent recreation
  const buttonConfigs = useMemo(() => ({
    testButtons: [
      { player: '1', button: '1' }, { player: '1', button: '2' }, { player: '1', button: '3' }, { player: '1', button: '4' },
      { player: '1', button: '5' }, { player: '1', button: '6' }, { player: '1', button: '7' }, { player: '1', button: '8' },
      { player: '2', button: '1' }, { player: '2', button: '2' }, { player: '2', button: '3' }, { player: '2', button: '4' },
      { player: '2', button: '5' }, { player: '2', button: '6' }, { player: '2', button: '7' }, { player: '2', button: '8' },
      { player: '3', button: '1' }, { player: '3', button: '2' }, { player: '3', button: '3' }, { player: '3', button: '4' },
      { player: '4', button: '1' }, { player: '4', button: '2' }, { player: '4', button: '3' }, { player: '4', button: '4' }
    ],
    allButtons: [
      { player: '1', button: '1' }, { player: '1', button: '2' }, { player: '1', button: '3' }, { player: '1', button: '4' },
      { player: '1', button: '5' }, { player: '1', button: '6' }, { player: '1', button: '7' }, { player: '1', button: '8' },
      { player: '2', button: '1' }, { player: '2', button: '2' }, { player: '2', button: '3' }, { player: '2', button: '4' },
      { player: '2', button: '5' }, { player: '2', button: '6' }, { player: '2', button: '7' }, { player: '2', button: '8' },
      { player: '3', button: '1' }, { player: '3', button: '2' }, { player: '3', button: '3' }, { player: '3', button: '4' },
      { player: '4', button: '1' }, { player: '4', button: '2' }, { player: '4', button: '3' }, { player: '4', button: '4' }
    ]
  }), [])

  const runPatternCommand = useCallback(async (pattern, params = {}, successMessage = 'Pattern dispatched') => {
    try {
      const response = await runLEDPattern(pattern, params)
      const message = response?.status || successMessage
      showToast(message, 'success')
      return response
    } catch (err) {
      const message = err?.error || err?.message || 'Pattern request failed'
      showToast(message, 'error')
      throw err
    }
  }, [showToast])

  const updateLEDFromServer = useCallback((data) => {
    // Update LED state from server
    const key = `${data.player}-${data.button}`
    setCurrentActiveButtons(prev => {
      const newSet = new Set(prev)
      if (data.state) {
        newSet.add(key)
      } else {
        newSet.delete(key)
      }
      return newSet
    })
  }, [])

  const toggleLED = useCallback((player, button) => {
    // Normal toggle behavior
    const key = `${player}-${button}`
    const isActive = activeButtonsRef.current.has(key)
    const newState = !isActive

    setCurrentActiveButtons(prev => {
      const newSet = new Set(prev)
      if (newState) newSet.add(key)
      else newSet.delete(key)
      return newSet
    })

    wsManagerRef.current?.sendLEDCommand(player, button, newState)
  }, [])

  const clearAllLEDs = useCallback(async () => {
    setCurrentActiveButtons(new Set())
    try {
      await runPatternCommand('clear_all', {}, 'Cleared LED layout')
    } catch {
      /* error handled in runPatternCommand */
    }
  }, [runPatternCommand])

  const testAllLEDs = useCallback(async () => {
    const highlightSet = new Set(buttonConfigs.allButtons.map(({ player, button }) => `${player}-${button}`))
    setCurrentActiveButtons(highlightSet)
    try {
      const result = await testLED({ effect: 'solid', durationMs: 1200, color: '#9333ea' })
      const message = result?.status || 'Test dispatched'
      showToast(message, 'success')
    } catch (err) {
      const message = err?.error || err?.message || 'Quick test failed'
      showToast(message, 'error')
    } finally {
      setTimeout(() => {
        setCurrentActiveButtons(new Set())
      }, 1200)
    }
  }, [buttonConfigs.allButtons, showToast])

  const randomPattern = useCallback(async () => {
    const randomCount = Math.floor(Math.random() * buttonConfigs.allButtons.length * 0.7) + 3
    const shuffled = [...buttonConfigs.allButtons].sort(() => Math.random() - 0.5)
    const selection = shuffled.slice(0, randomCount)
    const activeSet = new Set(selection.map(({ player, button }) => `${player}-${button}`))
    setCurrentActiveButtons(activeSet)
    try {
      await runPatternCommand('random', { count: randomCount }, `Random pattern with ${randomCount} LEDs`)
    } catch {
      /* handled above */
    }
  }, [buttonConfigs.allButtons, runPatternCommand])

  const handleBrightnessChange = useCallback((value) => {
    setLedBrightness(value)
    if (brightnessDebounceRef.current) {
      clearTimeout(brightnessDebounceRef.current)
    }
    brightnessDebounceRef.current = setTimeout(() => {
      setLEDBrightness(value)
        .then((res) => {
          const message = res?.status || `Brightness set to ${value}%`
          showToast(message, 'success')
        })
        .catch((err) => {
          const message = err?.error || err?.message || 'Failed to set brightness'
          showToast(message, 'error')
        })
    }, 200)
  }, [showToast])

  const triggerHardwareTest = useCallback(
    async (effect, overrides = {}) => {
      try {
        const result = await testLED({ effect, ...overrides })
        if (result?.status) {
          showToast(`Hardware test: ${result.status}`, 'success')
        }
      } catch (err) {
        const message = err?.error || err?.message || 'Hardware test failed'
        showToast(message, 'error')
      }
    },
    [showToast]
  )

  const handleChannelTest = useCallback(async () => {
    if (!channelTestDevice) {
      showToast('Select a device before running a channel test', 'error')
      return
    }
    const channelNumber = Number(channelTestChannel)
    if (Number.isNaN(channelNumber) || channelNumber < 0) {
      showToast('Channel must be a non-negative number', 'error')
      return
    }

    setIsTestingChannel(true)
    setChannelTestResult(null)
    try {
      const result = await runLEDChannelTest({
        deviceId: channelTestDevice,
        channel: channelNumber,
        durationMs: 300
      })
      setChannelTestResult({ status: 'success', payload: result })
      showToast(`Channel ${channelNumber} test ${result.status}`, 'success')
    } catch (err) {
      const detail = err?.detail || err
      const message = detail?.message || detail?.error || err?.message || 'Channel test failed'
      setChannelTestResult({ status: 'error', message })
      showToast(message, 'error')
    } finally {
      setIsTestingChannel(false)
    }
  }, [channelTestChannel, channelTestDevice, showToast])

  // LED Mapping handlers
  const handleLoadProfile = useCallback(async (profileValue) => {
    if (!profileValue) return null

    const profileEntry = availableProfiles.find(profile => profile.value === profileValue)
    const requestName = profileEntry?.value ?? profileValue

    try {
      const profile = await getLEDProfile(requestName)
      const mapping = profile.mapping || {}
      const buttons = extractButtonsFromPayload(mapping)

      if (Object.keys(buttons).length > 0) {
        setMappingForm(buildFormFromButtons(buttons))
        setMappingData(JSON.stringify({ buttons }, null, 2))
      } else {
        setMappingForm({ ...DEFAULT_MAPPING_FORM })
        setMappingData(JSON.stringify(mapping, null, 2))
      }

      const mergedMetadata = {
        ...(typeof profile.metadata === 'object' && profile.metadata ? profile.metadata : {}),
        ...(profileEntry?.metadata || {})
      }
      const payload = {
        profile_name: profile.profile_name || mergedMetadata.profile_name || requestName,
        scope: profile.scope || mergedMetadata.scope || 'game',
        game: profile.game || mergedMetadata.game || requestName,
        metadata: { ...mergedMetadata, source: 'led-blinky-panel' },
        buttons
      }

      setSelectedProfile(profileEntry?.value ?? profileValue)
      setSelectedProfileMeta(mergedMetadata)
      setProfilePreview(null)
      showToast(`Loaded profile: ${payload.game}`, 'success')
      return payload
    } catch (err) {
      console.error('Failed to load profile:', err)
      showToast('Failed to load profile', 'error')
      return null
    }
  }, [availableProfiles, showToast])

  const buildProfilePayload = useCallback(() => {
    if (!mappingData.trim()) {
      throw new Error('Empty mapping payload')
    }

    let parsed
    parsed = JSON.parse(mappingData)

    const buttons = extractButtonsFromPayload(parsed)
    if (Object.keys(buttons).length === 0) {
      throw new Error('No valid button mappings found')
    }

    const profileName = parsed.profile_name || selectedProfile || 'custom-profile'
    const scope = parsed.scope || selectedProfileMeta?.scope || 'game'
    const game = parsed.game || selectedProfileMeta?.game || profileName
    const metadata = {
      ...(typeof parsed.metadata === 'object' && parsed.metadata ? parsed.metadata : {}),
      source: 'led-blinky-panel'
    }

    return {
      profile_name: profileName,
      scope,
      game,
      metadata,
      buttons
    }
  }, [mappingData, selectedProfile, selectedProfileMeta])

  const handlePreviewProfile = useCallback(
    async (payloadOverride = null, { profileKey } = {}) => {
      if (!payloadOverride && !mappingData.trim()) {
        showToast('Please enter mapping data', 'error')
        return
      }

      let payload
      try {
        payload = payloadOverride || buildProfilePayload()
      } catch (err) {
        if (err instanceof SyntaxError) {
          showToast('Invalid JSON format', 'error')
        } else {
          const message = err?.message || 'Failed to generate preview'
          showToast(message, 'error')
        }
        return
      }

      try {
        const payloadString = JSON.stringify(payload)
        const preview = await previewLEDProfile(payload)
        setProfilePreview(preview)
        setLastPreviewPayload(payloadString)
        setLastPreviewProfileKey(profileKey || selectedProfile || payload.profile_name || payload.game || null)
        showToast('Preview generated', 'success')
      } catch (err) {
        if (err instanceof SyntaxError) {
          showToast('Invalid JSON format', 'error')
        } else {
          const message = err?.message || 'Failed to generate preview'
          showToast(message, 'error')
        }
      }
    },
    [buildProfilePayload, mappingData, selectedProfile, showToast]
  )

  const handleApplyProfile = useCallback(async () => {
    if (!mappingData.trim()) {
      showToast('Please enter mapping data', 'error')
      return
    }

    if (!profilePreview) {
      showToast('Preview changes before applying', 'error')
      return
    }

    setIsApplyingMapping(true)
    try {
      const basePayload = buildProfilePayload()
      const payloadString = JSON.stringify(basePayload)
      if (!lastPreviewPayload || payloadString !== lastPreviewPayload) {
        showToast('Preview changes before applying', 'error')
        return
      }
      const result = await applyLEDProfile({ ...basePayload, dry_run: false })
      setProfilePreview(result.preview)
      setLastPreviewPayload(payloadString)
      const statusText = result.status === 'applied' ? 'Profile applied successfully' : 'Dry run'
      showToast(statusText, 'success')
    } catch (err) {
      if (err instanceof SyntaxError) {
        showToast('Invalid JSON format', 'error')
      } else {
        const message = err?.detail || err?.error || err?.message || 'Failed to apply mapping'
        showToast(message, 'error')
      }
    } finally {
      setIsApplyingMapping(false)
    }
  }, [buildProfilePayload, lastPreviewPayload, mappingData, profilePreview, showToast])

  const previewProfileFromLibrary = useCallback(
    async (profileValue) => {
      const payload = await handleLoadProfile(profileValue)
      if (!payload) return
      if (!payload.buttons || Object.keys(payload.buttons).length === 0) {
        showToast('Profile has no button mappings to preview', 'error')
        return
      }
      try {
        await handlePreviewProfile(payload, { profileKey: profileValue })
      } catch {
        /* errors handled inside handlePreviewProfile */
      }
    },
    [handleLoadProfile, handlePreviewProfile, showToast]
  )

  const applyProfileFromLibrary = useCallback(
    async (profileValue) => {
      if (lastPreviewProfileKey !== profileValue) {
        showToast('Preview this profile before applying', 'error')
        return
      }
      await handleApplyProfile()
    },
    [handleApplyProfile, lastPreviewProfileKey, showToast]
  )

  const editProfileInDesigner = useCallback(
    async (profileValue) => {
      const payload = await handleLoadProfile(profileValue)
      if (payload) {
        setActiveMode('animation')
      }
    },
    [handleLoadProfile]
  )

  const toggleWebSocketConnection = useCallback(async () => {
    if (connectionStatus === 'connected') {
      wsManagerRef.current?.disconnect()
      await refreshHardwareStatus()
      return
    }

    const latestStatus = await refreshHardwareStatus()
    const targetUrl = buildGatewayWebSocketUrl(latestStatus?.ws?.url || gatewaySocketUrl)
    if (!targetUrl) {
      showToast('Gateway WebSocket unavailable', 'error')
      return
    }
    wsManagerRef.current?.connect(targetUrl)
  }, [connectionStatus, gatewaySocketUrl, refreshHardwareStatus, showToast])

  // AI response helper (moved before toggleVoiceInput to avoid TDZ)
  const getAIResponse = useCallback((message) => {
    const lowerMessage = message.toLowerCase()

    if (lowerMessage.includes('websocket') || lowerMessage.includes('connect') || lowerMessage.includes('hardware')) {
      return "To connect to your LED hardware, open the Hardware tab and let the gateway issue the /api/local/led/ws link. The panel now requests that URL automatically so headers stay intact—no more raw ws:// entries needed."
    } else if (lowerMessage.includes('test') || lowerMessage.includes('led')) {
      return "I can help you test your LED setup! Use the Test All button for a full system check, or try the Hardware tab for specific test patterns. What specific testing do you need help with?"
    } else if (lowerMessage.includes('game') || lowerMessage.includes('profile')) {
      return "Game profiles automatically configure your LEDs for specific games. Try selecting Street Fighter II or Mortal Kombat from the Game Profiles tab to see how it optimizes button layouts!"
    } else {
      return "I'm here to help with your LED panel configuration! I can assist with WebSocket connections, testing LEDs, setting up game profiles, creating animations, or troubleshooting hardware issues. What would you like to work on?"
    }
  }, [])

  const toggleVoiceInput = useCallback(() => {
    // Stop any existing recognition first
    if (recognitionRef.current) {
      try {
        recognitionRef.current.stop()
      } catch (err) {
        // Ignore errors when stopping
      }
      recognitionRef.current = null
    }

    if (!isVoiceRecording) {
      // Start voice recording
      const SpeechRecognition = window.SpeechRecognition || window.webkitSpeechRecognition

      if (!SpeechRecognition) {
        showToast('Speech recognition not supported in this browser. Use Chrome/Edge.', 'error')
        return
      }

      try {
        const recognition = new SpeechRecognition()
        recognition.continuous = false
        recognition.interimResults = false
        recognition.lang = 'en-US'

        // Store in ref to prevent multiple instances
        recognitionRef.current = recognition

        recognition.onstart = () => {
          setIsVoiceRecording(true)
          showToast('Listening... speak now!', 'success')
        }

        recognition.onresult = async (event) => {
          // Only process if this is a final result to prevent duplicates
          if (!event.results[0].isFinal) {
            return
          }

          const transcript = event.results[0][0].transcript
          setIsVoiceRecording(false)
          recognitionRef.current = null

          if (!transcript.trim()) {
            showToast('No speech detected', 'warning')
            return
          }

          console.log('[LED Blinky Voice] Processing transcript:', transcript)

          // Add user message to chat
          setChatMessages(prev => [...prev, { type: 'user', message: transcript }])
          showToast(`You said: "${transcript}"`, 'success')

          // Send to useBlinkyChat hook for AI processing
          const processVoiceInput = async () => {
            try {
              console.log('[LED Blinky Voice] Sending to blinkyChat.send():', transcript)
              const result = await blinkyChat.send(transcript, 'state')

              const response = result?.message?.content || 'I did not receive a response.'
              const commands = result?.commands || []
              console.log('[LED Blinky Voice] AI responded:', response.substring(0, 50))
              console.log('[LED Blinky Voice] Parsed commands:', commands)

              setChatMessages(prev => [...prev, { type: 'ai', message: response }])

              // Execute any LED commands from the AI response
              if (commands.length > 0) {
                console.log('[LED Blinky Voice] Executing', commands.length, 'commands...')
                const commandContext = {
                  calibrationToken,
                  setCalibrationToken,
                  showToast,
                  loadChannelMappings
                }
                await executeLEDCommands(commands, commandContext)
              }

              // Play the response using Blinky's voice
              try {
                console.log('[LED Blinky Voice] Speaking response:', response.substring(0, 50))
                await speakAsBlinky(response)
              } catch (err) {
                console.error('[LED Blinky Voice] TTS error:', err)
              }
            } catch (err) {
              console.error('[LED Blinky Voice] AI error:', err)
              const errorMsg = 'Sorry, I encountered an error. Please try again.'
              setChatMessages(prev => [...prev, { type: 'ai', message: errorMsg }])
            }
          }

          processVoiceInput()
        }

        recognition.onerror = (event) => {
          console.error('Speech recognition error:', event.error)
          showToast(`Voice error: ${event.error}`, 'error')
          setIsVoiceRecording(false)
          recognitionRef.current = null
        }

        recognition.onend = () => {
          setIsVoiceRecording(false)
          recognitionRef.current = null
        }

        recognition.start()
      } catch (err) {
        console.error('Failed to start speech recognition:', err)
        showToast('Failed to start voice input', 'error')
        setIsVoiceRecording(false)
        recognitionRef.current = null
      }
    } else {
      // Stop voice recording
      setIsVoiceRecording(false)
      showToast('Voice input stopped', 'success')
    }
  }, [isVoiceRecording, showToast, getAIResponse])

  const sendChatMessage = useCallback(async () => {
    if (!chatInput.trim()) return

    const userMessage = chatInput.trim()
    setChatMessages(prev => [...prev, { type: 'user', message: userMessage }])
    setChatInput('')

    try {
      // Send to useBlinkyChat hook for AI processing
      console.log('[LED Blinky Chat] Sending typed message:', userMessage)
      const result = await blinkyChat.send(userMessage, 'state')

      const response = result?.message?.content || 'I did not receive a response.'
      const commands = result?.commands || []
      console.log('[LED Blinky Chat] AI responded:', response.substring(0, 50))
      console.log('[LED Blinky Chat] Parsed commands:', commands)

      setChatMessages(prev => [...prev, { type: 'ai', message: response }])

      // Execute any LED commands from the AI response
      if (commands.length > 0) {
        console.log('[LED Blinky Chat] Executing', commands.length, 'commands...')
        const commandContext = {
          calibrationToken,
          setCalibrationToken,
          showToast,
          loadChannelMappings
        }
        await executeLEDCommands(commands, commandContext)
      }

      // NOTE: No TTS for typed messages - only voice input speaks
    } catch (err) {
      console.error('[LED Blinky Chat] Error:', err)
      const errorMsg = 'Sorry, I encountered an error. Please try again.'
      setChatMessages(prev => [...prev, { type: 'ai', message: errorMsg }])
    }
  }, [chatInput, blinkyChat, calibrationToken, setCalibrationToken, showToast, loadChannelMappings])

  // Keyboard shortcuts (moved below handler definitions to avoid TDZ)
  useEffect(() => {
    const handleKeyPress = (e) => {
      if (e.target.tagName === 'INPUT' || e.target.tagName === 'TEXTAREA' || e.target.tagName === 'SELECT') {
        return
      }

      if (e.ctrlKey || e.metaKey) {
        switch (e.key.toLowerCase()) {
          case 't':
            e.preventDefault()
            testAllLEDs()
            showToast('Keyboard shortcut: Test All LEDs', 'success')
            break
          case 'c':
            e.preventDefault()
            clearAllLEDs()
            showToast('Keyboard shortcut: Clear All LEDs', 'success')
            break
          case 'r':
            e.preventDefault()
            randomPattern()
            showToast('Keyboard shortcut: Random Pattern', 'success')
            break
        }
      } else {
        switch (e.key) {
          case 'Escape':
            if (chatOpen) {
              setChatOpen(false)
              showToast('Chat closed', 'success')
            }
            break
          case ' ':
            e.preventDefault()
            toggleLED('1', '1')
            showToast('Space: Toggled P1-B1', 'success')
            break
        }
      }
    }

    document.addEventListener('keydown', handleKeyPress)
    return () => document.removeEventListener('keydown', handleKeyPress)
  }, [chatOpen, testAllLEDs, clearAllLEDs, randomPattern, toggleLED])

  const hasMappingInput = Boolean(mappingData.trim())
  const canApplyProfile = hasMappingInput && Boolean(profilePreview) && Boolean(lastPreviewPayload) && !isApplyingMapping
  const bindingRequestKey = selectedGame && selectedGameProfileName ? `${selectedGame.id}:${selectedGameProfileName}` : null
  const canPreviewBinding = Boolean(selectedGame && selectedGameProfileName && !isPreviewingBinding && !isLoadingBinding)
  const canApplyBinding =
    Boolean(bindingPreview && bindingRequestKey && lastBindingPreviewKey === bindingRequestKey && !isApplyingBinding)
  const canClearBinding = Boolean(selectedGameBinding && !isClearingBinding)
  const canApplyLibraryProfile =
    Boolean(
      selectedProfile &&
      profilePreview &&
      lastPreviewPayload &&
      lastPreviewProfileKey === selectedProfile &&
      !isApplyingMapping
    )
  const filteredProfiles = useMemo(() => {
    const term = profileSearchTerm.trim().toLowerCase()
    if (!term) {
      return availableProfiles
    }
    return availableProfiles.filter(profile => {
      const label = (profile.label || '').toLowerCase()
      const filename = (profile.metadata?.filename || '').toLowerCase()
      const gameName = (profile.metadata?.game || '').toLowerCase()
      const scope = (profile.metadata?.scope || '').toLowerCase()
      return label.includes(term) || filename.includes(term) || gameName.includes(term) || scope.includes(term)
    })
  }, [availableProfiles, profileSearchTerm])
  const selectedProfileDisplayName =
    selectedProfileMeta?.game ||
    selectedProfileMeta?.profile_name ||
    selectedProfile ||
    'profile'
  const libraryPreviewReady = Boolean(selectedProfile && lastPreviewProfileKey === selectedProfile && profilePreview)

  return (
    <div className="led-panel-main">
      {/* Chat Toggle Button */}
      <button
        className="led-chat-toggle"
        onClick={() => setChatOpen(!chatOpen)}
        aria-label={chatOpen ? 'Close chat' : 'Open chat'}
        aria-expanded={chatOpen}
      >
        💬
      </button>

      {/* LED Click-to-Map Calibration Modal - DISABLED: use inline calibration wizard with purple GUI instead */}
      {false && ledLearnWizardActive && (
        <div style={{
          position: 'fixed',
          top: 0,
          left: 0,
          right: 0,
          bottom: 0,
          background: 'rgba(0, 0, 0, 0.9)',
          display: 'flex',
          alignItems: 'center',
          justifyContent: 'center',
          zIndex: 9999
        }}>
          <div style={{
            background: 'linear-gradient(135deg, #1a1a2e, #16213e)',
            borderRadius: '20px',
            border: '2px solid #9333ea',
            padding: '32px',
            maxWidth: '800px',
            width: '95%',
            maxHeight: '90vh',
            overflow: 'auto',
            boxShadow: '0 0 60px rgba(147, 51, 234, 0.4)'
          }}>
            {/* Header */}
            <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '24px' }}>
              <h2 style={{
                fontSize: '24px',
                fontWeight: '700',
                background: 'linear-gradient(135deg, #c084fc, #9333ea)',
                backgroundClip: 'text',
                WebkitBackgroundClip: 'text',
                WebkitTextFillColor: 'transparent',
                margin: 0
              }}>
                💡 LED Click-to-Map Calibration
              </h2>
              <button
                onClick={async () => {
                  try {
                    await fetch('/api/local/led/click-to-map/cancel', {
                      method: 'POST',
                      headers: { 'x-scope': 'config', 'x-device-id': 'CAB-0001' }
                    })
                  } catch (e) { }
                  setLedLearnWizardActive(false)
                  setLedLearnWizardStep(0)
                }}
                style={{
                  background: 'transparent',
                  border: 'none',
                  color: '#9ca3af',
                  fontSize: '28px',
                  cursor: 'pointer'
                }}
              >
                ×
              </button>
            </div>

            {/* Status */}
            <div style={{
              background: 'rgba(16, 185, 129, 0.1)',
              border: '1px solid #10b981',
              borderRadius: '12px',
              padding: '16px',
              marginBottom: '20px',
              textAlign: 'center'
            }}>
              <div style={{ fontSize: '18px', color: '#10b981', fontWeight: '600', marginBottom: '8px' }}>
                Channel {clickToMapChannel || 1} / {clickToMapTotal || 32} is flashing
              </div>
              <div style={{ color: '#9ca3af', fontSize: '14px' }}>
                Click the button below that just lit up (or Skip if no button lit)
              </div>
            </div>

            {/* Button Grid - User clicks to map */}
            <div style={{ marginBottom: '20px' }}>
              <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '12px' }}>
                <h3 style={{ color: '#e5e7eb', fontSize: '16px', margin: 0 }}>Select the button that lit up:</h3>
                {/* Player Count Toggle */}
                <div style={{ display: 'flex', gap: '8px', alignItems: 'center' }}>
                  <span style={{ color: '#9ca3af', fontSize: '12px' }}>Players:</span>
                  {[2, 4].map(count => (
                    <button
                      key={count}
                      onClick={() => setCabinetPlayerCount(count)}
                      style={{
                        background: cabinetPlayerCount === count ? '#9333ea' : 'transparent',
                        border: cabinetPlayerCount === count ? 'none' : '1px solid #6b7280',
                        borderRadius: '6px',
                        color: cabinetPlayerCount === count ? 'white' : '#9ca3af',
                        padding: '4px 12px',
                        fontSize: '12px',
                        cursor: 'pointer'
                      }}
                    >
                      {count}P
                    </button>
                  ))}
                </div>
              </div>

              {/* Player Grids - Dynamic based on cabinetPlayerCount */}
              <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: '12px' }}>
                {[1, 2, 3, 4].filter(p => p <= cabinetPlayerCount).map(player => (
                  <div key={player} style={{ background: 'rgba(0,0,0,0.3)', borderRadius: '12px', padding: '10px' }}>
                    <div style={{
                      color: player === 1 ? '#ef4444' : player === 2 ? '#3b82f6' : player === 3 ? '#10b981' : '#f59e0b',
                      fontWeight: '600',
                      marginBottom: '8px',
                      fontSize: '13px'
                    }}>
                      Player {player}
                    </div>
                    <div style={{ display: 'grid', gridTemplateColumns: 'repeat(5, 1fr)', gap: '4px' }}>
                      {[1, 2, 3, 4, 5, 6, 7, 8].map(btn => (
                        <button
                          key={btn}
                          onClick={async () => {
                            try {
                              const res = await fetch('/api/local/led/click-to-map/assign', {
                                method: 'POST',
                                headers: { 'x-scope': 'config', 'x-device-id': 'CAB-0001', 'Content-Type': 'application/json' },
                                body: JSON.stringify({ logical_button: `p${player}.button${btn}` })
                              })
                              const data = await res.json()
                              if (data.status === 'complete') {
                                showToast(`All ${data.total_mapped || 0} channels mapped!`, 'success')
                              } else {
                                setClickToMapChannel(data.next_channel)
                              }
                            } catch (e) {
                              showToast('Failed to map: ' + e.message, 'error')
                            }
                          }}
                          style={{
                            background: player === 1 ? '#ef4444' : player === 2 ? '#3b82f6' : player === 3 ? '#10b981' : '#f59e0b',
                            border: 'none',
                            borderRadius: '4px',
                            color: 'white',
                            padding: '6px 4px',
                            fontSize: '10px',
                            fontWeight: '600',
                            cursor: 'pointer'
                          }}
                        >
                          B{btn}
                        </button>
                      ))}
                      {/* Start & Coin */}
                      <button
                        onClick={async () => {
                          try {
                            const res = await fetch('/api/local/led/click-to-map/assign', {
                              method: 'POST',
                              headers: { 'x-scope': 'config', 'x-device-id': 'CAB-0001', 'Content-Type': 'application/json' },
                              body: JSON.stringify({ logical_button: `p${player}.start` })
                            })
                            const data = await res.json()
                            if (data.status === 'complete') showToast('All channels mapped!', 'success')
                            else setClickToMapChannel(data.next_channel)
                          } catch (e) { }
                        }}
                        style={{
                          background: '#fbbf24',
                          border: 'none', borderRadius: '4px', color: '#1a1a2e', padding: '6px 4px', fontSize: '10px', fontWeight: '600', cursor: 'pointer'
                        }}
                      >
                        ST
                      </button>
                      <button
                        onClick={async () => {
                          try {
                            const res = await fetch('/api/local/led/click-to-map/assign', {
                              method: 'POST',
                              headers: { 'x-scope': 'config', 'x-device-id': 'CAB-0001', 'Content-Type': 'application/json' },
                              body: JSON.stringify({ logical_button: `p${player}.coin` })
                            })
                            const data = await res.json()
                            if (data.status === 'complete') showToast('All channels mapped!', 'success')
                            else setClickToMapChannel(data.next_channel)
                          } catch (e) { }
                        }}
                        style={{
                          background: '#d97706',
                          border: 'none', borderRadius: '4px', color: 'white', padding: '6px 4px', fontSize: '10px', fontWeight: '600', cursor: 'pointer'
                        }}
                      >
                        CN
                      </button>
                    </div>
                  </div>
                ))}
              </div>
            </div>

            {/* Actions */}
            <div style={{ display: 'flex', gap: '12px', justifyContent: 'center' }}>
              <button
                onClick={async () => {
                  try {
                    const res = await fetch('/api/local/led/click-to-map/skip', {
                      method: 'POST',
                      headers: { 'x-scope': 'config', 'x-device-id': 'CAB-0001' }
                    })
                    const data = await res.json()
                    if (data.status === 'complete') {
                      showToast('All channels done!', 'success')
                    } else {
                      setClickToMapChannel(data.next_channel)
                    }
                  } catch (e) { }
                }}
                style={{
                  background: 'transparent',
                  border: '1px solid #6b7280',
                  borderRadius: '8px',
                  color: '#9ca3af',
                  padding: '12px 24px',
                  fontSize: '14px',
                  cursor: 'pointer'
                }}
              >
                ⏭️ Skip (No Button Lit)
              </button>
              <button
                onClick={async () => {
                  try {
                    const res = await fetch('/api/local/led/click-to-map/save', {
                      method: 'POST',
                      headers: { 'x-scope': 'config', 'x-device-id': 'CAB-0001' }
                    })
                    const data = await res.json()
                    showToast(data.message || 'Saved!', 'success')
                    setLedLearnWizardActive(false)
                  } catch (e) {
                    showToast('Save failed: ' + e.message, 'error')
                  }
                }}
                style={{
                  background: 'linear-gradient(135deg, #10b981, #059669)',
                  border: 'none',
                  borderRadius: '8px',
                  color: 'white',
                  padding: '12px 24px',
                  fontSize: '14px',
                  fontWeight: '600',
                  cursor: 'pointer'
                }}
              >
                💾 Save Mappings
              </button>
            </div>
          </div>
        </div>
      )}

      {/* Chat Sidebar */}
      {chatOpen && (
        <div className="led-chat-sidebar" role="dialog" aria-label="LED Assistant Chat">
          <div className="led-chat-header">
            <div style={{ display: 'flex', alignItems: 'center', gap: '12px' }}>
              <img
                src="/led-avatar.jpeg"
                alt="LED Assistant Avatar"
                className="led-chat-avatar"
              />
              <div>
                <div style={{ fontSize: '16px', fontWeight: '600', color: '#9333ea' }}>LED Assistant</div>
                <div style={{ fontSize: '12px', color: '#d1d5db', display: 'flex', alignItems: 'center', gap: '8px' }}>
                  <div style={{ width: '8px', height: '8px', borderRadius: '50%', background: '#10b981' }}></div>
                  <span>Connected</span>
                </div>
              </div>
            </div>
            <button
              className="led-chat-close"
              onClick={() => setChatOpen(false)}
              aria-label="Close chat"
            >
              ×
            </button>
          </div>

          <div className="led-chat-messages" aria-live="polite">
            {chatMessages.map((msg, index) => (
              <div
                key={index}
                style={{
                  display: 'flex',
                  alignItems: 'flex-start',
                  gap: msg.type === 'ai' ? '8px' : '0',
                  alignSelf: msg.type === 'user' ? 'flex-end' : 'flex-start',
                  maxWidth: '80%',
                  flexDirection: msg.type === 'user' ? 'row-reverse' : 'row'
                }}
              >
                {msg.type === 'ai' && (
                  <img
                    src="/led-avatar.jpeg"
                    alt="LED Assistant"
                    style={{
                      width: '28px',
                      height: '28px',
                      borderRadius: '50%',
                      border: '1px solid #9333ea',
                      boxShadow: '0 0 6px rgba(147, 51, 234, 0.3)',
                      objectFit: 'cover',
                      flexShrink: 0,
                      marginTop: '2px'
                    }}
                  />
                )}
                <div className={`led-message ${msg.type}`}>
                  {msg.message}
                </div>
              </div>
            ))}
          </div>

          <div className="led-chat-input-container">
            <div className="led-chat-input-row">
              <input
                type="text"
                className="led-chat-input"
                value={chatInput}
                onChange={(e) => setChatInput(e.target.value)}
                onKeyPress={(e) => e.key === 'Enter' && sendChatMessage()}
                placeholder={isVoiceRecording ? "Listening..." : "Type your message or use voice input..."}
                aria-label="Chat with LED assistant"
              />
              <button
                className={`led-voice-btn ${isVoiceRecording ? 'recording' : ''}`}
                onClick={toggleVoiceInput}
                title={isVoiceRecording ? "Stop voice input" : "Start voice input"}
                aria-label={isVoiceRecording ? "Stop voice input" : "Start voice input"}
                aria-pressed={isVoiceRecording}
              >
                🎤
              </button>
              <button
                className="led-send-btn"
                onClick={sendChatMessage}
                aria-label="Send message"
              >
                ↵
              </button>
            </div>
          </div>
        </div>
      )
      }

      {/* Main Panel Container */}
      <div className="led-main-container">
        {/* Header */}
        <div className="led-header">
          <div className="led-header-title">
            <img
              src="/led-avatar.jpeg"
              alt="LED Mascot"
              className="led-header-avatar"
              onError={(e) => { e.currentTarget.style.display = 'none' }}
            />
            🎮 LED Blinky Configuration Center
          </div>
          <div style={{ display: 'flex', gap: '12px', alignItems: 'center' }}>
            <button
              className="led-close-btn"
              onClick={() => navigate('/')}
              aria-label="Close LED panel"
            >
              ×
            </button>
          </div>
        </div>

        {/* Status Bar */}
        <div className="led-status-bar">
          <div className="led-status-item">
            <div className={`led-status-dot ${connectedDevices.length > 0 ? 'connected' : simulationMode ? 'simulation' : 'disconnected'}`}></div>
            <span>
              {connectedDevices.length > 0
                ? `LED-Wiz Connected (${connectedDevices.length})`
                : simulationMode
                  ? 'Simulation Mode'
                  : 'Hardware Disconnected'}
            </span>
          </div>
          <div className="led-status-item">
            <span>Active Profile: Street Fighter II</span>
          </div>
          <div className="led-status-item">
            <span>{currentActiveButtons.size} LEDs</span>
          </div>
          <div className="led-status-item" style={{ display: 'flex', alignItems: 'center', gap: '8px' }}>
            <label htmlFor="cabinetPlayerCount" style={{ color: '#9ca3af', fontSize: '13px' }}>Cabinet:</label>
            <select
              id="cabinetPlayerCount"
              value={cabinetPlayerCount}
              onChange={(e) => setCabinetPlayerCount(Number(e.target.value))}
              style={{
                background: '#111',
                border: '1px solid #374151',
                borderRadius: '6px',
                color: '#e5e7eb',
                padding: '4px 12px',
                fontSize: '13px',
                cursor: 'pointer'
              }}
            >
              <option value={2}>2-Player</option>
              <option value={4}>4-Player</option>
            </select>
          </div>
          <button
            onClick={() => calibrationWizard.startWizard({ totalPorts: 32 })}
            disabled={calibrationWizard.isActive || calibrationWizard.isLoading}
            style={{
              background: calibrationWizard.isActive ? '#374151' : 'linear-gradient(135deg, #9333ea, #7c3aed)',
              border: 'none',
              borderRadius: '8px',
              color: 'white',
              padding: '6px 14px',
              fontSize: '13px',
              fontWeight: '600',
              cursor: calibrationWizard.isActive ? 'not-allowed' : 'pointer',
              display: 'flex',
              alignItems: 'center',
              gap: '6px'
            }}
          >
            🎓 Start LED Mapping
          </button>
        </div>

        {/* Title Section */}

        {/* Hardware Scanning Banner */}
        {isRefreshingStatus && (
          <div className="led-scanning-indicator">
            <div className="spinner"></div>
            <div className="text">Scanning for LED hardware...</div>
          </div>
        )}

        {/* Hardware Status Banner */}
        {!isRefreshingStatus && hardwareStatus && (
          <div className={`led-hardware-banner ${simulationMode ? 'mock' : connectedDevices.length > 0 ? 'connected' : 'disconnected'}`}>
            <div className="info">
              <div className="status-icon"></div>
              <span>
                {simulationMode
                  ? 'Simulation Mode - No LED-Wiz hardware detected. Connect your LED-Wiz and refresh.'
                  : connectedDevices.length > 0
                    ? `LED-Wiz Connected (${connectedDevices.length} device${connectedDevices.length > 1 ? 's' : ''})`
                    : 'No LED hardware detected - Running in simulation mode'
                }
              </span>
            </div>
            <button className="action" onClick={refreshHardwareStatus}>Refresh</button>
          </div>
        )}

        <div style={{
          padding: '28px 32px 20px',
          textAlign: 'center',
          background: '#000000',
          borderBottom: '1px solid #9333ea'
        }}>
          <div style={{
            fontSize: '32px',
            fontWeight: '800',
            background: 'linear-gradient(135deg, #c084fc, #9333ea, #7c3aed)',
            backgroundClip: 'text',
            WebkitBackgroundClip: 'text',
            WebkitTextFillColor: 'transparent',
            marginBottom: '10px'
          }}>
            🎨 LED Control Center
          </div>
          <div style={{
            color: '#d1d5db',
            fontSize: '15px',
            maxWidth: '600px',
            margin: '0 auto',
            lineHeight: '1.5'
          }}>
            Complete LED management with real-time control, game profiles, and custom animations
          </div>
        </div>

        {/* Mode Switcher */}
        <div style={{
          background: '#000000',
          padding: '16px 24px',
          display: 'flex',
          justifyContent: 'center',
          gap: '4px',
          borderBottom: '1px solid #9333ea'
        }}>
          {[
            { key: 'profiles', icon: '🎮', label: 'Game Profiles' },
            { key: 'realtime', icon: '⚡', label: 'Real-time Control' },
            { key: 'layout', icon: '🔧', label: 'LED Layout' },
            { key: 'hardware', icon: '💻', label: 'Hardware' },
            { key: 'calibration', icon: '🎓', label: 'Calibration' }
          ].map((mode) => {
            const isDisabled = Boolean(mode.disabled)
            const isActive = activeMode === mode.key
            return (
              <button
                key={mode.key}
                onClick={() => {
                  if (!isDisabled) {
                    setActiveMode(mode.key)
                  }
                }}
                disabled={isDisabled}
                style={{
                  background: isActive ? 'linear-gradient(135deg, #111111, #0a0a0a)' : 'transparent',
                  border: isActive ? '1px solid #9333ea' : '1px solid transparent',
                  color: isActive ? '#9333ea' : '#9ca3af',
                  padding: '12px 28px',
                  cursor: isDisabled ? 'not-allowed' : 'pointer',
                  fontSize: '14px',
                  fontWeight: '600',
                  borderRadius: '10px',
                  display: 'flex',
                  flexDirection: 'column',
                  alignItems: 'center',
                  gap: '6px',
                  opacity: isDisabled ? 0.5 : 1
                }}
              >
                <span style={{ display: 'flex', alignItems: 'center', gap: '10px' }}>
                  <span>{mode.icon}</span>
                  <span>{mode.label}</span>
                </span>
                {isDisabled ? <ComingSoonTag /> : null}
              </button>
            )
          })}
        </div>

        {/* Main Content Area */}
        <div style={{
          display: 'grid',
          gridTemplateColumns: 'minmax(450px, 1fr) minmax(500px, 2fr)',
          gap: '28px',
          padding: '28px',
          background: '#000000',
          minHeight: '400px'
        }}>
          {/* Left: LED Panel */}
          <div style={{ display: 'flex', flexDirection: 'column', gap: '20px' }}>
            <div style={{
              background: '#0f0f0f',
              border: '1px solid #9333ea',
              borderRadius: '16px',
              padding: '24px'
            }}>
              <div style={{
                display: 'flex',
                justifyContent: 'space-between',
                alignItems: 'center',
                marginBottom: '20px'
              }}>
                <div style={{
                  fontSize: '16px',
                  fontWeight: '700',
                  color: '#9333ea'
                }}>
                  Arcade Panel Layout
                </div>
                <div style={{
                  display: 'flex',
                  alignItems: 'center',
                  gap: '8px',
                  fontSize: '12px',
                  color: '#10b981'
                }}>
                  <div style={{ width: '8px', height: '8px', borderRadius: '50%', background: '#10b981' }}></div>
                  <span>Live Preview</span>
                </div>
              </div>

              {/* LED Panel */}
              <div style={{
                background: '#000000',
                borderRadius: '12px',
                padding: '36px',
                minHeight: '380px',
                display: 'flex',
                alignItems: 'center',
                justifyContent: 'center',
                border: '1px solid #7c3aed'
              }}>
                <div style={{
                  display: 'grid',
                  gridTemplateColumns: '1fr 1fr 1fr 1fr',
                  gridTemplateRows: 'auto auto auto',
                  gap: '20px',
                  width: '100%',
                  maxWidth: '640px'
                }}>
                  {/* Player 3 (Top-Left) */}
                  <div style={{ gridColumn: 1, gridRow: 1, display: 'flex', flexDirection: 'column', alignItems: 'center', gap: '12px' }}>
                    <div style={{ fontWeight: '800', fontSize: '13px', color: '#c084fc', textTransform: 'uppercase' }}>P3</div>
                    <div style={{ display: 'flex', alignItems: 'center', gap: '18px' }}>
                      <div style={{ display: 'grid', gridTemplateColumns: 'repeat(2, 1fr)', gridTemplateRows: 'repeat(2, 1fr)', gap: '8px' }}>
                        {[1, 2, 3, 4].map(btn => (
                          <button
                            key={`3-${btn}`}
                            onClick={() => toggleLED('3', btn.toString())}
                            style={{
                              width: '32px',
                              height: '32px',
                              borderRadius: '50%',
                              border: '2px solid #7c3aed',
                              background: currentActiveButtons.has(`3-${btn}`)
                                ? 'radial-gradient(circle, #c084fc, #a855f7)'
                                : '#000000',
                              cursor: 'pointer',
                              color: currentActiveButtons.has(`3-${btn}`) ? '#000000' : '#e0e0ff',
                              fontSize: '11px',
                              fontWeight: 'bold',
                              display: 'flex',
                              alignItems: 'center',
                              justifyContent: 'center',
                              boxShadow: currentActiveButtons.has(`3-${btn}`) ? '0 0 10px #c084fc' : '0 0 4px rgba(192, 132, 252, 0.3)'
                            }}
                          >
                            {btn}
                          </button>
                        ))}
                      </div>
                      <div style={{ display: 'flex', flexDirection: 'column', gap: '8px' }}>
                        {['start', 'select'].map(btn => (
                          <button
                            key={`3-${btn}`}
                            onClick={() => toggleLED('3', btn)}
                            style={{
                              width: '28px',
                              height: '28px',
                              borderRadius: '50%',
                              border: '2px solid #7c3aed',
                              background: currentActiveButtons.has(`3-${btn}`)
                                ? 'radial-gradient(circle, #c084fc, #a855f7)'
                                : '#000000',
                              cursor: 'pointer',
                              color: currentActiveButtons.has(`3-${btn}`) ? '#000000' : '#e0e0ff',
                              fontSize: '10px',
                              fontWeight: 'bold',
                              display: 'flex',
                              alignItems: 'center',
                              justifyContent: 'center',
                              boxShadow: currentActiveButtons.has(`3-${btn}`) ? '0 0 8px #c084fc' : '0 0 4px rgba(192, 132, 252, 0.3)'
                            }}
                          >
                            {btn === 'start' ? 'ST' : 'SE'}
                          </button>
                        ))}
                      </div>
                    </div>
                  </div>

                  {/* Player 4 (Top-Right) */}
                  <div style={{ gridColumn: 4, gridRow: 1, display: 'flex', flexDirection: 'column', alignItems: 'center', gap: '12px' }}>
                    <div style={{ fontWeight: '800', fontSize: '13px', color: '#7c3aed', textTransform: 'uppercase' }}>P4</div>
                    <div style={{ display: 'flex', alignItems: 'center', gap: '18px' }}>
                      <div style={{ display: 'flex', flexDirection: 'column', gap: '8px' }}>
                        {['start', 'select'].map(btn => (
                          <button
                            key={`4-${btn}`}
                            onClick={() => toggleLED('4', btn)}
                            style={{
                              width: '28px',
                              height: '28px',
                              borderRadius: '50%',
                              border: '2px solid #7c3aed',
                              background: currentActiveButtons.has(`4-${btn}`)
                                ? 'radial-gradient(circle, #7c3aed, #6b21a8)'
                                : '#000000',
                              cursor: 'pointer',
                              color: currentActiveButtons.has(`4-${btn}`) ? '#ffffff' : '#e0e0ff',
                              fontSize: '10px',
                              fontWeight: 'bold',
                              display: 'flex',
                              alignItems: 'center',
                              justifyContent: 'center',
                              boxShadow: currentActiveButtons.has(`4-${btn}`) ? '0 0 8px #7c3aed' : '0 0 4px rgba(124, 58, 237, 0.3)'
                            }}
                          >
                            {btn === 'start' ? 'ST' : 'SE'}
                          </button>
                        ))}
                      </div>
                      <div style={{ display: 'grid', gridTemplateColumns: 'repeat(2, 1fr)', gridTemplateRows: 'repeat(2, 1fr)', gap: '8px' }}>
                        {[1, 2, 3, 4].map(btn => (
                          <button
                            key={`4-${btn}`}
                            onClick={() => toggleLED('4', btn.toString())}
                            style={{
                              width: '32px',
                              height: '32px',
                              borderRadius: '50%',
                              border: '2px solid #7c3aed',
                              background: currentActiveButtons.has(`4-${btn}`)
                                ? 'radial-gradient(circle, #7c3aed, #6b21a8)'
                                : '#000000',
                              cursor: 'pointer',
                              color: currentActiveButtons.has(`4-${btn}`) ? '#ffffff' : '#e0e0ff',
                              fontSize: '11px',
                              fontWeight: 'bold',
                              display: 'flex',
                              alignItems: 'center',
                              justifyContent: 'center',
                              boxShadow: currentActiveButtons.has(`4-${btn}`) ? '0 0 10px #7c3aed' : '0 0 4px rgba(124, 58, 237, 0.3)'
                            }}
                          >
                            {btn}
                          </button>
                        ))}
                      </div>
                    </div>
                  </div>

                  {/* Center Trackball */}
                  <div style={{ gridColumn: '2 / 4', gridRow: '1 / 3', display: 'flex', justifyContent: 'center', alignItems: 'center' }}>
                    <div style={{
                      width: '80px',
                      height: '80px',
                      minWidth: '80px',
                      minHeight: '80px',
                      maxWidth: '80px',
                      maxHeight: '80px',
                      aspectRatio: '1 / 1',
                      background: 'radial-gradient(circle at 30% 30%, #a855f7, #9333ea, #7c3aed)',
                      borderRadius: '50%',
                      border: '3px solid #c084fc',
                      cursor: 'pointer',
                      display: 'flex',
                      alignItems: 'center',
                      justifyContent: 'center',
                      fontSize: '11px',
                      fontWeight: 'bold',
                      color: '#ffffff',
                      boxShadow: '0 0 12px #9333ea, inset -6px -6px 12px rgba(0, 0, 0, 0.4), inset 6px 6px 12px rgba(168, 85, 247, 0.15)',
                      flexShrink: 0,
                      flexGrow: 0
                    }}>
                      TRACK
                    </div>
                  </div>

                  {/* Player 1 (Bottom-Left) */}
                  <div style={{ gridColumn: 1, gridRow: 3, display: 'flex', flexDirection: 'column', alignItems: 'center', gap: '10px' }}>
                    <div style={{ display: 'flex', gap: '10px' }}>
                      {['start', 'select'].map(btn => (
                        <button
                          key={`1-${btn}`}
                          onClick={() => toggleLED('1', btn)}
                          style={{
                            width: '28px',
                            height: '28px',
                            borderRadius: '50%',
                            border: '2px solid #7c3aed',
                            background: currentActiveButtons.has(`1-${btn}`)
                              ? 'radial-gradient(circle, #9333ea, #7c3aed)'
                              : '#000000',
                            cursor: 'pointer',
                            color: currentActiveButtons.has(`1-${btn}`) ? '#ffffff' : '#e0e0ff',
                            fontSize: '10px',
                            fontWeight: 'bold',
                            display: 'flex',
                            alignItems: 'center',
                            justifyContent: 'center',
                            boxShadow: currentActiveButtons.has(`1-${btn}`) ? '0 0 8px #9333ea' : '0 0 4px rgba(147, 51, 234, 0.3)'
                          }}
                        >
                          {btn === 'start' ? 'ST' : 'SE'}
                        </button>
                      ))}
                    </div>
                    <div style={{ display: 'grid', gridTemplateColumns: 'repeat(4, 1fr)', gridTemplateRows: 'repeat(2, 1fr)', gap: '8px' }}>
                      {[1, 2, 3, 7, 4, 5, 6, 8].map(btn => (
                        <button
                          key={`1-${btn}`}
                          onClick={() => toggleLED('1', btn.toString())}
                          style={{
                            width: '32px',
                            height: '32px',
                            borderRadius: '50%',
                            border: '2px solid #7c3aed',
                            background: currentActiveButtons.has(`1-${btn}`)
                              ? 'radial-gradient(circle, #9333ea, #7c3aed)'
                              : '#000000',
                            cursor: 'pointer',
                            color: currentActiveButtons.has(`1-${btn}`) ? '#ffffff' : '#e0e0ff',
                            fontSize: '11px',
                            fontWeight: 'bold',
                            display: 'flex',
                            alignItems: 'center',
                            justifyContent: 'center',
                            boxShadow: currentActiveButtons.has(`1-${btn}`) ? '0 0 8px #9333ea' : '0 0 4px rgba(147, 51, 234, 0.3)'
                          }}
                        >
                          {btn}
                        </button>
                      ))}
                    </div>
                    <div style={{ fontWeight: '800', fontSize: '13px', color: '#9333ea', textTransform: 'uppercase' }}>P1</div>
                  </div>

                  {/* Player 2 (Bottom-Right) */}
                  <div style={{ gridColumn: 4, gridRow: 3, display: 'flex', flexDirection: 'column', alignItems: 'center', gap: '10px', paddingRight: '8px' }}>
                    <div style={{ display: 'flex', gap: '8px' }}>
                      {['start', 'select'].map(btn => (
                        <button
                          key={`2-${btn}`}
                          onClick={() => toggleLED('2', btn)}
                          style={{
                            width: '28px',
                            height: '28px',
                            borderRadius: '50%',
                            border: '2px solid #7c3aed',
                            background: currentActiveButtons.has(`2-${btn}`)
                              ? 'radial-gradient(circle, #a855f7, #9333ea)'
                              : '#000000',
                            cursor: 'pointer',
                            color: currentActiveButtons.has(`2-${btn}`) ? '#ffffff' : '#e0e0ff',
                            fontSize: '10px',
                            fontWeight: 'bold',
                            display: 'flex',
                            alignItems: 'center',
                            justifyContent: 'center',
                            boxShadow: currentActiveButtons.has(`2-${btn}`) ? '0 0 8px #a855f7' : '0 0 4px rgba(124, 58, 237, 0.3)'
                          }}
                        >
                          {btn === 'start' ? 'ST' : 'SE'}
                        </button>
                      ))}
                    </div>
                    <div style={{ display: 'grid', gridTemplateColumns: 'repeat(4, 1fr)', gridTemplateRows: 'repeat(2, 1fr)', gap: '6px' }}>
                      {[1, 2, 3, 7, 4, 5, 6, 8].map(btn => (
                        <button
                          key={`2-${btn}`}
                          onClick={() => toggleLED('2', btn.toString())}
                          style={{
                            width: '32px',
                            height: '32px',
                            borderRadius: '50%',
                            border: '2px solid #7c3aed',
                            background: currentActiveButtons.has(`2-${btn}`)
                              ? 'radial-gradient(circle, #a855f7, #9333ea)'
                              : '#000000',
                            cursor: 'pointer',
                            color: currentActiveButtons.has(`2-${btn}`) ? '#ffffff' : '#e0e0ff',
                            fontSize: '11px',
                            fontWeight: 'bold',
                            display: 'flex',
                            alignItems: 'center',
                            justifyContent: 'center',
                            boxShadow: currentActiveButtons.has(`2-${btn}`) ? '0 0 10px #a855f7' : '0 0 4px rgba(124, 58, 237, 0.3)'
                          }}
                        >
                          {btn}
                        </button>
                      ))}
                    </div>
                    <div style={{ fontWeight: '800', fontSize: '13px', color: '#a855f7', textTransform: 'uppercase' }}>P2</div>
                  </div>
                </div>
              </div>
            </div>

            {/* Quick Controls */}
            <div style={{
              display: 'grid',
              gridTemplateColumns: 'repeat(2, 1fr)',
              gap: '12px',
              padding: '20px',
              background: '#0f0f0f',
              borderRadius: '12px',
              border: '1px solid #9333ea'
            }}>
              <button onClick={testAllLEDs} style={{ padding: '12px', background: '#000000', border: '1px solid #7c3aed', color: '#d1d5db', borderRadius: '8px', cursor: 'pointer', fontSize: '13px', fontWeight: '600' }}>
                <span>💡</span> Test All
              </button>
              <button onClick={clearAllLEDs} style={{ padding: '12px', background: '#000000', border: '1px solid #7c3aed', color: '#d1d5db', borderRadius: '8px', cursor: 'pointer', fontSize: '13px', fontWeight: '600' }}>
                <span>🚫</span> Clear
              </button>
              <button onClick={randomPattern} style={{ padding: '12px', background: '#000000', border: '1px solid #7c3aed', color: '#d1d5db', borderRadius: '8px', cursor: 'pointer', fontSize: '13px', fontWeight: '600' }}>
                <span>🎲</span> Random
              </button>
            </div>

            {/* LED Calibration Wizard */}
            <div style={{
              padding: '16px 20px',
              background: calibrationWizard.isActive ? '#1a0a2e' : '#0f0f0f',
              borderRadius: '12px',
              border: calibrationWizard.isActive ? '2px solid #10b981' : '1px solid #9333ea',
              transition: 'all 0.2s ease'
            }}>
              <div style={{
                display: 'flex',
                alignItems: 'center',
                justifyContent: 'space-between',
                marginBottom: calibrationWizard.isActive ? '16px' : '0'
              }}>
                <span style={{ fontSize: '14px', fontWeight: '600', color: calibrationWizard.isActive ? '#10b981' : '#9333ea' }}>
                  🔧 LED Calibration Wizard
                </span>
                {!calibrationWizard.isActive ? (
                  <button
                    onClick={() => calibrationWizard.startWizard({ totalPorts: 32 })}
                    disabled={calibrationWizard.isLoading}
                    style={{
                      padding: '8px 16px',
                      background: 'linear-gradient(135deg, #10b981, #059669)',
                      border: 'none',
                      borderRadius: '6px',
                      color: '#fff',
                      fontSize: '12px',
                      fontWeight: '600',
                      cursor: calibrationWizard.isLoading ? 'wait' : 'pointer',
                      opacity: calibrationWizard.isLoading ? 0.7 : 1
                    }}
                  >
                    🚀 Start Calibration
                  </button>
                ) : (
                  <div style={{ display: 'flex', gap: '8px' }}>
                    <button
                      onClick={() => calibrationWizard.skipPort()}
                      disabled={calibrationWizard.isLoading}
                      style={{
                        padding: '6px 12px',
                        background: '#7c3aed',
                        border: 'none',
                        borderRadius: '6px',
                        color: '#fff',
                        fontSize: '11px',
                        fontWeight: '600',
                        cursor: calibrationWizard.isLoading ? 'wait' : 'pointer'
                      }}
                    >
                      ⏭️ Skip
                    </button>
                    <button
                      onClick={() => calibrationWizard.finishWizard()}
                      style={{
                        padding: '6px 12px',
                        background: '#059669',
                        border: 'none',
                        borderRadius: '6px',
                        color: '#fff',
                        fontSize: '11px',
                        fontWeight: '600',
                        cursor: 'pointer'
                      }}
                    >
                      ✅ Finish
                    </button>
                    <button
                      onClick={() => calibrationWizard.cancelWizard()}
                      style={{
                        padding: '6px 12px',
                        background: '#dc2626',
                        border: 'none',
                        borderRadius: '6px',
                        color: '#fff',
                        fontSize: '11px',
                        fontWeight: '600',
                        cursor: 'pointer'
                      }}
                    >
                      ❌ Cancel
                    </button>
                  </div>
                )}
              </div>

              {/* Active Calibration UI */}
              {calibrationWizard.isActive && (
                <div style={{ display: 'flex', flexDirection: 'column', gap: '12px' }}>
                  {/* Progress Bar */}
                  <div style={{ display: 'flex', alignItems: 'center', gap: '12px' }}>
                    <div style={{
                      flex: 1,
                      height: '8px',
                      background: '#1a1a2e',
                      borderRadius: '4px',
                      overflow: 'hidden'
                    }}>
                      <div style={{
                        width: `${calibrationWizard.progressPercent}%`,
                        height: '100%',
                        background: 'linear-gradient(90deg, #10b981, #34d399)',
                        transition: 'width 0.3s ease'
                      }} />
                    </div>
                    <span style={{ fontSize: '12px', color: '#d1d5db', minWidth: '60px' }}>
                      {calibrationWizard.currentPort} / {calibrationWizard.totalPorts}
                    </span>
                  </div>

                  {/* Instructions */}
                  <div style={{
                    padding: '12px',
                    background: 'rgba(16, 185, 129, 0.1)',
                    borderRadius: '8px',
                    border: '1px solid rgba(16, 185, 129, 0.3)'
                  }}>
                    <div style={{ fontSize: '13px', color: '#10b981', fontWeight: '600', marginBottom: '6px' }}>
                      🔦 Port {calibrationWizard.currentPort} is blinking
                    </div>
                    <div style={{ fontSize: '12px', color: '#d1d5db' }}>
                      Look at your cabinet - which button is lit up? Click it above!
                    </div>
                  </div>

                  {/* Stats */}
                  <div style={{ display: 'flex', gap: '16px', fontSize: '11px', color: '#888' }}>
                    <span>✅ Mapped: {calibrationWizard.mappedCount}</span>
                    <span>⏭️ Skipped: {calibrationWizard.skippedCount}</span>
                  </div>
                </div>
              )}
            </div>

            {/* LED Brightness Control */}
            <div style={{
              padding: '16px 20px',
              background: '#0f0f0f',
              borderRadius: '12px',
              border: '1px solid #9333ea'
            }}>
              <div style={{
                display: 'flex',
                alignItems: 'center',
                justifyContent: 'space-between',
                marginBottom: '12px'
              }}>
                <span style={{ fontSize: '14px', fontWeight: '600', color: '#9333ea' }}>
                  💡 LED Brightness
                </span>
                <span style={{ fontSize: '13px', color: '#d1d5db' }}>
                  {ledBrightness}%
                </span>
              </div>
              <div style={{ position: 'relative' }}>
                <input
                  type="range"
                  min="10"
                  max="100"
                  value={ledBrightness}
                  onChange={(e) => {
                    const newBrightness = parseInt(e.target.value, 10)
                    handleBrightnessChange(Number.isNaN(newBrightness) ? ledBrightness : newBrightness)
                  }}
                  style={{
                    width: '100%',
                    height: '6px',
                    borderRadius: '3px',
                    background: `linear-gradient(to right, #7c3aed 0%, #9333ea ${ledBrightness}%, #333333 ${ledBrightness}%, #333333 100%)`,
                    outline: 'none',
                    appearance: 'none',
                    WebkitAppearance: 'none'
                  }}
                />
                <style>
                  {`
                    input[type="range"]::-webkit-slider-thumb {
                      appearance: none;
                      width: 18px;
                      height: 18px;
                      border-radius: 50%;
                      background: #9333ea;
                      border: 2px solid #ffffff;
                      cursor: pointer;
                      box-shadow: 0 0 8px rgba(147, 51, 234, 0.4);
                    }
                    input[type="range"]::-moz-range-thumb {
                      width: 18px;
                      height: 18px;
                      border-radius: 50%;
                      background: #9333ea;
                      border: 2px solid #ffffff;
                      cursor: pointer;
                      box-shadow: 0 0 8px rgba(147, 51, 234, 0.4);
                    }
                  `}
                </style>
              </div>
            </div>

            {/* LED Stats */}
            <div style={{
              display: 'flex',
              justifyContent: 'space-around',
              padding: '16px',
              background: '#0f0f0f',
              borderRadius: '8px',
              fontSize: '12px',
              border: '1px solid #9333ea'
            }}>
              <div style={{ textAlign: 'center' }}>
                <span style={{ display: 'block', fontSize: '16px', fontWeight: '700', color: '#9333ea' }}>{currentActiveButtons.size}</span>
                <span style={{ color: '#d1d5db' }}>Active LEDs</span>
              </div>
              <div style={{ textAlign: 'center' }}>
                <span style={{ display: 'block', fontSize: '16px', fontWeight: '700', color: '#9333ea' }}>96</span>
                <span style={{ color: '#d1d5db' }}>Total LEDs</span>
              </div>
              <div style={{ textAlign: 'center' }}>
                <span style={{ display: 'block', fontSize: '16px', fontWeight: '700', color: '#9333ea' }}>12ms</span>
                <span style={{ color: '#d1d5db' }}>Response</span>
              </div>
            </div>
          </div>

          {/* Right: Mode Content */}
          <div style={{
            background: '#0f0f0f',
            border: '1px solid #9333ea',
            borderRadius: '16px',
            overflow: 'hidden',
            display: 'flex',
            flexDirection: 'column',
            maxHeight: '70vh'
          }}>
            {/* Game Profiles Mode */}
            {activeMode === 'profiles' && (
              <div style={{ padding: '24px', overflowY: 'auto', display: 'flex', flexDirection: 'column', gap: '20px' }}>
                {/* Live LED Preview Panel */}
                <div style={{
                  padding: '20px',
                  background: '#000000',
                  borderRadius: '12px',
                  border: '1px solid #7c3aed',
                  marginBottom: '8px'
                }}>
                  <div style={{
                    fontSize: '16px',
                    fontWeight: '700',
                    color: '#9333ea',
                    marginBottom: '16px',
                    display: 'flex',
                    alignItems: 'center',
                    gap: '10px'
                  }}>
                    <span></span>
                    <span>Live LED Preview</span>
                  </div>
                  <ArcadePanelPreview
                    mappingForm={mappingForm}
                    activeButtons={currentActiveButtons}
                    playerCount={cabinetPlayerCount}
                    showLabels={true}
                    onButtonClick={(player, button) => {
                      // Phase 6.5: Unified wizard-aware click handler
                      const buttonId = `p${player}.button${button}`
                      if (wizardState.isActive && activeMode === 'calibration') {
                        // Route to hoisted wizard mapping function
                        handleWizardMapButton(buttonId)
                      } else {
                        // Normal LED toggle
                        toggleLED(player, button)
                      }
                    }}
                  />
                </div>

                <div style={{
                  padding: '24px',
                  background: '#000000',
                  borderRadius: '12px',
                  border: '1px solid #7c3aed',
                  display: 'flex',
                  flexDirection: 'column',
                  gap: '16px'
                }}>
                  <div style={{
                    fontSize: '18px',
                    fontWeight: '700',
                    color: '#9333ea',
                    display: 'flex',
                    alignItems: 'center',
                    gap: '10px'
                  }}>
                    <span>[LG]</span>
                    <span>LaunchBox Games</span>
                  </div>
                  <div style={{ display: 'flex', gap: '12px', flexWrap: 'wrap' }}>
                    <input
                      type="text"
                      value={gameSearchTerm}
                      onChange={(e) => setGameSearchTerm(e.target.value)}
                      onKeyDown={handleGameSearchKeyDown}
                      placeholder="Search by game title or leave blank to list recent cache"
                      style={{
                        flex: '1 1 260px',
                        padding: '12px',
                        background: '#0a0a0a',
                        border: '1px solid #4c1d95',
                        borderRadius: '8px',
                        color: '#ffffff',
                        fontSize: '13px'
                      }}
                    />
                    <button
                      onClick={handleSearchGames}
                      disabled={isLoadingGames}
                      style={{
                        padding: '12px 18px',
                        background: isLoadingGames ? '#312e81' : '#9333ea',
                        border: 'none',
                        borderRadius: '8px',
                        color: '#ffffff',
                        fontWeight: '600',
                        cursor: isLoadingGames ? 'not-allowed' : 'pointer',
                        opacity: isLoadingGames ? 0.6 : 1
                      }}
                    >
                      {isLoadingGames ? 'Searching…' : 'Search'}
                    </button>
                    <button
                      onClick={() => loadGameResults('')}
                      disabled={isLoadingGames}
                      style={{
                        padding: '12px 18px',
                        background: '#111827',
                        border: '1px solid #4b5563',
                        borderRadius: '8px',
                        color: '#e5e7eb',
                        fontWeight: '600',
                        cursor: isLoadingGames ? 'not-allowed' : 'pointer',
                        opacity: isLoadingGames ? 0.6 : 1
                      }}
                    >
                      Reset
                    </button>
                  </div>
                  <div style={{ display: 'flex', flexDirection: 'column', gap: '10px', maxHeight: '260px', overflowY: 'auto' }}>
                    {isLoadingGames ? (
                      <div style={{ color: '#9ca3af', fontSize: '13px' }}>Loading LaunchBox games…</div>
                    ) : gameResults.length > 0 ? (
                      gameResults.map(game => {
                        const isActive = selectedGame?.id === game.id
                        const assignedName = game.assigned_profile?.profile_name
                        return (
                          <div
                            key={game.id}
                            style={{
                              border: `1px solid ${isActive ? '#9333ea' : '#1f2937'}`,
                              borderRadius: '10px',
                              padding: '14px',
                              background: '#050505',
                              display: 'flex',
                              justifyContent: 'space-between',
                              gap: '12px',
                              flexWrap: 'wrap'
                            }}
                          >
                            <div>
                              <div style={{ fontSize: '15px', fontWeight: '600', color: '#f3f4f6' }}>{game.title || 'Unknown Game'}</div>
                              <div style={{ fontSize: '12px', color: '#9ca3af' }}>
                                {game.platform || 'Unknown Platform'}
                                {' • '}
                                {assignedName ? `LED Profile: ${assignedName}` : 'No LED profile assigned'}
                              </div>
                            </div>
                            <button
                              onClick={() => handleSelectGame(game)}
                              disabled={isActive}
                              style={{
                                padding: '10px 16px',
                                borderRadius: '8px',
                                border: '1px solid #7c3aed',
                                background: isActive ? '#1f2937' : '#000000',
                                color: isActive ? '#6b7280' : '#d1d5db',
                                fontSize: '12px',
                                fontWeight: '600',
                                cursor: isActive ? 'default' : 'pointer'
                              }}
                            >
                              {isActive ? 'Selected' : 'Select'}
                            </button>
                          </div>
                        )
                      })
                    ) : (
                      <div style={{ color: '#9ca3af', fontSize: '13px' }}>
                        {gameSearchTerm.trim() ? 'No LaunchBox games match that search.' : 'No LaunchBox games loaded yet.'}
                      </div>
                    )}
                  </div>

                </div>

                {selectedGame && (
                  <div style={{
                    padding: '24px',
                    background: '#000000',
                    borderRadius: '12px',
                    border: '1px solid #7c3aed',
                    display: 'flex',
                    flexDirection: 'column',
                    gap: '16px'
                  }}>
                    <div style={{
                      fontSize: '18px',
                      fontWeight: '700',
                      color: '#9333ea',
                      display: 'flex',
                      alignItems: 'center',
                      gap: '10px'
                    }}>
                      <span>[SG]</span>
                      <span>Selected Game</span>
                    </div>
                    <div style={{ fontSize: '14px', color: '#f3f4f6' }}>{selectedGame.title}</div>
                    <div style={{ fontSize: '12px', color: '#9ca3af' }}>
                      Platform: {selectedGame.platform || 'Unknown'} • Current profile: {selectedGameBinding?.profile_name || 'None'}
                    </div>
                    <div>
                      <label style={{ display: 'block', fontSize: '12px', color: '#9ca3af', marginBottom: '6px' }}>Assign LED Profile</label>
                      <select
                        value={selectedGameProfileName}
                        onChange={(e) => setSelectedGameProfileName(e.target.value)}
                        disabled={isLoadingBinding}
                        style={{
                          width: '100%',
                          padding: '12px',
                          background: '#0a0a0a',
                          border: '1px solid #4b5563',
                          borderRadius: '8px',
                          color: '#ffffff',
                          fontSize: '13px'
                        }}
                      >
                        <option value="">-- Select a Profile --</option>
                        {availableProfiles.map(profile => (
                          <option key={profile.value} value={profile.value}>
                            {profile.label}
                          </option>
                        ))}
                      </select>
                    </div>
                    <div style={{ display: 'flex', flexWrap: 'wrap', gap: '10px' }}>
                      <button
                        onClick={handlePreviewGameProfile}
                        disabled={!canPreviewBinding}
                        style={{
                          flex: '1 1 160px',
                          padding: '12px',
                          borderRadius: '8px',
                          border: '1px solid #10b981',
                          background: canPreviewBinding ? '#000000' : '#1b1b1b',
                          color: canPreviewBinding ? '#10b981' : '#6b7280',
                          fontSize: '13px',
                          fontWeight: '600',
                          cursor: canPreviewBinding ? 'pointer' : 'not-allowed'
                        }}
                      >
                        {isPreviewingBinding ? 'Previewing…' : 'Preview Binding'}
                      </button>
                      <button
                        onClick={handleApplyGameProfile}
                        disabled={!canApplyBinding}
                        style={{
                          flex: '1 1 160px',
                          padding: '12px',
                          borderRadius: '8px',
                          border: 'none',
                          background: canApplyBinding ? 'linear-gradient(135deg, #9333ea, #7c3aed)' : '#2d1b3b',
                          color: '#ffffff',
                          fontSize: '13px',
                          fontWeight: '600',
                          cursor: canApplyBinding ? 'pointer' : 'not-allowed'
                        }}
                      >
                        {isApplyingBinding ? 'Applying…' : 'Apply to Game'}
                      </button>
                      <button
                        onClick={handleClearGameProfile}
                        disabled={!canClearBinding}
                        style={{
                          flex: '1 1 160px',
                          padding: '12px',
                          borderRadius: '8px',
                          border: '1px solid #ef4444',
                          background: canClearBinding ? '#1b0b0b' : '#1f1f1f',
                          color: canClearBinding ? '#ef4444' : '#6b7280',
                          fontSize: '13px',
                          fontWeight: '600',
                          cursor: canClearBinding ? 'pointer' : 'not-allowed'
                        }}
                      >
                        {isClearingBinding ? 'Clearing…' : 'Clear Binding'}
                      </button>
                    </div>
                    {bindingPreview && (
                      <div style={{
                        marginTop: '12px',
                        padding: '16px',
                        background: '#050505',
                        borderRadius: '8px',
                        border: '1px solid #1f2937'
                      }}>
                        <div style={{ fontSize: '13px', color: '#d1d5db', marginBottom: '6px' }}>Binding Preview</div>
                        <div style={{ fontSize: '12px', color: '#9ca3af', marginBottom: '8px' }}>
                          Target file: <code style={{ color: '#a7f3d0' }}>{bindingPreview.target_file}</code>
                        </div>
                        <div style={{ fontSize: '12px', color: '#9ca3af', marginBottom: '8px', display: 'flex', gap: '12px', flexWrap: 'wrap' }}>
                          <span>Scope: {bindingPreview.scope}</span>
                          <span>Total channels: {bindingPreview.total_channels}</span>
                          <span>Missing buttons: {bindingPreview.missing_buttons?.length ? bindingPreview.missing_buttons.join(', ') : 'None'}</span>
                        </div>
                        <div style={{
                          marginBottom: '10px',
                          padding: '10px',
                          background: '#0a0a0a',
                          borderRadius: '6px',
                          border: '1px solid #1f2937'
                        }}>
                          <div style={{ fontSize: '12px', color: '#e5e7eb', marginBottom: '4px' }}>Diff</div>
                          <pre style={{ margin: 0, maxHeight: '120px', overflow: 'auto', fontSize: '12px', color: '#9ca3af' }}>{bindingPreview.diff}</pre>
                        </div>
                        <div style={{
                          padding: '10px',
                          background: '#0a0a0a',
                          borderRadius: '6px',
                          border: '1px solid #1f2937'
                        }}>
                          <div style={{ fontSize: '12px', color: '#e5e7eb', marginBottom: '4px' }}>Resolved Buttons</div>
                          {(bindingPreview.resolved_buttons || []).slice(0, 8).map((button, index) => {
                            const channels = button.channels || []
                            const channelSummary = channels.length
                              ? channels.map(channel => `${channel.device_id}#${channel.channel_index}`).join(', ')
                              : 'No hardware channel resolved'
                            return (
                              <div key={`${button.logical_button}-${index}`} style={{ fontSize: '12px', color: '#9ca3af' }}>
                                {button.logical_button} → {channelSummary}
                              </div>
                            )
                          })}
                          {bindingPreview.resolved_buttons && bindingPreview.resolved_buttons.length > 8 && (
                            <div style={{ fontSize: '12px', color: '#6b7280', marginTop: '4px' }}>
                              +{bindingPreview.resolved_buttons.length - 8} more channels
                            </div>
                          )}
                        </div>
                      </div>
                    )}
                    <div style={{ fontSize: '12px', color: '#6b7280' }}>
                      Assignments are stored under <code>configs/ledblinky/game_profiles.json</code> so LaunchBox sessions stay in sync.
                    </div>
                  </div>
                )}

                <div style={{
                  padding: '24px',
                  background: '#000000',
                  borderRadius: '12px',
                  border: '1px solid #7c3aed',
                  display: 'flex',
                  flexDirection: 'column',
                  gap: '16px'
                }}>
                  <div style={{
                    fontSize: '18px',
                    fontWeight: '700',
                    color: '#9333ea',
                    display: 'flex',
                    alignItems: 'center',
                    gap: '10px'
                  }}>
                    <span>[GP]</span>
                    <span>Game Profile Library</span>
                  </div>
                  <div style={{
                    display: 'flex',
                    flexWrap: 'wrap',
                    gap: '12px',
                    alignItems: 'center'
                  }}>
                    <input
                      type="text"
                      value={profileSearchTerm}
                      onChange={(e) => setProfileSearchTerm(e.target.value)}
                      placeholder="Search by game, filename, or scope"
                      style={{
                        flex: '1 1 300px',
                        minWidth: '200px',
                        padding: '12px',
                        background: '#0a0a0a',
                        border: '1px solid #4c1d95',
                        borderRadius: '8px',
                        color: '#ffffff',
                        fontSize: '13px'
                      }}
                    />
                    <button
                      onClick={refreshProfiles}
                      disabled={isLoadingProfiles}
                      style={{
                        padding: '12px 18px',
                        background: isLoadingProfiles ? '#312e81' : '#9333ea',
                        border: 'none',
                        borderRadius: '8px',
                        color: '#ffffff',
                        fontWeight: '600',
                        cursor: isLoadingProfiles ? 'not-allowed' : 'pointer',
                        opacity: isLoadingProfiles ? 0.6 : 1
                      }}
                    >
                      {isLoadingProfiles ? 'Refreshing…' : 'Refresh'}
                    </button>
                  </div>
                  <div style={{ display: 'flex', flexDirection: 'column', gap: '12px' }}>
                    {filteredProfiles.length > 0 ? (
                      filteredProfiles.map(profile => {
                        const meta = profile.metadata || {}
                        const isActive = selectedProfile === profile.value
                        const summaryParts = [
                          meta.scope ? `Scope: ${meta.scope}` : null,
                          Array.isArray(meta.mapping_keys) ? `${meta.mapping_keys.length} keys` : null,
                          meta.filename ? `File: ${meta.filename}` : null
                        ].filter(Boolean)
                        const canApplyThisProfile = isActive && canApplyLibraryProfile
                        return (
                          <div
                            key={profile.value}
                            style={{
                              border: `1px solid ${isActive ? '#10b981' : '#4b5563'}`,
                              borderRadius: '10px',
                              padding: '16px',
                              background: '#050505'
                            }}
                          >
                            <div style={{
                              display: 'flex',
                              justifyContent: 'space-between',
                              flexWrap: 'wrap',
                              gap: '12px'
                            }}>
                              <div>
                                <div style={{
                                  fontSize: '15px',
                                  fontWeight: '600',
                                  color: '#f3f4f6',
                                  marginBottom: '4px'
                                }}>
                                  {meta.game || meta.profile_name || profile.label}
                                </div>
                                <div style={{ fontSize: '12px', color: '#9ca3af' }}>
                                  {summaryParts.length > 0 ? summaryParts.join(' • ') : 'Unscoped profile'}
                                </div>
                              </div>
                              <div style={{ display: 'flex', gap: '8px', flexWrap: 'wrap' }}>
                                <button
                                  onClick={() => previewProfileFromLibrary(profile.value)}
                                  style={{
                                    padding: '10px 14px',
                                    borderRadius: '6px',
                                    border: '1px solid #9333ea',
                                    background: '#000000',
                                    color: '#9333ea',
                                    fontSize: '12px',
                                    fontWeight: '600',
                                    cursor: 'pointer'
                                  }}
                                >
                                  Preview
                                </button>
                                <button
                                  onClick={() => applyProfileFromLibrary(profile.value)}
                                  disabled={!canApplyThisProfile}
                                  style={{
                                    padding: '10px 14px',
                                    borderRadius: '6px',
                                    border: 'none',
                                    background: canApplyThisProfile ? '#10b981' : '#374151',
                                    color: canApplyThisProfile ? '#051b16' : '#9ca3af',
                                    fontSize: '12px',
                                    fontWeight: '600',
                                    cursor: canApplyThisProfile ? 'pointer' : 'not-allowed'
                                  }}
                                >
                                  Apply
                                </button>
                                <button
                                  onClick={() => editProfileInDesigner(profile.value)}
                                  style={{
                                    padding: '10px 14px',
                                    borderRadius: '6px',
                                    border: '1px solid #4b5563',
                                    background: '#111111',
                                    color: '#d1d5db',
                                    fontSize: '12px',
                                    fontWeight: '600',
                                    cursor: 'pointer'
                                  }}
                                >
                                  Edit in Designer
                                </button>
                              </div>
                            </div>
                          </div>
                        )
                      })
                    ) : (
                      <div style={{ color: '#9ca3af', fontSize: '13px' }}>
                        {profileSearchTerm.trim()
                          ? 'No profiles match your search.'
                          : 'No LED profiles found in configs/ledblinky/profiles.'}
                      </div>
                    )}
                  </div>
                  <div style={{ fontSize: '12px', color: '#6b7280' }}>
                    Preview resolves Chuck’s logical buttons to LED channels. Apply remains disabled until the latest preview matches the selected profile.
                  </div>
                </div>

                {libraryPreviewReady && profilePreview && (
                  <div style={{
                    padding: '24px',
                    background: '#000000',
                    borderRadius: '12px',
                    border: '1px solid #10b981'
                  }}>
                    <div style={{
                      fontSize: '16px',
                      fontWeight: '700',
                      color: '#10b981',
                      marginBottom: '12px',
                      display: 'flex',
                      alignItems: 'center',
                      gap: '10px'
                    }}>
                      <span>[PV]</span>
                      <span>Preview Summary: {selectedProfileDisplayName}</span>
                    </div>
                    <div style={{ fontSize: '13px', color: '#d1d5db', marginBottom: '8px' }}>
                      Target file: <code style={{ color: '#a7f3d0' }}>{profilePreview.target_file}</code>
                    </div>
                    <div style={{ fontSize: '12px', color: '#9ca3af', display: 'flex', flexWrap: 'wrap', gap: '12px', marginBottom: '12px' }}>
                      <span>Scope: {profilePreview.scope}</span>
                      {profilePreview.game && <span>Game: {profilePreview.game}</span>}
                      <span>Total channels: {profilePreview.total_channels}</span>
                      <span>Missing buttons: {profilePreview.missing_buttons.length ? profilePreview.missing_buttons.join(', ') : 'None'}</span>
                    </div>
                    <div style={{
                      marginBottom: '12px',
                      padding: '12px',
                      background: '#050505',
                      borderRadius: '8px',
                      border: '1px solid #1f2937'
                    }}>
                      <div style={{ fontSize: '12px', color: '#e5e7eb', marginBottom: '6px' }}>Diff</div>
                      <pre style={{
                        margin: 0,
                        maxHeight: '140px',
                        overflow: 'auto',
                        fontSize: '12px',
                        color: '#9ca3af'
                      }}>
                        {profilePreview.diff}
                      </pre>
                    </div>
                    <div style={{
                      padding: '12px',
                      background: '#050505',
                      borderRadius: '8px',
                      border: '1px solid #1f2937'
                    }}>
                      <div style={{ fontSize: '12px', color: '#e5e7eb', marginBottom: '8px' }}>Resolved Buttons</div>
                      {(profilePreview.resolved_buttons || []).slice(0, 8).map((button, index) => {
                        const channels = button.channels || []
                        const channelSummary = channels.length
                          ? channels.map(channel => `${channel.device_id}#${channel.channel_index}`).join(', ')
                          : 'No hardware channel resolved'
                        return (
                          <div key={`${button.logical_button}-${index}`} style={{ fontSize: '12px', color: '#9ca3af' }}>
                            {button.logical_button} → {channelSummary}
                          </div>
                        )
                      })}
                      {profilePreview.resolved_buttons && profilePreview.resolved_buttons.length > 8 && (
                        <div style={{ fontSize: '12px', color: '#6b7280', marginTop: '4px' }}>
                          +{profilePreview.resolved_buttons.length - 8} more channels
                        </div>
                      )}
                    </div>
                  </div>
                )}
              </div>
            )}

            {activeMode === 'layout' && (
              <div style={{ padding: '24px', overflowY: 'auto' }}>
                <div style={{
                  padding: '24px',
                  background: '#000000',
                  borderRadius: '12px',
                  marginBottom: '20px',
                  border: '1px solid #7c3aed'
                }}>
                  <div style={{
                    fontSize: '18px',
                    fontWeight: '700',
                    color: '#9333ea',
                    marginBottom: '20px',
                    display: 'flex',
                    alignItems: 'center',
                    gap: '10px'
                  }}>
                    <span>dY"�</span>
                    <span>LED Layout & Calibration</span>
                  </div>

                  <div style={{
                    display: 'grid',
                    gridTemplateColumns: 'repeat(auto-fit, minmax(200px, 1fr))',
                    gap: '12px',
                    fontSize: '12px',
                    color: '#d1d5db',
                    marginBottom: '16px'
                  }}>
                    <div>Target file: <code style={{ color: '#a78bfa' }}>{channelState.target_file || 'configs/ledblinky/led_channels.json'}</code></div>
                    <div>Total mapped: <strong>{channelState.total_channels ?? 0}</strong></div>
                    <div>Unmapped buttons: <strong>{Array.isArray(channelState.unmapped) ? channelState.unmapped.length : 0}</strong></div>
                    <div>Unknown entries: <strong>{Array.isArray(channelState.unknown_logical) ? channelState.unknown_logical.length : 0}</strong></div>
                  </div>

                  <div style={{ display: 'flex', gap: '10px', flexWrap: 'wrap', marginBottom: '16px' }}>
                    <button
                      onClick={startCalibrationSession}
                      disabled={isStartingCalibration}
                      style={{
                        padding: '12px 18px',
                        borderRadius: '8px',
                        border: '1px solid #10b981',
                        background: '#051b16',
                        color: '#10b981',
                        fontWeight: '600',
                        cursor: isStartingCalibration ? 'not-allowed' : 'pointer',
                        opacity: isStartingCalibration ? 0.6 : 1
                      }}>
                      {isStartingCalibration ? 'Starting...' : 'Start Calibration'}
                    </button>
                    <button
                      onClick={flashSelectedChannel}
                      disabled={!calibrationToken || !channelSelection.logicalButton || isFlashingChannel}
                      style={{
                        padding: '12px 18px',
                        borderRadius: '8px',
                        border: '1px solid #9333ea',
                        background: '#111111',
                        color: '#d1d5db',
                        fontWeight: '600',
                        cursor: (!calibrationToken || isFlashingChannel) ? 'not-allowed' : 'pointer',
                        opacity: (!calibrationToken || isFlashingChannel) ? 0.5 : 1
                      }}>
                      {isFlashingChannel ? 'Flashing...' : 'Flash Selected'}
                    </button>
                    <button
                      onClick={() => stopCalibrationSession()}
                      disabled={!calibrationToken || isStoppingCalibration}
                      style={{
                        padding: '12px 18px',
                        borderRadius: '8px',
                        border: '1px solid #ef4444',
                        background: '#2c0505',
                        color: '#fca5a5',
                        fontWeight: '600',
                        cursor: !calibrationToken || isStoppingCalibration ? 'not-allowed' : 'pointer',
                        opacity: !calibrationToken || isStoppingCalibration ? 0.5 : 1
                      }}>
                      {isStoppingCalibration ? 'Stopping...' : 'Stop Calibration'}
                    </button>
                  </div>
                  <div style={{ fontSize: '12px', color: '#9ca3af', marginBottom: '16px' }}>
                    {calibrationToken
                      ? <>Active token: <code style={{ color: '#a78bfa' }}>{calibrationToken}</code></>
                      : 'Calibration mode inactive.'}
                  </div>

                  {isLoadingChannels ? (
                    <div style={{ color: '#9ca3af', fontSize: '13px', marginBottom: '16px' }}>Loading wiring map...</div>
                  ) : (
                    <div style={{
                      background: '#050505',
                      border: '1px solid #1f2937',
                      borderRadius: '8px',
                      padding: '12px',
                      marginBottom: '16px',
                      maxHeight: '200px',
                      overflowY: 'auto',
                      fontSize: '12px'
                    }}>
                      {channelEntries.length ? channelEntries.map(([logicalButton, entry]) => {
                        const mapping = entry || {}
                        const isMissing = Array.isArray(channelState.unmapped) && channelState.unmapped.includes(logicalButton)
                        const isUnknown = Array.isArray(channelState.unknown_logical) && channelState.unknown_logical.includes(logicalButton)
                        const deviceId = mapping.device_id || mapping.deviceId || '—'
                        const channelValue = mapping.channel || mapping.channel_index || '—'
                        const color = isMissing ? '#f59e0b' : isUnknown ? '#ef4444' : '#d1d5db'
                        return (
                          <div key={logicalButton} style={{
                            display: 'flex',
                            justifyContent: 'space-between',
                            marginBottom: '4px',
                            color
                          }}>
                            <span>{logicalButton}</span>
                            <span style={{ fontFamily: 'monospace' }}>{deviceId} #{channelValue}</span>
                          </div>
                        )
                      }) : (
                        <div style={{ color: '#6b7280' }}>No LED channels stored yet. Run a calibration to seed the file.</div>
                      )}
                    </div>
                  )}

                  <div style={{
                    display: 'grid',
                    gridTemplateColumns: 'repeat(auto-fit, minmax(200px, 1fr))',
                    gap: '12px',
                    marginBottom: '16px'
                  }}>
                    <div>
                      <label style={{ fontSize: '12px', color: '#9ca3af', marginBottom: '6px', display: 'block' }}>Logical Button</label>
                      <select
                        value={channelSelection.logicalButton}
                        onChange={(e) => handleSelectChannel(e.target.value)}
                        style={{
                          width: '100%',
                          padding: '10px',
                          background: '#0a0a0a',
                          borderRadius: '8px',
                          border: '1px solid #7c3aed',
                          color: '#ffffff',
                          fontSize: '13px'
                        }}>
                        <option value="">-- Select --</option>
                        {channelOptions.map((option) => (
                          <option key={option} value={option}>{option}</option>
                        ))}
                      </select>
                    </div>
                    <div>
                      <label style={{ fontSize: '12px', color: '#9ca3af', marginBottom: '6px', display: 'block' }}>Device ID</label>
                      <input
                        value={channelSelection.deviceId}
                        onChange={(e) => handleChannelFieldChange('deviceId', e.target.value)}
                        placeholder="e.g. 0x045e:0x028e"
                        style={{
                          width: '100%',
                          padding: '10px',
                          background: '#0a0a0a',
                          borderRadius: '8px',
                          border: '1px solid #7c3aed',
                          color: '#ffffff',
                          fontSize: '13px'
                        }}
                      />
                    </div>
                    <div>
                      <label style={{ fontSize: '12px', color: '#9ca3af', marginBottom: '6px', display: 'block' }}>Channel #</label>
                      <input
                        type="number"
                        min={1}
                        value={channelSelection.channel}
                        onChange={(e) => handleChannelFieldChange('channel', e.target.value)}
                        placeholder="1"
                        style={{
                          width: '100%',
                          padding: '10px',
                          background: '#0a0a0a',
                          borderRadius: '8px',
                          border: '1px solid #7c3aed',
                          color: '#ffffff',
                          fontSize: '13px'
                        }}
                      />
                    </div>
                  </div>

                  <div style={{ display: 'flex', gap: '12px', flexWrap: 'wrap', marginBottom: '16px' }}>
                    <button
                      onClick={previewChannelUpdate}
                      disabled={isChannelPreviewing || !channelSelection.logicalButton}
                      style={{
                        padding: '12px 18px',
                        background: '#111111',
                        borderRadius: '8px',
                        border: '1px solid #7c3aed',
                        color: '#d1d5db',
                        cursor: isChannelPreviewing ? 'not-allowed' : 'pointer',
                        opacity: isChannelPreviewing ? 0.6 : 1,
                        fontWeight: 600
                      }}>
                      {isChannelPreviewing ? 'Previewing...' : 'Preview Wiring Change'}
                    </button>
                    <button
                      onClick={applyChannelUpdate}
                      disabled={isChannelApplying || !channelSelection.logicalButton}
                      style={{
                        padding: '12px 18px',
                        background: '#9333ea',
                        borderRadius: '8px',
                        border: '1px solid #7c3aed',
                        color: '#ffffff',
                        cursor: isChannelApplying ? 'not-allowed' : 'pointer',
                        opacity: isChannelApplying ? 0.6 : 1,
                        fontWeight: 600
                      }}>
                      {isChannelApplying ? 'Applying...' : 'Apply Wiring + Backup'}
                    </button>
                    <button
                      onClick={removeChannelMapping}
                      disabled={isDeletingChannel || !channelSelection.logicalButton}
                      style={{
                        padding: '12px 18px',
                        background: '#2c0505',
                        borderRadius: '8px',
                        border: '1px solid #ef4444',
                        color: '#f87171',
                        cursor: isDeletingChannel ? 'not-allowed' : 'pointer',
                        opacity: isDeletingChannel ? 0.5 : 1,
                        fontWeight: 600
                      }}>
                      {isDeletingChannel ? 'Deleting...' : 'Delete Mapping'}
                    </button>
                  </div>

                  {channelPreview && (
                    <div style={{
                      background: '#050505',
                      border: '1px solid #1f2937',
                      borderRadius: '8px',
                      padding: '12px'
                    }}>
                      <div style={{ fontSize: '13px', color: '#d1d5db', marginBottom: '6px' }}>
                        Target: <code style={{ color: '#a78bfa' }}>{channelPreview.target_file}</code>
                      </div>
                      <div style={{ fontSize: '12px', color: '#9ca3af', marginBottom: '8px', display: 'flex', gap: '12px', flexWrap: 'wrap' }}>
                        <span>Status: {channelPreview.has_changes ? 'Changes detected' : 'No diff'}</span>
                        <span>Total mapped: {channelPreview.total_channels}</span>
                        <span>Unmapped after preview: {Array.isArray(channelPreview.unmapped) ? channelPreview.unmapped.length : 0}</span>
                      </div>
                      <div style={{ fontSize: '12px', color: '#9ca3af', marginBottom: '6px' }}>Diff</div>
                      <pre style={{
                        background: '#000000',
                        borderRadius: '6px',
                        border: '1px solid #1f2937',
                        padding: '10px',
                        maxHeight: '140px',
                        overflowY: 'auto',
                        fontSize: '11px',
                        color: '#d1d5db'
                      }}>{channelPreview.diff}</pre>
                      {(Array.isArray(channelPreview.unmapped) && channelPreview.unmapped.length > 0) && (
                        <div style={{ fontSize: '12px', color: '#fbbf24', marginTop: '8px' }}>
                          Unmapped buttons: {channelPreview.unmapped.join(', ')}
                        </div>
                      )}
                      {(Array.isArray(channelPreview.unknown_logical) && channelPreview.unknown_logical.length > 0) && (
                        <div style={{ fontSize: '12px', color: '#f87171', marginTop: '4px' }}>
                          Unknown entries: {channelPreview.unknown_logical.join(', ')}
                        </div>
                      )}
                    </div>
                  )}
                </div>
              </div>
            )}

            {/* Hardware Mode */}
            {activeMode === 'hardware' && (
              <div style={{ padding: '24px', overflowY: 'auto' }}>
                <div style={{
                  padding: '24px',
                  background: '#000000',
                  borderRadius: '12px',
                  marginBottom: '20px',
                  border: '1px solid #7c3aed'
                }}>
                  <div style={{
                    fontSize: '18px',
                    fontWeight: '700',
                    color: '#9333ea',
                    marginBottom: '20px',
                    display: 'flex',
                    alignItems: 'center',
                    gap: '10px'
                  }}>
                    <span>🔧</span>
                    <span>Hardware Connection</span>
                  </div>

                  <div style={{
                    background: '#000000',
                    border: '1px solid #9333ea',
                    borderRadius: '12px',
                    padding: '20px',
                    marginBottom: '20px'
                  }}>
                    <div style={{
                      display: 'flex',
                      alignItems: 'center',
                      justifyContent: 'space-between',
                      marginBottom: '16px'
                    }}>
                      <div style={{ display: 'flex', alignItems: 'center', gap: '10px' }}>
                        <div style={{
                          width: '8px',
                          height: '8px',
                          borderRadius: '50%',
                          background: connectionStatus === 'connected' ? '#9333ea' : '#ef4444'
                        }}></div>
                        <span>{connectionStatus === 'connected' ? 'Connected' : 'Disconnected'}</span>
                      </div>
                      <button
                        onClick={toggleWebSocketConnection}
                        disabled={isRefreshingStatus}
                        title={isRefreshingStatus ? 'Refreshing hardware status...' : undefined}
                        style={{
                          background: connectionStatus === 'connected' ? '#ef4444' : '#10b981',
                          border: 'none',
                          color: '#000000',
                          padding: '8px 16px',
                          borderRadius: '6px',
                          cursor: isRefreshingStatus ? 'not-allowed' : 'pointer',
                          fontSize: '13px',
                          fontWeight: '600',
                          opacity: isRefreshingStatus ? 0.6 : 1
                        }}
                      >
                        {connectionStatus === 'connected' ? 'Disconnect' : 'Connect'}
                      </button>
                    </div>

                    <div style={{ marginBottom: '10px' }}>
                      <label style={{ display: 'block', marginBottom: '6px', fontSize: '13px', color: '#d1d5db' }}>Gateway Endpoint</label>
                      <div
                        style={{
                          width: '100%',
                          padding: '10px 14px',
                          background: '#0a0a0a',
                          border: '1px solid #7c3aed',
                          borderRadius: '6px',
                          color: '#ffffff',
                          fontSize: '13px',
                          fontFamily: 'monospace'
                        }}
                      >
                        {gatewaySocketUrl}
                      </div>
                    </div>

                    <div style={{ fontSize: '12px', color: '#6b7280', marginTop: '10px' }}>
                      <div>Connections now route through the gateway endpoint (/api/local/led/ws) so headers stay intact.</div>
                      {hardwareStatus?.ws?.target ? (
                        <div>Hardware proxy target: <span style={{ color: '#d1d5db' }}>{hardwareStatus.ws.target}</span></div>
                      ) : (
                        <div>The gateway is currently running in mock mode (no hardware target configured).</div>
                      )}
                      {hardwareStatus?.updated_at && (
                        <div>Last updated: {new Date(hardwareStatus.updated_at).toLocaleTimeString()}</div>
                      )}
                    </div>
                  </div>

                  <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', marginBottom: '8px' }}>
                    <span style={{ color: '#9ca3af', fontSize: '13px' }}>Connection Log</span>
                    <button
                      onClick={refreshHardwareStatus}
                      disabled={isRefreshingStatus}
                      style={{
                        padding: '6px 12px',
                        borderRadius: '6px',
                        border: '1px solid #7c3aed',
                        background: '#0a0a0a',
                        color: '#e5e7eb',
                        fontSize: '12px',
                        cursor: isRefreshingStatus ? 'not-allowed' : 'pointer',
                        opacity: isRefreshingStatus ? 0.6 : 1
                      }}
                    >
                      Refresh
                    </button>
                  </div>

                  <div style={{
                    background: '#000000',
                    border: '1px solid #7c3aed',
                    borderRadius: '8px',
                    padding: '16px',
                    fontFamily: 'monospace',
                    fontSize: '12px',
                    maxHeight: '200px',
                    overflowY: 'auto',
                    marginBottom: '20px'
                  }}>
                    {connectionLog.length > 0 ? (
                      connectionLog.map((entry, index) => (
                        <div key={index} style={{
                          color: entry.type === 'success' ? '#10b981' : entry.type === 'error' ? '#ef4444' : entry.type === 'warning' ? '#f59e0b' : '#9333ea',
                          marginBottom: '3px'
                        }}>
                          [{entry.timestamp}] {entry.message}
                        </div>
                      ))
                    ) : (
                      <div style={{ color: '#6b7280' }}>Connection log will appear here...</div>
                    )}
                  </div>

                  <div style={{
                    padding: '16px',
                    borderRadius: '8px',
                    border: '1px solid #1f2937',
                    background: '#050505',
                    marginBottom: '20px'
                  }}>
                    <div style={{
                      display: 'flex',
                      alignItems: 'center',
                      justifyContent: 'space-between',
                      marginBottom: '12px'
                    }}>
                      <span style={{ color: '#9ca3af', fontSize: '13px' }}>LED Engine Status</span>
                      <button
                        onClick={refreshHardwareStatus}
                        disabled={isRefreshingStatus}
                        style={{
                          padding: '6px 12px',
                          borderRadius: '6px',
                          border: '1px solid #7c3aed',
                          background: '#0a0a0a',
                          color: '#e5e7eb',
                          fontSize: '12px',
                          cursor: isRefreshingStatus ? 'not-allowed' : 'pointer',
                          opacity: isRefreshingStatus ? 0.6 : 1
                        }}
                      >
                        Refresh
                      </button>
                    </div>
                    {engineDiagnostics ? (
                      <>
                        <div style={{
                          display: 'grid',
                          gridTemplateColumns: 'repeat(auto-fit, minmax(180px, 1fr))',
                          gap: '12px',
                          marginBottom: '12px'
                        }}>
                          <div style={{ color: '#d1d5db', fontSize: '13px' }}>
                            <div style={{ color: '#9ca3af', fontSize: '11px' }}>Loop</div>
                            <div>{engineDiagnostics.running ? 'Running' : 'Stopped'}</div>
                          </div>
                          <div style={{ color: '#d1d5db', fontSize: '13px' }}>
                            <div style={{ color: '#9ca3af', fontSize: '11px' }}>Mode</div>
                            <div>{simulationMode ? 'Simulation' : 'Hardware'}</div>
                          </div>
                          <div style={{ color: '#d1d5db', fontSize: '13px' }}>
                            <div style={{ color: '#9ca3af', fontSize: '11px' }}>Tick Interval</div>
                            <div>{engineDiagnostics.tick_ms ? `${(Number(engineDiagnostics.tick_ms) || 0).toFixed(2)} ms` : 'Unknown'}</div>
                          </div>
                          <div style={{ color: '#d1d5db', fontSize: '13px' }}>
                            <div style={{ color: '#9ca3af', fontSize: '11px' }}>Last HID Write</div>
                            <div>{formatTimestampValue(engineDiagnostics.last_hid_write)}</div>
                          </div>
                          <div style={{ color: '#d1d5db', fontSize: '13px' }}>
                            <div style={{ color: '#9ca3af', fontSize: '11px' }}>Queue Depth</div>
                            <div>{queueDepth}</div>
                          </div>
                          <div style={{ color: '#d1d5db', fontSize: '13px' }}>
                            <div style={{ color: '#9ca3af', fontSize: '11px' }}>Pending Commands</div>
                            <div>{pendingCommands}</div>
                          </div>
                          <div style={{ color: '#d1d5db', fontSize: '13px' }}>
                            <div style={{ color: '#9ca3af', fontSize: '11px' }}>WS Connections</div>
                            <div>{wsConnectionCount}</div>
                          </div>
                          <div style={{ color: '#d1d5db', fontSize: '13px' }}>
                            <div style={{ color: '#9ca3af', fontSize: '11px' }}>Active Pattern</div>
                            <div>{activePatternName || 'None'}</div>
                          </div>
                        </div>
                        <div style={{ color: '#9ca3af', fontSize: '12px', marginBottom: '12px' }}>
                          {registryMessage ||
                            (simulationMode
                              ? 'Simulation mode - no LED hardware detected.'
                              : 'Hardware controllers detected.')}
                        </div>
                        {engineDiagnostics.last_error && (
                          <div style={{ color: '#f87171', fontSize: '12px', marginBottom: '12px' }}>
                            Last error: {engineDiagnostics.last_error}
                          </div>
                        )}
                        <div>
                          <div style={{ color: '#9ca3af', fontSize: '12px', marginBottom: '6px' }}>Engine Log</div>
                          <div style={{
                            background: '#000000',
                            border: '1px solid #1f2937',
                            borderRadius: '6px',
                            padding: '10px',
                            fontFamily: 'monospace',
                            fontSize: '11px',
                            maxHeight: '140px',
                            overflowY: 'auto'
                          }}>
                            {engineEvents.length > 0 ? engineEvents.map((entry, index) => (
                              <div key={index} style={{ color: '#d1d5db', marginBottom: '4px' }}>
                                [{formatTimestampValue(entry.timestamp)}] {entry.action}
                                {entry.pattern && ` ${entry.pattern}`}
                                {entry.message && ` - ${entry.message}`}
                              </div>
                            )) : (
                              <div style={{ color: '#6b7280' }}>Engine activity will appear here.</div>
                            )}
                          </div>
                        </div>
                      </>
                    ) : (
                      <div style={{ color: '#6b7280', fontSize: '12px' }}>Diagnostics will appear once the backend runtime reports its status.</div>
                    )}
                  </div>

                  <div style={{
                    padding: '16px',
                    borderRadius: '8px',
                    border: '1px solid #1f2937',
                    background: '#050505',
                    marginBottom: '20px'
                  }}>
                    <div style={{
                      fontSize: '16px',
                      fontWeight: '700',
                      color: '#9333ea',
                      marginBottom: '12px'
                    }}>
                      Detected LED Devices
                    </div>
                    {connectedDevices.length > 0 ? (
                      <div style={{ display: 'flex', flexDirection: 'column', gap: '10px' }}>
                        {connectedDevices.map((device, index) => (
                          <div key={device.device_id || `active-device-${index}`} style={{
                            border: '1px solid #1f2937',
                            borderRadius: '6px',
                            padding: '10px',
                            background: '#000000'
                          }}>
                            <div style={{ color: '#d1d5db', fontSize: '13px', marginBottom: '4px' }}>{device.device_id}</div>
                            <div style={{ color: '#9ca3af', fontSize: '11px', display: 'flex', gap: '12px', flexWrap: 'wrap' }}>
                              <span>Channels: {device.channels}</span>
                              {device.vendor_id && device.product_id && <span>VID: {device.vendor_id} PID: {device.product_id}</span>}
                              {device.serial && <span>Serial: {device.serial}</span>}
                              {device.product && <span>{device.product}</span>}
                            </div>
                          </div>
                        ))}
                      </div>
                    ) : (
                      <div style={{ color: '#6b7280', fontSize: '12px' }}>
                        {simulationMode
                          ? 'Simulation mode - no LED hardware detected.'
                          : 'No LED hardware devices reported yet.'}
                      </div>
                    )}
                  </div>

                  <div style={{
                    padding: '16px',
                    borderRadius: '8px',
                    border: '1px solid #1f2937',
                    background: '#050505',
                    marginBottom: '20px'
                  }}>
                    <div style={{
                      fontSize: '16px',
                      fontWeight: '700',
                      color: '#9333ea',
                      marginBottom: '12px'
                    }}>
                      Channel Test
                    </div>
                    <div style={{ color: '#9ca3af', fontSize: '12px', marginBottom: '12px' }}>
                      Flash a single LED channel even when running in simulation mode to verify the runtime.
                    </div>
                    {registryDevices.length > 0 ? (
                      <div style={{ display: 'flex', flexDirection: 'column', gap: '12px' }}>
                        <div>
                          <label style={{ display: 'block', color: '#d1d5db', fontSize: '13px', marginBottom: '4px' }}>Device</label>
                          <select
                            value={channelTestDevice}
                            onChange={(event) => setChannelTestDevice(event.target.value)}
                            style={{
                              width: '100%',
                              padding: '10px',
                              borderRadius: '6px',
                              border: '1px solid #7c3aed',
                              background: '#000000',
                              color: '#d1d5db',
                              fontSize: '13px'
                            }}
                          >
                            {registryDevices.map((device, index) => (
                              <option key={device.device_id || `device-${index}`} value={device.device_id}>
                                {device.device_id} {device.simulation ? '(simulation)' : ''}
                              </option>
                            ))}
                          </select>
                        </div>
                        <div>
                          <label style={{ display: 'block', color: '#d1d5db', fontSize: '13px', marginBottom: '4px' }}>Channel (0-31)</label>
                          <input
                            type="number"
                            min="0"
                            max="31"
                            value={channelTestChannel}
                            onChange={(event) => setChannelTestChannel(event.target.value)}
                            style={{
                              width: '100%',
                              padding: '10px',
                              borderRadius: '6px',
                              border: '1px solid #7c3aed',
                              background: '#000000',
                              color: '#d1d5db',
                              fontSize: '13px'
                            }}
                          />
                        </div>
                        <button
                          onClick={handleChannelTest}
                          disabled={isTestingChannel}
                          style={{
                            padding: '10px 14px',
                            borderRadius: '6px',
                            border: '1px solid #7c3aed',
                            background: isTestingChannel ? '#4c1d95' : '#9333ea',
                            color: '#ffffff',
                            fontSize: '13px',
                            fontWeight: '600',
                            cursor: isTestingChannel ? 'not-allowed' : 'pointer',
                            opacity: isTestingChannel ? 0.7 : 1
                          }}
                        >
                          {isTestingChannel ? 'Testing...' : 'Test Channel'}
                        </button>
                        {channelTestResult && (
                          <div style={{
                            marginTop: '4px',
                            fontSize: '12px',
                            color: channelTestResult.status === 'error' ? '#f87171' : '#10b981'
                          }}>
                            {channelTestResult.status === 'error'
                              ? channelTestResult.message
                              : `Channel ${channelTestResult.payload?.channel} acknowledged (${channelTestResult.payload?.mode})`}
                          </div>
                        )}
                      </div>
                    ) : (
                      <div style={{ color: '#6b7280', fontSize: '12px' }}>No devices available for channel diagnostics.</div>
                    )}
                  </div>

                  <div style={{ marginBottom: '20px' }}>
                    <div style={{
                      fontSize: '16px',
                      fontWeight: '700',
                      color: '#9333ea',
                      marginBottom: '16px',
                      display: 'flex',
                      alignItems: 'center',
                      gap: '10px'
                    }}>
                      <span>🔥</span>
                      <span>Hardware Test</span>
                    </div>
                    <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: '10px' }}>
                      <button onClick={() => triggerHardwareTest('all_on', { durationMs: 1500, color: '#9333ea' })} style={{ padding: '12px', background: '#000000', border: '1px solid #7c3aed', color: '#d1d5db', borderRadius: '8px', cursor: 'pointer', fontSize: '13px', fontWeight: '600' }}>All LEDs On</button>
                      <button onClick={() => triggerHardwareTest('all_off')} style={{ padding: '12px', background: '#000000', border: '1px solid #7c3aed', color: '#d1d5db', borderRadius: '8px', cursor: 'pointer', fontSize: '13px', fontWeight: '600' }}>All LEDs Off</button>
                      <button
                        disabled
                        title="Chase diagnostics will be enabled once the backend LED pattern runner lands."
                        style={{
                          padding: '12px',
                          background: '#000000',
                          border: '1px solid #7c3aed',
                          color: '#d1d5db',
                          borderRadius: '8px',
                          cursor: 'not-allowed',
                          fontSize: '13px',
                          fontWeight: '600',
                          opacity: 0.5
                        }}>
                        <div style={{ display: 'flex', flexDirection: 'column', gap: '4px', alignItems: 'center' }}>
                          <span>Chase Pattern</span>
                          <ComingSoonTag />
                        </div>
                      </button>
                      <button
                        disabled
                        title="Rainbow test requires backend support; coming soon."
                        style={{
                          padding: '12px',
                          background: '#000000',
                          border: '1px solid #7c3aed',
                          color: '#d1d5db',
                          borderRadius: '8px',
                          cursor: 'not-allowed',
                          fontSize: '13px',
                          fontWeight: '600',
                          opacity: 0.5
                        }}>
                        <div style={{ display: 'flex', flexDirection: 'column', gap: '4px', alignItems: 'center' }}>
                          <span>Rainbow Test</span>
                          <ComingSoonTag />
                        </div>
                      </button>
                    </div>
                  </div>
                </div>
              </div>
            )}

            {/* Calibration Mode - Wiring Wizard (Phase 6.5) */}
            {activeMode === 'calibration' && (
              <div style={{
                padding: '24px',
                overflowY: 'auto',
                display: 'grid',
                gridTemplateColumns: '1fr 1fr',
                gap: '24px'
              }}>
                {/* Left: Wiring Wizard Controls */}
                <div>
                  <WiringWizard
                    wizardState={wizardState}
                    onStateChange={setWizardState}
                    numPlayers={cabinetPlayerCount}
                    onMapButton={handleWizardMapButton}
                    onComplete={() => {
                      setWizardState(prev => ({ ...prev, isActive: false }))
                      showToast('LED mappings saved successfully!', 'success')
                    }}
                    onCancel={() => {
                      setWizardState(prev => ({ ...prev, isActive: false }))
                      showToast('Calibration cancelled', 'info')
                    }}
                  />

                  {/* Existing Channel Mappings Display */}
                  <div style={{
                    marginTop: '24px',
                    padding: '20px',
                    background: '#0f0f0f',
                    borderRadius: '12px',
                    border: '1px solid #7c3aed'
                  }}>
                    <div style={{
                      fontSize: '16px',
                      fontWeight: '700',
                      color: '#9333ea',
                      marginBottom: '12px',
                      display: 'flex',
                      alignItems: 'center',
                      gap: '8px'
                    }}>
                      <span>📋</span>
                      <span>Current LED Channel Mappings</span>
                    </div>
                    <p style={{ color: '#9ca3af', fontSize: '13px' }}>
                      {Object.keys(channelState.channels || {}).length > 0
                        ? `${Object.keys(channelState.channels).length} button(s) mapped`
                        : 'No mappings configured. Use the wizard above to create mappings.'}
                    </p>
                  </div>
                </div>

                {/* Right: Arcade Panel Preview - MUST be visible in calibration mode */}
                <div>
                  <div style={{
                    padding: '20px',
                    background: wizardState.isActive ? '#1a0a2e' : '#0f0f0f',
                    borderRadius: '12px',
                    border: wizardState.isActive ? '2px solid #10b981' : '1px solid #9333ea',
                    transition: 'all 0.3s ease'
                  }}>
                    <div style={{
                      fontSize: '16px',
                      fontWeight: '700',
                      color: wizardState.isActive ? '#10b981' : '#9333ea',
                      marginBottom: '16px',
                      display: 'flex',
                      alignItems: 'center',
                      gap: '8px'
                    }}>
                      <span>{wizardState.isActive ? '👆' : '🎮'}</span>
                      <span>{wizardState.isActive ? 'Click Button to Map' : 'Arcade Panel Preview'}</span>
                    </div>

                    {wizardState.isActive && (
                      <div style={{
                        marginBottom: '16px',
                        padding: '12px',
                        background: 'rgba(16, 185, 129, 0.15)',
                        borderRadius: '8px',
                        textAlign: 'center',
                        color: '#34d399',
                        fontSize: '14px',
                        fontWeight: '600'
                      }}>
                        👇 Click the button on this panel that matches the blinking LED
                      </div>
                    )}

                    <ArcadePanelPreview
                      mappingForm={mappingForm}
                      activeButtons={currentActiveButtons}
                      playerCount={cabinetPlayerCount}
                      showLabels={true}
                      onButtonClick={(player, button) => {
                        // Phase 6.5: Unified wizard click handler
                        const buttonId = `p${player}.button${button}`
                        if (wizardState.isActive) {
                          // Route to hoisted wizard mapping function
                          handleWizardMapButton(buttonId)
                        } else {
                          // Normal LED toggle when wizard not active
                          toggleLED(player, button)
                        }
                      }}
                    />
                  </div>
                </div>
              </div>
            )}

            {/* Animation Designer Mode - DEPRECATED (keeping for backwards compat) */}
            {activeMode === 'animation' && (
              <div style={{ padding: '24px', overflowY: 'auto' }}>
                {/* Profile Selector */}
                <div style={{
                  padding: '20px',
                  background: '#000000',
                  borderRadius: '12px',
                  marginBottom: '20px',
                  border: '1px solid #7c3aed'
                }}>
                  <div style={{
                    fontSize: '16px',
                    fontWeight: '700',
                    color: '#9333ea',
                    marginBottom: '12px',
                    display: 'flex',
                    alignItems: 'center',
                    gap: '8px'
                  }}>
                    <span>📁</span>
                    <span>LED Profile Library</span>
                  </div>
                  <select
                    value={selectedProfile}
                    onChange={(e) => handleLoadProfile(e.target.value)}
                    disabled={isLoadingProfiles}
                    style={{
                      width: '100%',
                      padding: '12px',
                      background: '#0a0a0a',
                      border: '1px solid #9333ea',
                      borderRadius: '8px',
                      color: '#ffffff',
                      fontSize: '14px'
                    }}
                  >
                    <option value="">-- Select a Profile to Load --</option>
                    {availableProfiles.map(profile => (
                      <option key={profile.value} value={profile.value}>
                        {profile.label}
                      </option>
                    ))}
                  </select>
                  {selectedProfileMeta && (
                    <div style={{
                      marginTop: '8px',
                      color: '#8b5cf6',
                      fontSize: '12px'
                    }}>
                      {selectedProfileMeta.filename ? `File: ${selectedProfileMeta.filename}` : null}
                      {selectedProfileMeta.scope ? ` • Scope: ${selectedProfileMeta.scope}` : null}
                      {Array.isArray(selectedProfileMeta.mapping_keys) && selectedProfileMeta.mapping_keys.length > 0
                        ? ` • Keys: ${selectedProfileMeta.mapping_keys.length}`
                        : null}
                    </div>
                  )}
                  {isLoadingProfiles && (
                    <div style={{ marginTop: '8px', color: '#9333ea', fontSize: '12px' }}>
                      Loading profiles...
                    </div>
                  )}
                </div>

                {/* LED Mapping Configuration */}
                <div style={{
                  padding: '20px',
                  background: '#000000',
                  borderRadius: '12px',
                  border: '1px solid #7c3aed'
                }}>
                  <div style={{
                    fontSize: '16px',
                    fontWeight: '700',
                    color: '#9333ea',
                    marginBottom: '16px',
                    display: 'flex',
                    alignItems: 'center',
                    gap: '8px'
                  }}>
                    <span>🎨</span>
                    <span>LED Mapping Configuration</span>
                  </div>

                  {/* Color Picker Section */}
                  <div style={{
                    marginBottom: '20px',
                    padding: '16px',
                    background: '#0a0a0a',
                    borderRadius: '8px',
                    border: '1px solid #7c3aed'
                  }}>
                    <h3 style={{
                      fontSize: '14px',
                      fontWeight: '600',
                      color: '#d1d5db',
                      marginBottom: '16px'
                    }}>
                      Button Colors
                    </h3>

                    {/* Player 1 Colors */}
                    <div style={{ marginBottom: '16px' }}>
                      <div style={{
                        fontSize: '13px',
                        fontWeight: '600',
                        color: '#9333ea',
                        marginBottom: '12px'
                      }}>
                        Player 1
                      </div>
                      <div style={{
                        display: 'grid',
                        gridTemplateColumns: 'repeat(2, 1fr)',
                        gap: '12px'
                      }}>
                        {['button1', 'button2', 'button3', 'button4'].map((btn, idx) => (
                          <div key={`p1_${btn}`} style={{
                            display: 'flex',
                            alignItems: 'center',
                            gap: '8px'
                          }}>
                            <label style={{
                              fontSize: '12px',
                              color: '#d1d5db',
                              minWidth: '60px'
                            }}>
                              Button {idx + 1}:
                            </label>
                            <input
                              type="color"
                              value={mappingForm[`p1_${btn}`]}
                              onChange={(e) => setButtonColor(`p1_${btn}`, e.target.value)}
                              style={{
                                width: '40px',
                                height: '32px',
                                cursor: 'pointer',
                                border: '1px solid #7c3aed',
                                borderRadius: '4px',
                                background: '#000000',
                                padding: '2px'
                              }}
                            />
                            <span style={{
                              fontSize: '11px',
                              color: '#9ca3af',
                              fontFamily: 'monospace'
                            }}>
                              {mappingForm[`p1_${btn}`]}
                            </span>
                          </div>
                        ))}
                      </div>
                    </div>

                    {/* Player 2 Colors */}
                    <div>
                      <div style={{
                        fontSize: '13px',
                        fontWeight: '600',
                        color: '#a855f7',
                        marginBottom: '12px'
                      }}>
                        Player 2
                      </div>
                      <div style={{
                        display: 'grid',
                        gridTemplateColumns: 'repeat(2, 1fr)',
                        gap: '12px'
                      }}>
                        {['button1', 'button2', 'button3', 'button4'].map((btn, idx) => (
                          <div key={`p2_${btn}`} style={{
                            display: 'flex',
                            alignItems: 'center',
                            gap: '8px'
                          }}>
                            <label style={{
                              fontSize: '12px',
                              color: '#d1d5db',
                              minWidth: '60px'
                            }}>
                              Button {idx + 1}:
                            </label>
                            <input
                              type="color"
                              value={mappingForm[`p2_${btn}`]}
                              onChange={(e) => setButtonColor(`p2_${btn}`, e.target.value)}
                              style={{
                                width: '40px',
                                height: '32px',
                                cursor: 'pointer',
                                border: '1px solid #7c3aed',
                                borderRadius: '4px',
                                background: '#000000',
                                padding: '2px'
                              }}
                            />
                            <span style={{
                              fontSize: '11px',
                              color: '#9ca3af',
                              fontFamily: 'monospace'
                            }}>
                              {mappingForm[`p2_${btn}`]}
                            </span>
                          </div>
                        ))}
                      </div>
                    </div>
                  </div>

                  {/* Advanced JSON Editor (Collapsible) */}
                  <details style={{ marginBottom: '12px' }}>
                    <summary style={{
                      fontSize: '13px',
                      fontWeight: '600',
                      color: '#d1d5db',
                      cursor: 'pointer',
                      padding: '8px',
                      background: '#0a0a0a',
                      borderRadius: '6px',
                      border: '1px solid #4b5563',
                      marginBottom: '8px',
                      userSelect: 'none'
                    }}>
                      ⚙️ Advanced: JSON Editor
                    </summary>
                    <div style={{ marginTop: '8px' }}>
                      <label style={{
                        display: 'block',
                        marginBottom: '8px',
                        fontSize: '12px',
                        color: '#9ca3af'
                      }}>
                        Direct JSON Mapping (Expert Mode):
                      </label>
                      <textarea
                        value={mappingData}
                        onChange={(e) => {
                          setMappingData(e.target.value)
                          // Try to parse and sync to color pickers
                          try {
                            const parsed = JSON.parse(e.target.value)
                            if (parsed.player1 || parsed.player2) {
                              setMappingForm({
                                p1_button1: parsed.player1?.button1 || mappingForm.p1_button1,
                                p1_button2: parsed.player1?.button2 || mappingForm.p1_button2,
                                p1_button3: parsed.player1?.button3 || mappingForm.p1_button3,
                                p1_button4: parsed.player1?.button4 || mappingForm.p1_button4,
                                p2_button1: parsed.player2?.button1 || mappingForm.p2_button1,
                                p2_button2: parsed.player2?.button2 || mappingForm.p2_button2,
                                p2_button3: parsed.player2?.button3 || mappingForm.p2_button3,
                                p2_button4: parsed.player2?.button4 || mappingForm.p2_button4
                              })
                            }
                          } catch (err) {
                            // Invalid JSON, ignore for now
                          }
                        }}
                        placeholder={`{
  "profile_name": "custom-profile",
  "scope": "game",
  "game": "Example Game",
  "buttons": {
    "p1.button1": { "color": "#FF0000" },
    "p1.button2": { "color": "#00FF00" },
    "p1.button3": { "color": "#0000FF" },
    "p1.button4": { "color": "#FFFF00" },
    "p2.button1": { "color": "#FF00FF" }
  }
}`}
                        style={{
                          width: '100%',
                          minHeight: '160px',
                          padding: '12px',
                          background: '#0a0a0a',
                          border: '1px solid #4b5563',
                          borderRadius: '6px',
                          color: '#ffffff',
                          fontSize: '12px',
                          fontFamily: 'monospace',
                          resize: 'vertical'
                        }}
                      />
                    </div>
                  </details>

                  {/* Preview Display */}
                  {profilePreview && (
                    <div style={{
                      marginBottom: '16px',
                      padding: '12px',
                      background: '#0a0a0a',
                      border: '1px solid #10b981',
                      borderRadius: '8px'
                    }}>
                      <div style={{
                        fontSize: '13px',
                        fontWeight: '600',
                        color: '#10b981',
                        marginBottom: '8px'
                      }}>
                        Preview Changes:
                      </div>
                      <pre style={{
                        margin: 0,
                        fontSize: '12px',
                        color: '#d1d5db',
                        overflow: 'auto',
                        maxHeight: '150px'
                      }}>
                        {JSON.stringify(profilePreview, null, 2)}
                      </pre>
                    </div>
                  )}

                  {/* Action Buttons */}
                  <div style={{
                    display: 'flex',
                    gap: '12px'
                  }}>
                    <button
                      onClick={handlePreviewProfile}
                      disabled={!hasMappingInput}
                      style={{
                        flex: 1,
                        padding: '12px',
                        background: '#111111',
                        border: '1px solid #9333ea',
                        borderRadius: '8px',
                        color: '#9333ea',
                        fontSize: '14px',
                        fontWeight: '600',
                        cursor: hasMappingInput ? 'pointer' : 'not-allowed',
                        opacity: hasMappingInput ? 1 : 0.5
                      }}
                    >
                      Preview Changes
                    </button>
                    <button
                      onClick={handleApplyProfile}
                      disabled={!canApplyProfile}
                      style={{
                        flex: 1,
                        padding: '12px',
                        background: isApplyingMapping ? '#333' : 'linear-gradient(135deg, #9333ea, #7c3aed)',
                        border: 'none',
                        borderRadius: '8px',
                        color: '#ffffff',
                        fontSize: '14px',
                        fontWeight: '600',
                        cursor: canApplyProfile ? 'pointer' : 'not-allowed',
                        opacity: canApplyProfile ? 1 : 0.5
                      }}
                    >
                      {isApplyingMapping ? 'Applying...' : 'Apply Mapping'}
                    </button>
                  </div>

                  <div style={{
                    marginTop: '12px',
                    fontSize: '12px',
                    color: '#6b7280'
                  }}>
                    Configure button colors and animations for different games. Changes are saved automatically.
                  </div>
                </div>
              </div>
            )}

            {/* Real-time Control Mode - Camera Demo Ready */}
            {activeMode === 'realtime' && (
              <div style={{ padding: '24px', display: 'flex', flexDirection: 'column', gap: '24px' }}>

                {/* Block 1: Hardware Status Card */}
                <div style={{
                  background: 'linear-gradient(135deg, #111, #0a0a0a)',
                  border: '1px solid #9333ea',
                  borderRadius: '12px',
                  padding: '20px'
                }}>
                  <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '16px' }}>
                    <h3 style={{ color: '#9333ea', margin: 0, fontSize: '16px', fontWeight: '700' }}>
                      💻 Hardware Status
                    </h3>
                    <button
                      onClick={refreshHardwareStatus}
                      disabled={isRefreshingStatus}
                      style={{
                        background: isRefreshingStatus ? '#374151' : 'linear-gradient(135deg, #9333ea, #7c3aed)',
                        border: 'none',
                        borderRadius: '8px',
                        color: 'white',
                        padding: '8px 16px',
                        cursor: isRefreshingStatus ? 'not-allowed' : 'pointer',
                        fontSize: '13px',
                        fontWeight: '600'
                      }}
                    >
                      {isRefreshingStatus ? '⏳ Refreshing...' : '🔄 Refresh Status'}
                    </button>
                  </div>
                  <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(180px, 1fr))', gap: '12px' }}>
                    <div style={{ background: '#0a0a0a', padding: '12px', borderRadius: '8px', border: '1px solid #374151' }}>
                      <div style={{ color: '#9ca3af', fontSize: '11px', marginBottom: '4px' }}>Connection</div>
                      <div style={{ color: connectedDevices.length > 0 ? '#10b981' : simulationMode ? '#f59e0b' : '#ef4444', fontWeight: '600' }}>
                        {connectedDevices.length > 0 ? '✅ Connected' : simulationMode ? '⚠️ Simulation' : '❌ Disconnected'}
                      </div>
                    </div>
                    <div style={{ background: '#0a0a0a', padding: '12px', borderRadius: '8px', border: '1px solid #374151' }}>
                      <div style={{ color: '#9ca3af', fontSize: '11px', marginBottom: '4px' }}>Device Type</div>
                      <div style={{ color: '#e5e7eb', fontWeight: '600' }}>
                        {connectedDevices[0]?.device_id || 'LED-Wiz (simulated)'}
                      </div>
                    </div>
                    <div style={{ background: '#0a0a0a', padding: '12px', borderRadius: '8px', border: '1px solid #374151' }}>
                      <div style={{ color: '#9ca3af', fontSize: '11px', marginBottom: '4px' }}>LED Count</div>
                      <div style={{ color: '#e5e7eb', fontWeight: '600' }}>
                        {channelState.total_channels || 32} channels
                      </div>
                    </div>
                    <div style={{ background: '#0a0a0a', padding: '12px', borderRadius: '8px', border: '1px solid #374151' }}>
                      <div style={{ color: '#9ca3af', fontSize: '11px', marginBottom: '4px' }}>WebSocket</div>
                      <div style={{ color: connectionStatus === 'connected' ? '#10b981' : '#9ca3af', fontWeight: '600' }}>
                        {connectionStatus === 'connected' ? '🔗 Live' : '⚡ Ready'}
                      </div>
                    </div>
                  </div>
                  {demoLastError && (
                    <div style={{ marginTop: '12px', padding: '8px 12px', background: 'rgba(239, 68, 68, 0.1)', border: '1px solid #ef4444', borderRadius: '6px', color: '#ef4444', fontSize: '12px' }}>
                      ⚠️ {demoLastError}
                    </div>
                  )}
                </div>

                {/* Block 2: Test Controls */}
                <div style={{
                  background: 'linear-gradient(135deg, #111, #0a0a0a)',
                  border: '1px solid #9333ea',
                  borderRadius: '12px',
                  padding: '20px'
                }}>
                  <h3 style={{ color: '#9333ea', margin: '0 0 16px 0', fontSize: '16px', fontWeight: '700' }}>
                    🔦 Test Controls
                  </h3>

                  {/* Test All LEDs */}
                  <div style={{ display: 'flex', gap: '12px', alignItems: 'center', marginBottom: '16px', flexWrap: 'wrap' }}>
                    <select
                      value={demoTestDuration}
                      onChange={(e) => setDemoTestDuration(Number(e.target.value))}
                      style={{
                        background: '#0a0a0a',
                        border: '1px solid #374151',
                        borderRadius: '6px',
                        color: '#e5e7eb',
                        padding: '8px 12px',
                        fontSize: '13px'
                      }}
                    >
                      <option value={500}>500ms</option>
                      <option value={1000}>1 second</option>
                      <option value={2000}>2 seconds</option>
                      <option value={5000}>5 seconds</option>
                    </select>
                    <button
                      onClick={async () => {
                        setIsTestingAllLEDs(true)
                        setDemoLastError(null)
                        try {
                          await testAllLEDs({ durationMs: demoTestDuration })
                          showToast('All LEDs tested!', 'success')
                        } catch (err) {
                          setDemoLastError(err?.error || err?.message || 'Test failed')
                        } finally {
                          setIsTestingAllLEDs(false)
                        }
                      }}
                      disabled={isTestingAllLEDs}
                      style={{
                        background: isTestingAllLEDs ? '#374151' : 'linear-gradient(135deg, #10b981, #059669)',
                        border: 'none',
                        borderRadius: '8px',
                        color: 'white',
                        padding: '10px 20px',
                        cursor: isTestingAllLEDs ? 'not-allowed' : 'pointer',
                        fontWeight: '600',
                        fontSize: '14px'
                      }}
                    >
                      {isTestingAllLEDs ? '⏳ Testing...' : '💡 Test All LEDs'}
                    </button>
                  </div>

                  {/* Flash Selected Control */}
                  <div style={{ display: 'flex', gap: '12px', alignItems: 'center', flexWrap: 'wrap' }}>
                    <select
                      value={demoFlashPlayer}
                      onChange={(e) => setDemoFlashPlayer(e.target.value)}
                      style={{
                        background: '#0a0a0a',
                        border: '1px solid #374151',
                        borderRadius: '6px',
                        color: '#e5e7eb',
                        padding: '8px 12px',
                        fontSize: '13px'
                      }}
                    >
                      {[1, 2, 3, 4].map(p => <option key={p} value={p}>Player {p}</option>)}
                    </select>
                    <select
                      value={demoFlashButton}
                      onChange={(e) => setDemoFlashButton(e.target.value)}
                      style={{
                        background: '#0a0a0a',
                        border: '1px solid #374151',
                        borderRadius: '6px',
                        color: '#e5e7eb',
                        padding: '8px 12px',
                        fontSize: '13px'
                      }}
                    >
                      {[1, 2, 3, 4, 5, 6, 7, 8, 'start', 'coin'].map(b => (
                        <option key={b} value={b}>{typeof b === 'number' ? `Button ${b}` : b.charAt(0).toUpperCase() + b.slice(1)}</option>
                      ))}
                    </select>
                    <input
                      type="color"
                      value={demoFlashColor}
                      onChange={(e) => setDemoFlashColor(e.target.value)}
                      style={{
                        width: '44px',
                        height: '36px',
                        border: '2px solid #374151',
                        borderRadius: '6px',
                        cursor: 'pointer'
                      }}
                    />
                    <button
                      onClick={async () => {
                        setIsFlashingDemo(true)
                        setDemoLastError(null)
                        try {
                          const logicalButton = `p${demoFlashPlayer}.button${demoFlashButton}`
                          await flashLEDCalibration({
                            token: calibrationToken || 'demo',
                            logical_button: logicalButton,
                            color: demoFlashColor,
                            duration_ms: 500
                          })
                          showToast(`Flashed P${demoFlashPlayer} ${demoFlashButton}`, 'success')
                        } catch (err) {
                          // Fallback: try testLED if calibration fails
                          try {
                            await testLED({ effect: 'solid', color: demoFlashColor, durationMs: 500 })
                          } catch (err2) {
                            setDemoLastError(err?.error || err?.message || 'Flash failed')
                          }
                        } finally {
                          setIsFlashingDemo(false)
                        }
                      }}
                      disabled={isFlashingDemo}
                      style={{
                        background: isFlashingDemo ? '#374151' : 'linear-gradient(135deg, #f59e0b, #d97706)',
                        border: 'none',
                        borderRadius: '8px',
                        color: 'white',
                        padding: '10px 20px',
                        cursor: isFlashingDemo ? 'not-allowed' : 'pointer',
                        fontWeight: '600',
                        fontSize: '14px'
                      }}
                    >
                      {isFlashingDemo ? '⏳...' : '⚡ Flash'}
                    </button>
                  </div>
                </div>

                {/* Block 3: Per-Control Color Grid (Profile Colors) */}
                <div style={{
                  background: 'linear-gradient(135deg, #111, #0a0a0a)',
                  border: '1px solid #9333ea',
                  borderRadius: '12px',
                  padding: '20px'
                }}>
                  <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '16px' }}>
                    <h3 style={{ color: '#9333ea', margin: 0, fontSize: '16px', fontWeight: '700' }}>
                      🎨 Profile Color Grid
                    </h3>
                    <button
                      onClick={async () => {
                        setDemoLastError(null)
                        try {
                          const profile = {
                            profile_name: 'manual_profile',
                            scope: 'manual',
                            buttons: buildButtonsFromForm(mappingForm)
                          }
                          await applyLEDProfile(profile)
                          showToast('Colors applied to hardware!', 'success')
                        } catch (err) {
                          setDemoLastError(err?.error || err?.message || 'Apply failed')
                        }
                      }}
                      style={{
                        background: 'linear-gradient(135deg, #9333ea, #7c3aed)',
                        border: 'none',
                        borderRadius: '8px',
                        color: 'white',
                        padding: '8px 16px',
                        cursor: 'pointer',
                        fontWeight: '600',
                        fontSize: '13px'
                      }}
                    >
                      ✅ Apply Colors
                    </button>
                  </div>
                  <div style={{ color: '#9ca3af', fontSize: '12px', marginBottom: '16px' }}>
                    Click any button to change its color. Changes affect the current profile, not hardware wiring.
                  </div>

                  {/* P1/P2 8-button layout */}
                  <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: '24px', marginBottom: '20px' }}>
                    {[1, 2].map(player => (
                      <div key={player} style={{ background: '#0a0a0a', borderRadius: '10px', padding: '16px', border: '1px solid #374151' }}>
                        <div style={{ color: '#c084fc', fontWeight: '700', marginBottom: '12px', fontSize: '14px' }}>
                          Player {player}
                        </div>
                        {/* Row 1: 1,2,3,7 */}
                        <div style={{ display: 'flex', gap: '8px', marginBottom: '8px' }}>
                          {[1, 2, 3, 7].map(btn => {
                            const formKey = `p${player}_button${btn}`
                            const color = mappingForm[formKey] || '#333'
                            return (
                              <div key={btn} style={{ position: 'relative' }}>
                                <input
                                  type="color"
                                  value={color}
                                  onChange={(e) => setMappingForm(prev => ({ ...prev, [formKey]: e.target.value }))}
                                  style={{
                                    width: '36px',
                                    height: '36px',
                                    border: '2px solid #7c3aed',
                                    borderRadius: '50%',
                                    cursor: 'pointer',
                                    background: color
                                  }}
                                  title={`P${player} B${btn}`}
                                />
                                <span style={{ position: 'absolute', bottom: '-14px', left: '50%', transform: 'translateX(-50%)', fontSize: '10px', color: '#9ca3af' }}>{btn}</span>
                              </div>
                            )
                          })}
                        </div>
                        {/* Row 2: 4,5,6,8 */}
                        <div style={{ display: 'flex', gap: '8px', marginTop: '16px' }}>
                          {[4, 5, 6, 8].map(btn => {
                            const formKey = `p${player}_button${btn}`
                            const color = mappingForm[formKey] || '#333'
                            return (
                              <div key={btn} style={{ position: 'relative' }}>
                                <input
                                  type="color"
                                  value={color}
                                  onChange={(e) => setMappingForm(prev => ({ ...prev, [formKey]: e.target.value }))}
                                  style={{
                                    width: '36px',
                                    height: '36px',
                                    border: '2px solid #7c3aed',
                                    borderRadius: '50%',
                                    cursor: 'pointer',
                                    background: color
                                  }}
                                  title={`P${player} B${btn}`}
                                />
                                <span style={{ position: 'absolute', bottom: '-14px', left: '50%', transform: 'translateX(-50%)', fontSize: '10px', color: '#9ca3af' }}>{btn}</span>
                              </div>
                            )
                          })}
                        </div>
                      </div>
                    ))}
                  </div>

                  {/* P3/P4 4-button layout */}
                  <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: '24px' }}>
                    {[3, 4].map(player => (
                      <div key={player} style={{ background: '#0a0a0a', borderRadius: '10px', padding: '12px', border: '1px solid #374151' }}>
                        <div style={{ color: '#a855f7', fontWeight: '600', marginBottom: '8px', fontSize: '13px' }}>
                          Player {player}
                        </div>
                        <div style={{ display: 'flex', gap: '6px' }}>
                          {[1, 2, 3, 4].map(btn => {
                            const formKey = `p${player}_button${btn}`
                            const color = mappingForm[formKey] || '#333'
                            return (
                              <input
                                key={btn}
                                type="color"
                                value={color}
                                onChange={(e) => setMappingForm(prev => ({ ...prev, [formKey]: e.target.value }))}
                                style={{
                                  width: '28px',
                                  height: '28px',
                                  border: '2px solid #6b21a8',
                                  borderRadius: '50%',
                                  cursor: 'pointer',
                                  background: color
                                }}
                                title={`P${player} B${btn}`}
                              />
                            )
                          })}
                        </div>
                      </div>
                    ))}
                  </div>
                </div>

                {/* Block 4: Now Playing / Per-Game Proof */}
                <div style={{
                  background: 'linear-gradient(135deg, #111, #0a0a0a)',
                  border: '1px solid #9333ea',
                  borderRadius: '12px',
                  padding: '20px'
                }}>
                  <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '16px' }}>
                    <h3 style={{ color: '#9333ea', margin: 0, fontSize: '16px', fontWeight: '700' }}>
                      🎮 Now Playing
                    </h3>
                    <button
                      onClick={async () => {
                        setDemoLastError(null)
                        try {
                          const profiles = await listLEDProfiles()
                          setAvailableProfiles(profiles?.profiles || [])
                          showToast(`Loaded ${profiles?.profiles?.length || 0} profiles`, 'success')
                        } catch (err) {
                          setDemoLastError(err?.error || err?.message || 'Failed to load profiles')
                        }
                      }}
                      style={{
                        background: '#374151',
                        border: 'none',
                        borderRadius: '6px',
                        color: '#e5e7eb',
                        padding: '6px 12px',
                        cursor: 'pointer',
                        fontSize: '12px'
                      }}
                    >
                      🔄 Reload Profiles
                    </button>
                  </div>

                  <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: '16px', marginBottom: '16px' }}>
                    <div style={{ background: '#0a0a0a', padding: '16px', borderRadius: '8px', border: '1px solid #374151' }}>
                      <div style={{ color: '#9ca3af', fontSize: '11px', marginBottom: '6px' }}>Current Game</div>
                      <div style={{ color: '#e5e7eb', fontWeight: '600', fontSize: '15px' }}>
                        {selectedGame?.title || selectedProfile || 'No game selected'}
                      </div>
                    </div>
                    <div style={{ background: '#0a0a0a', padding: '16px', borderRadius: '8px', border: '1px solid #374151' }}>
                      <div style={{ color: '#9ca3af', fontSize: '11px', marginBottom: '6px' }}>Active Profile</div>
                      <div style={{ color: '#c084fc', fontWeight: '600', fontSize: '15px' }}>
                        {selectedGameProfileName || selectedProfileMeta?.profile_name || selectedProfile || 'Default'}
                      </div>
                    </div>
                  </div>

                  <button
                    onClick={async () => {
                      setDemoLastError(null)
                      try {
                        if (selectedGame && selectedGameProfileName) {
                          // Apply game profile binding
                          const result = await applyGameProfileBinding({
                            gameId: selectedGame.id || selectedGame.game_id,
                            profileName: selectedGameProfileName
                          })
                          // Update form from result if available
                          if (result?.preview?.buttons) {
                            setMappingForm(buildFormFromButtons(result.preview.buttons))
                          }
                          showToast(`Applied ${selectedGameProfileName} profile!`, 'success')
                        } else if (selectedProfile) {
                          // Apply selected profile
                          const profile = await getLEDProfile(selectedProfile)
                          if (profile?.buttons) {
                            setMappingForm(buildFormFromButtons(profile.buttons))
                          }
                          await applyLEDProfile(profile)
                          showToast(`Applied ${selectedProfile} profile!`, 'success')
                        } else {
                          setDemoLastError('Select a game or profile first')
                        }
                      } catch (err) {
                        setDemoLastError(err?.error || err?.message || 'Apply failed')
                      }
                    }}
                    style={{
                      background: 'linear-gradient(135deg, #9333ea, #7c3aed)',
                      border: 'none',
                      borderRadius: '8px',
                      color: 'white',
                      padding: '12px 24px',
                      cursor: 'pointer',
                      fontWeight: '600',
                      fontSize: '14px',
                      width: '100%'
                    }}
                  >
                    🚀 Apply Profile to Hardware
                  </button>
                </div>

              </div>
            )}
          </div>
        </div>

        {/* Bottom Bar */}
        <div style={{
          background: '#000000',
          borderTop: '1px solid #9333ea',
          padding: '20px 24px',
          display: 'flex',
          justifyContent: 'space-between',
          alignItems: 'center'
        }}>
          <div style={{ display: 'flex', gap: '16px' }}>
            <button
              disabled
              title="Saving configurations requires the new backend workflow."
              style={{
                padding: '10px 20px',
                borderRadius: '8px',
                border: 'none',
                fontWeight: '600',
                cursor: 'not-allowed',
                fontSize: '14px',
                background: 'linear-gradient(135deg, #9333ea, #7c3aed)',
                color: '#ffffff',
                opacity: 0.5
              }}>
              <div style={{ display: 'flex', flexDirection: 'column', gap: '4px', alignItems: 'center' }}>
                <span>Save Configuration</span>
                <ComingSoonTag />
              </div>
            </button>
            <button
              disabled
              title="Export will be enabled once gateway-safe downloads are available."
              style={{
                padding: '10px 20px',
                borderRadius: '8px',
                fontWeight: '600',
                cursor: 'not-allowed',
                fontSize: '14px',
                background: '#111111',
                color: '#9333ea',
                border: '1px solid #9333ea',
                opacity: 0.5
              }}>
              <div style={{ display: 'flex', flexDirection: 'column', gap: '4px', alignItems: 'center' }}>
                <span>Export</span>
                <ComingSoonTag />
              </div>
            </button>
            <button
              disabled
              title="Pattern saving is paused until it routes through the gateway."
              style={{
                padding: '10px 20px',
                borderRadius: '8px',
                fontWeight: '600',
                cursor: 'not-allowed',
                fontSize: '14px',
                background: '#111111',
                color: '#10b981',
                border: '1px solid #10b981',
                display: 'flex',
                alignItems: 'center',
                gap: '6px',
                opacity: 0.5
              }}>
              <div style={{ display: 'flex', flexDirection: 'column', gap: '4px', alignItems: 'center' }}>
                <span>dY'_ Save Pattern</span>
                <ComingSoonTag />
              </div>
            </button>
            <button
              disabled
              title="Load Pattern will return once profiles are managed via the gateway."
              style={{
                padding: '10px 20px',
                borderRadius: '8px',
                fontWeight: '600',
                cursor: 'not-allowed',
                fontSize: '14px',
                background: '#111111',
                color: '#f59e0b',
                border: '1px solid #f59e0b',
                display: 'flex',
                alignItems: 'center',
                gap: '6px',
                opacity: 0.5
              }}>
              <div style={{ display: 'flex', flexDirection: 'column', gap: '4px', alignItems: 'center' }}>
                <span>dY"? Load Pattern</span>
                <ComingSoonTag />
              </div>
            </button>
          </div>
          <div style={{ display: 'flex', alignItems: 'center', gap: '16px', color: '#d1d5db', fontSize: '13px' }}>
            <div style={{ display: 'flex', alignItems: 'center', gap: '8px' }}>
              <div style={{ width: '8px', height: '8px', borderRadius: '50%', background: '#9333ea' }}></div>
              <span>LEDBlinky Connected</span>
            </div>
            <div>
              <span>Last Sync: Never</span>
            </div>
          </div>
        </div>

        {/* Minimal AI Chat (wired to aiClient) */}
        <div style={{ padding: '16px 24px', background: '#0f0f0f', borderTop: '1px solid #9333ea' }}>
          <div style={{ marginBottom: '8px', color: '#9333ea', fontWeight: 700 }}>AI Assistant</div>
          <ChatBox />
        </div>
      </div>
    </div >
  )
}

export default LEDBlinkyPanel

import React, { useCallback, useEffect, useMemo, useRef, useState } from 'react'
import { useNavigate, useLocation } from 'react-router-dom'
import { chat as aiChat } from '../../services/aiClient'
import './consoleWizard.css'

const STORAGE_KEY = 'console-wizard-mappings'

const DEFAULT_DEVICES = [
  { name: '8BitDo SN30 Pro (2dc8:6101)', safety: 'safe' },
  { name: 'Xbox One Controller', safety: 'safe' },
  { name: 'PlayStation 5 DualSense', safety: 'safe' },
  { name: 'PlayStation 4 DualShock 4', safety: 'safe' },
  { name: 'Xbox Series X Controller', safety: 'safe' },
  { name: 'Nintendo Switch Pro Controller', safety: 'safe' },
  { name: 'SNES USB Controller (Clone)', safety: 'safe' },
  { name: 'Generic USB Gamepad', safety: 'safe' }
]

const EMULATOR_PRESETS = [
  { value: 'retroarch', label: 'RetroArch' },
  { value: 'mame', label: 'MAME' },
  { value: 'dolphin', label: 'Dolphin (GameCube/Wii)' },
  { value: 'pcsx2', label: 'PCSX2 (PlayStation 2)' },
  { value: 'project64', label: 'Project64 (Nintendo 64)' },
  { value: 'duckstation', label: 'DuckStation (PlayStation 1)' },
  { value: 'epsxe', label: 'ePSXe (PlayStation 1)' },
  { value: 'ppsspp', label: 'PPSSPP (PlayStation Portable)' },
  { value: 'rpcs3', label: 'RPCS3 (PlayStation 3)' },
  { value: 'xenia', label: 'Xenia (Xbox 360)' },
  { value: 'xemu', label: 'Xemu (Original Xbox)' },
  { value: 'yuzu', label: 'Yuzu (Nintendo Switch)' },
  { value: 'ryujinx', label: 'Ryujinx (Nintendo Switch)' },
  { value: 'cemu', label: 'Cemu (Wii U)' },
  { value: 'redream', label: 'Redream (Dreamcast)' },
  { value: 'flycast', label: 'Flycast (Dreamcast)' },
  { value: 'teknoparrot', label: 'TeknoParrot (Modern Arcade)' },
  { value: 'fbneo', label: 'FBNeo (Arcade)' },
  { value: 'mupen64plus', label: 'Mupen64Plus (Nintendo 64)' },
  { value: 'melonds', label: 'melonDS (Nintendo DS)' },
  { value: 'desmume', label: 'DeSmuME (Nintendo DS)' },
  { value: 'mgba', label: 'mGBA (Game Boy Advance)' },
  { value: 'snes9x', label: 'Snes9x (Super Nintendo)' },
  { value: 'bsnes', label: 'bsnes (Super Nintendo)' },
  { value: 'nestopia', label: 'Nestopia (NES)' },
  { value: 'fceux', label: 'FCEUX (NES)' }
]

const ALL_INPUT_KEYS = [
  'D-UP','D-DOWN','D-LEFT','D-RIGHT',
  'LS-UP','LS-DOWN','LS-LEFT','LS-RIGHT','L3',
  'RS-UP','RS-DOWN','RS-LEFT','RS-RIGHT','R3',
  'A','B','X','Y',
  'L1','R1','L2','R2',
  'START','SELECT','HOME'
]

const EMULATOR_CONFIG_KEYS = {
  retroarch: {
    'D-UP': 'input_up_btn', 'D-DOWN': 'input_down_btn', 'D-LEFT': 'input_left_btn', 'D-RIGHT': 'input_right_btn',
    'LS-UP': 'input_l_y_minus_axis', 'LS-DOWN': 'input_l_y_plus_axis', 'LS-LEFT': 'input_l_x_minus_axis', 'LS-RIGHT': 'input_l_x_plus_axis',
    'RS-UP': 'input_r_y_minus_axis', 'RS-DOWN': 'input_r_y_plus_axis', 'RS-LEFT': 'input_r_x_minus_axis', 'RS-RIGHT': 'input_r_x_plus_axis',
    'A': 'input_a_btn', 'B': 'input_b_btn', 'X': 'input_x_btn', 'Y': 'input_y_btn',
    'L1': 'input_l_btn', 'R1': 'input_r_btn', 'L2': 'input_l2_btn', 'R2': 'input_r2_btn',
    'L3': 'input_l3_btn', 'R3': 'input_r3_btn',
    'START': 'input_start_btn', 'SELECT': 'input_select_btn', 'HOME': 'input_menu_toggle_btn'
  },
  mame: {
    'D-UP': 'P1_JOYSTICK_UP', 'D-DOWN': 'P1_JOYSTICK_DOWN', 'D-LEFT': 'P1_JOYSTICK_LEFT', 'D-RIGHT': 'P1_JOYSTICK_RIGHT',
    'A': 'P1_BUTTON1', 'B': 'P1_BUTTON2', 'X': 'P1_BUTTON3', 'Y': 'P1_BUTTON4',
    'L1': 'P1_BUTTON5', 'R1': 'P1_BUTTON6', 'L2': 'P1_BUTTON7', 'R2': 'P1_BUTTON8',
    'START': 'P1_START', 'SELECT': 'COIN1'
  }
}

function Section({ title, children }) {
  return (
    <div className="mapping-section">
      <div className="section-header">{title}</div>
      {children}
    </div>
  )
}

export default function ConsoleWizard() {
  const navigate = useNavigate()
  const location = useLocation()
  const params = new URLSearchParams(location.search)
  const openChatInitially = params.get('chat') === '1'

  const [devices, setDevices] = useState(DEFAULT_DEVICES)
  const [selectedDeviceIndex, setSelectedDeviceIndex] = useState(0)
  const [currentPlayer, setCurrentPlayer] = useState(1)
  const [emulatorPreset, setEmulatorPreset] = useState('retroarch')
  const [chatOpen, setChatOpen] = useState(openChatInitially)

  const DEFAULT_MAP = {
    'D-UP': 'hat0up', 'D-DOWN': 'hat0down', 'D-LEFT': 'hat0left', 'D-RIGHT': 'hat0right',
    'LS-UP': '-axis1', 'LS-DOWN': '+axis1', 'LS-LEFT': '-axis0', 'LS-RIGHT': '+axis0', 'L3': 'btn10',
    'RS-UP': '-axis4', 'RS-DOWN': '+axis4', 'RS-LEFT': '-axis3', 'RS-RIGHT': '+axis3', 'R3': 'btn11',
    'A': 'btn0', 'B': 'btn1', 'X': 'btn2', 'Y': 'btn3',
    'L1': 'btn4', 'R1': 'btn5', 'L2': 'axis2', 'R2': 'axis5',
    'START': 'btn9', 'SELECT': 'btn8', 'HOME': 'btn12'
  }
  const [mappings, setMappings] = useState(() => ({
    1: { ...DEFAULT_MAP }, 2: { ...DEFAULT_MAP }, 3: { ...DEFAULT_MAP }, 4: { ...DEFAULT_MAP }
  }))

  const [capturingKey, setCapturingKey] = useState(null)
  const [selectedInputKey, setSelectedInputKey] = useState(null)
  const [appliedKeys, setAppliedKeys] = useState([])
  const [pressedButtons, setPressedButtons] = useState(new Set()) // Track currently pressed buttons
  const prevPlayerRef = useRef(currentPlayer)

  const isKeySupported = useCallback((k) => {
    const map = EMULATOR_CONFIG_KEYS[emulatorPreset]
    return !map || !!map[k]
  }, [emulatorPreset])

  const updateMapping = useCallback((key, value) => {
    setMappings(prev => ({
      ...prev,
      [currentPlayer]: { ...prev[currentPlayer], [key]: value }
    }))
  }, [currentPlayer])

  const selectedDevice = useMemo(() => devices[selectedDeviceIndex], [devices, selectedDeviceIndex])

  const closePanel = useCallback(() => {
    navigate('/')
  }, [navigate])

  // Auto-load devices on component mount
  useEffect(() => {
    const loadDevices = async () => {
      try {
        const res = await fetch('/api/local/console/controllers')
        const data = await res.json()
        
        if (res.ok && data.controllers?.length > 0) {
          // Update devices list with real detected controllers
          const detectedDevices = data.controllers.map(c => ({
            name: c.name || c.id || 'Unknown Controller',
            safety: 'safe',
            vid: c.vid,
            pid: c.pid,
            detected: true
          }))
          setDevices(detectedDevices)
        }
      } catch (err) {
        // Silently fail on mount - user can click Scan Devices to retry
        console.log('Auto-load controllers failed (non-critical):', err.message)
      }
    }
    
    loadDevices()
  }, [])

  // Auto-save mappings to localStorage whenever they change
  useEffect(() => {
    try {
      const raw = localStorage.getItem(STORAGE_KEY)
      const db = raw ? JSON.parse(raw) : {}
      db[emulatorPreset] = db[emulatorPreset] || {}
      db[emulatorPreset][`P${currentPlayer}`] = mappings[currentPlayer]
      localStorage.setItem(STORAGE_KEY, JSON.stringify(db))
      console.log(`Auto-saved ${emulatorPreset} P${currentPlayer} mappings`)
    } catch (e) {
      console.error('Auto-save failed', e)
    }
  }, [mappings, currentPlayer, emulatorPreset])

  // Chat state
  const [messages, setMessages] = useState([
    { type: 'assistant', content: "Hello! I'm here to help you configure your controllers. Click any input field to see a visual guide, or ask me anything!" }
  ])
  const [chatInput, setChatInput] = useState('')
  const [micRecording, setMicRecording] = useState(false)
  const chatContainerRef = useRef(null)
  const chatInputRef = useRef(null)

  const sendChat = useCallback(async () => {
    const content = chatInput.trim()
    if (!content) return
    setMessages(prev => [...prev, { type: 'user', content }])
    setChatInput('')
    try {
      const res = await aiChat({
        provider: 'claude',
        messages: [
          { role: 'system', content: 'You are a console controller setup assistant. Help with presets and mapping succinctly.' },
          { role: 'user', content }
        ],
        metadata: { panel: 'controller-wizard', action: 'help' },
        scope: 'state',
        deviceId: 'demo_001'
      })
      const reply = res?.message?.content || '[No response]'
      setMessages(prev => [...prev, { type: 'assistant', content: reply }])
    } catch (e) {
      setMessages(prev => [...prev, { type: 'assistant', content: 'If a mapping is not detected, press and hold the input for 2 seconds or verify the device connection.' }])
    }
  }, [chatInput])

  const onKeyDownChat = useCallback((e) => {
    if (e.key === 'Enter' && !e.shiftKey) {
      e.preventDefault()
      sendChat()
    }
  }, [sendChat])

  // Auto-scroll chat to bottom on new messages
  useEffect(() => {
    if (chatContainerRef.current) {
      chatContainerRef.current.scrollTop = chatContainerRef.current.scrollHeight
    }
  }, [messages, chatOpen])

  // Auto-resize textarea
  useEffect(() => {
    if (!chatInputRef.current) return
    chatInputRef.current.style.height = 'auto'
    chatInputRef.current.style.height = Math.min(chatInputRef.current.scrollHeight, 120) + 'px'
  }, [chatInput])

  const handleToggleMic = useCallback(() => {
    setMicRecording(prev => {
      const next = !prev
      setMessages(m => [
        ...m,
        { type: 'assistant', content: next ? 'Voice recording started...' : 'Voice recording stopped.' }
      ])
      return next
    })
  }, [])

  const saveProfile = useCallback(() => {
    try {
      const raw = localStorage.getItem(STORAGE_KEY)
      const db = raw ? JSON.parse(raw) : {}
      db[emulatorPreset] = db[emulatorPreset] || {}
      db[emulatorPreset][`P${currentPlayer}`] = mappings[currentPlayer]
      localStorage.setItem(STORAGE_KEY, JSON.stringify(db))
      alert(`Saved ${emulatorPreset} profile for P${currentPlayer}`)
    } catch (e) {
      console.error('Save failed', e)
      alert('Failed to save locally')
    }
  }, [currentPlayer, emulatorPreset, mappings])

  const exportConfig = useCallback(() => {
    const cfg = {}
    const keyMap = EMULATOR_CONFIG_KEYS[emulatorPreset] || {}
    ALL_INPUT_KEYS.forEach(k => {
      const targetKey = keyMap[k]
      const val = mappings[currentPlayer][k]
      if (targetKey) cfg[targetKey] = val
      else cfg[k] = val
    })
    const blob = new Blob([JSON.stringify({ emulator: emulatorPreset, player: currentPlayer, device: selectedDevice?.name, mappings: cfg }, null, 2)], { type: 'application/json' })
    const url = URL.createObjectURL(blob)
    const a = document.createElement('a')
    a.href = url
    a.download = `controller-profile-P${currentPlayer}-${emulatorPreset}.json`
    document.body.appendChild(a)
    a.click()
    a.remove()
    URL.revokeObjectURL(url)
  }, [currentPlayer, emulatorPreset, selectedDevice, mappings])

  const testInputs = useCallback(() => {
    // Use Gamepad API to detect button presses in real-time
    const pollGamepad = (prevState = { buttons: {}, axes: {} }) => {
      const gamepads = navigator.getGamepads && navigator.getGamepads()
      if (!gamepads) {
        console.warn('Gamepad API not available')
        return { buttons: {}, axes: {} }
      }
      
      const currentState = { buttons: {}, axes: {} }
      
      // Map button indices to key names
      const BUTTON_MAP = {
        0: 'A',        // Y button on some controllers
        1: 'B',        // X button on some controllers
        2: 'X',        // A button on some controllers
        3: 'Y',        // B button on some controllers
        4: 'L1',       // LB
        5: 'R1',       // RB
        12: 'D-UP',
        13: 'D-DOWN',
        14: 'D-LEFT',
        15: 'D-RIGHT',
        8: 'SELECT',   // Back
        9: 'START',    // Start
        10: 'L3',      // Left stick click
        11: 'R3',      // Right stick click
        16: 'HOME'     // Xbox button / Home
      }
      
      const AXIS_MAP = {
        0: { positive: 'RS-RIGHT', negative: 'RS-LEFT' },
        1: { positive: 'RS-DOWN', negative: 'RS-UP' },
        2: { negative: 'L2' },     // L2 is -1 when pressed
        3: { positive: 'LS-RIGHT', negative: 'LS-LEFT' },
        4: { positive: 'LS-DOWN', negative: 'LS-UP' },
        5: { negative: 'R2' }      // R2 is -1 when pressed
      }
      
      for (let i = 0; i < gamepads.length; i++) {
        const gamepad = gamepads[i]
        if (!gamepad) continue
        
        // Check buttons
        for (let j = 0; j < gamepad.buttons.length; j++) {
          const btn = gamepad.buttons[j]
          const pressed = typeof btn === 'object' ? btn.pressed : btn === 1.0
          if (BUTTON_MAP[j]) {
            currentState.buttons[BUTTON_MAP[j]] = pressed
          }
        }
        
        // Check axes (analog sticks and triggers)
        if (gamepad.axes) {
          for (let j = 0; j < gamepad.axes.length; j++) {
            const value = gamepad.axes[j]
            const axisConfig = AXIS_MAP[j]
            
            if (axisConfig) {
              // For triggers (axes 2 and 5), they range from 0 (not pressed) to 1 (fully pressed)
              if (j === 2 || j === 5) {
                // Triggers: pressed when value < -0.5 (negative)
                const pressed = value < -0.5
                if (axisConfig.negative) {
                  currentState.buttons[axisConfig.negative] = pressed
                }
              } else {
                // Sticks: positive direction when > 0.5, negative direction when < -0.5
                if (value > 0.5 && axisConfig.positive) {
                  currentState.buttons[axisConfig.positive] = true
                }
                if (value < -0.5 && axisConfig.negative) {
                  currentState.buttons[axisConfig.negative] = true
                }
              }
            }
          }
        }
      }
      
      return currentState
    }
    
    // Gamepad connected/disconnected event listeners
    const handleGamepadConnected = (e) => {
      console.log('Gamepad connected:', e.gamepad.id)
    }
    
    const handleGamepadDisconnected = (e) => {
      console.log('Gamepad disconnected:', e.gamepad.id)
    }
    
    window.addEventListener('gamepadconnected', handleGamepadConnected)
    window.addEventListener('gamepaddisconnected', handleGamepadDisconnected)
    
    // Collect input events over time
    const inputs = new Set()
    const pollInterval = 50 // ms
    const totalTime = 5000 // ms
    const startTime = Date.now()
    let prevState = { buttons: {}, axes: {} }
    let testComplete = false
    
    const poll = () => {
      const currentState = pollGamepad(prevState)
      
      // Update pressed buttons visualization
      const pressed = new Set()
      Object.entries(currentState.buttons).forEach(([key, isPressed]) => {
        if (isPressed) {
          pressed.add(key)
          inputs.add(key) // Track any button that was pressed
        }
      })
      setPressedButtons(pressed)
      
      prevState = currentState
      
      const elapsed = Date.now() - startTime
      if (elapsed < totalTime && !testComplete) {
        setTimeout(poll, pollInterval)
      } else if (elapsed >= totalTime && !testComplete) {
        testComplete = true
        // Clean up event listeners
        window.removeEventListener('gamepadconnected', handleGamepadConnected)
        window.removeEventListener('gamepaddisconnected', handleGamepadDisconnected)
        
        // Clear pressed buttons visualization
        setPressedButtons(new Set())
        
        // Display results
        if (inputs.size > 0) {
          const inputList = Array.from(inputs).slice(0, 25).join(', ')
          alert(`✅ Success! Detected ${inputs.size} unique button(s):\n\n${inputList}${inputs.size > 25 ? '\n... and more' : ''}`)
        } else {
          alert('❌ No input detected in 5 seconds.\n\nTroubleshooting:\n1. Make sure controller is connected and turned on\n2. Press buttons DURING the test\n3. Some browsers may require interaction before detecting gamepads\n4. Try pressing a button now, then run the test again')
        }
      }
    }
    
    alert('🎮 Testing controller inputs...\n\nPress buttons on your controller now!\nThe test will run for 5 seconds.\n\nButtons will light up when pressed and go dark when released.')
    poll()
  }, [])

  const scanDevices = useCallback(async () => {
    try {
      const res = await fetch('/api/local/console/controllers')
      const data = await res.json()

      if (res.ok && data.controllers?.length > 0) {
        // Update devices list with real detected controllers
        const detectedDevices = data.controllers.map(c => ({
          name: c.name || c.id || 'Unknown Controller',
          safety: 'safe',
          vid: c.vid,
          pid: c.pid,
          detected: true
        }))
        setDevices(detectedDevices)
        setSelectedDeviceIndex(0)
        alert(`Found ${data.controllers.length} controller(s):\n${data.controllers.map(c => c.name || c.id).join('\n')}`)
      } else if (!res.ok && data.detail?.message) {
        // Backend returned an error (e.g., USB not available)
        alert(`Controller detection unavailable:\n\n${data.detail.message}\n\nYou can still configure mappings manually using the default device list.`)
      } else {
        alert('No controllers detected. On WSL, USB detection may not work. You can still configure mappings manually.')
      }
    } catch (err) {
      console.error('Scan devices error:', err)
      alert(`Device scan failed: ${err.message}\n\nNote: Backend must be running on port 8000`)
    }
  }, [])

  const loadProfile = useCallback(() => {
    try {
      const raw = localStorage.getItem(STORAGE_KEY)
      const db = raw ? JSON.parse(raw) : {}
      const data = db?.[emulatorPreset]?.[`P${currentPlayer}`]
      if (data) {
        setMappings(prev => ({ ...prev, [currentPlayer]: { ...prev[currentPlayer], ...data } }))
        alert(`Loaded ${emulatorPreset} profile for P${currentPlayer}`)
      } else {
        alert('No saved profile found for this emulator/player')
      }
    } catch (e) {
      console.error('Load failed', e)
      alert('Failed to load locally')
    }
  }, [currentPlayer, emulatorPreset])

  const copyPlayerConfig = useCallback(() => {
    setMappings(prev => ({ 1: prev[currentPlayer], 2: prev[currentPlayer], 3: prev[currentPlayer], 4: prev[currentPlayer] }))
    alert(`Copied Player ${currentPlayer} mapping to all players`)
  }, [currentPlayer])

  const validateMapping = useCallback(() => {
    const map = mappings[currentPlayer]
    const requiredKeys = Object.keys(EMULATOR_CONFIG_KEYS[emulatorPreset] || {}).length
      ? Object.keys(EMULATOR_CONFIG_KEYS[emulatorPreset])
      : ALL_INPUT_KEYS

    const warnings = []
    const errors = []
    const seen = new Map()

    requiredKeys.forEach(k => {
      const v = String(map[k] || '').trim()
      if (!v) warnings.push(`${k} is not mapped`)
      else if (seen.has(v)) errors.push(`Duplicate mapping: ${v}`)
      else seen.set(v, k)
    })

    let message = `Validation Results:\nPlayer ${currentPlayer}\n\n`
    if (errors.length === 0 && warnings.length === 0) {
      message += ' Perfect! Configuration is ready.'
    } else {
      if (errors.length > 0) message += ` Errors:\n${errors.join('\n')}\n\n`
      if (warnings.length > 0) message += ` Warnings:\n${warnings.join('\n')}`
    }
    alert(message)
  }, [mappings, currentPlayer, emulatorPreset])

  const dryRun = useCallback(() => {
    alert('Dry run complete (mock). Changes look valid.')
  }, [])

  const applyChanges = useCallback(async () => {
    if (emulatorPreset !== 'retroarch') {
      alert(`Apply is currently only supported for RetroArch.\n\nFor ${emulatorPreset}, use Export to save your configuration.`)
      return
    }

    try {
      // For RetroArch, we can use the backend API
      // Note: This requires matching the current mappings to a known profile
      // For now, we'll show a message explaining the limitation
      alert(`To apply RetroArch configs:\n\n1. Use "Save Profile" to save your current mappings\n2. Navigate to /console-wizard\n3. Select the matching controller profile\n4. Use the wizard to generate the RetroArch config\n\nDirect apply from this interface will be available in a future update.`)
    } catch (err) {
      console.error('Apply changes error:', err)
      alert(`Failed to apply: ${err.message}`)
    }
  }, [emulatorPreset])

  const resetMappings = useCallback(() => {
    setMappings(prev => ({ ...prev, [currentPlayer]: { ...DEFAULT_MAP } }))
  }, [currentPlayer])

  // Autosave previous player's mapping and autoload new player's saved profile
  useEffect(() => {
    const prev = prevPlayerRef.current
    if (prev !== currentPlayer) {
      try {
        // Save previous
        const raw = localStorage.getItem(STORAGE_KEY)
        const db = raw ? JSON.parse(raw) : {}
        db[emulatorPreset] = db[emulatorPreset] || {}
        db[emulatorPreset][`P${prev}`] = mappings[prev]
        localStorage.setItem(STORAGE_KEY, JSON.stringify(db))
      } catch {}

      // Load new
      try {
        const raw = localStorage.getItem(STORAGE_KEY)
        const db = raw ? JSON.parse(raw) : {}
        const data = db?.[emulatorPreset]?.[`P${currentPlayer}`]
        if (data) {
          setMappings(prevMap => ({ ...prevMap, [currentPlayer]: { ...prevMap[currentPlayer], ...data } }))
          setAppliedKeys(Object.keys(data))
          const t = setTimeout(() => setAppliedKeys([]), 800)
          return () => clearTimeout(t)
        }
      } catch {}
    }
    prevPlayerRef.current = currentPlayer
  }, [currentPlayer, emulatorPreset])

  const startMapping = useCallback((key) => {
    setCapturingKey(key)
    setSelectedInputKey(key)
    // Simulated capture after delay
    setTimeout(() => {
      const demo = key.startsWith('D-') ? 'hat0' + key.split('-')[1].toLowerCase() : key.startsWith('LS-') ? (key.includes('LEFT')?'-axis0':key.includes('RIGHT')?'+axis0':key.includes('UP')?'-axis1':'+axis1') : key.startsWith('RS-') ? (key.includes('LEFT')?'-axis3':key.includes('RIGHT')?'+axis3':key.includes('UP')?'-axis4':'+axis4') : key === 'L3' ? 'btn10' : key === 'R3' ? 'btn11' : key === 'A' ? 'btn0' : key === 'B' ? 'btn1' : key === 'X' ? 'btn2' : key === 'Y' ? 'btn3' : key === 'L1' ? 'btn4' : key === 'R1' ? 'btn5' : key === 'L2' ? 'axis2' : key === 'R2' ? 'axis5' : key === 'START' ? 'btn9' : key === 'SELECT' ? 'btn8' : key === 'HOME' ? 'btn12' : ''
      if (demo) updateMapping(key, demo)
      setCapturingKey(null)
    }, 1000)
  }, [updateMapping])

  // On emulator preset change: clear unsupported keys and briefly highlight the affected fields
  useEffect(() => {
    const map = EMULATOR_CONFIG_KEYS[emulatorPreset]
    const affected = []
    if (map) {
      setMappings(prev => {
        const next = { ...prev }
        const cur = { ...next[currentPlayer] }
        ALL_INPUT_KEYS.forEach(k => {
          if (!map[k] && cur[k]) {
            cur[k] = ''
            affected.push(k)
          }
        })
        next[currentPlayer] = cur
        return next
      })
    }
    if (affected.length) {
      setAppliedKeys(affected)
      const t = setTimeout(() => setAppliedKeys([]), 800)
      return () => clearTimeout(t)
    }
  }, [emulatorPreset, currentPlayer])

  const emulatorPresetLabel = useMemo(() => EMULATOR_PRESETS.find(p => p.value === emulatorPreset)?.label || emulatorPreset, [emulatorPreset])
  const getConfigKey = useCallback((k) => (EMULATOR_CONFIG_KEYS[emulatorPreset] || {})[k] || null, [emulatorPreset])
  const shortDeviceName = useMemo(() => {
    const n = selectedDevice?.name || ''
    return n.split(' ').slice(0, 3).join(' ')
  }, [selectedDevice])

  return (
    <div className="console-wizard">
      <div className="panel-overlay">
        <div className="panel-container">
            <div className="header-bar">
            <div className="header-title">
              <span>Console Controller Wizard</span>
              <span className="wizard-pill">Console / Emulators</span>
            </div>
            <div className="header-actions">
              <button className="close-btn" onClick={closePanel} title="Close">✕</button>
            </div>
          </div>

          <div className="content-area">
            <div className="wizard-subtitle">Emulator profiles and console mapping. For arcade mapping use Control Panel.</div>
            <div className="controller-grid">
              {/* Left: Devices + Presets */}
              <div className="controller-panel">
                <div className="panel-header">
                  <div className="panel-title">Connected Devices</div>
                  <div className="panel-controls">
                    <div className="player-tabs">
                      {[1,2,3,4].map(n => (
                        <button
                          key={n}
                          className={`player-tab ${currentPlayer === n ? 'active' : ''}`}
                          onClick={() => setCurrentPlayer(n)}
                        >
                          P{n}
                        </button>
                      ))}
                    </div>
                    <select
                      id="emulator-preset"
                      value={emulatorPreset}
                      onChange={e => setEmulatorPreset(e.target.value)}
                    >
                      {EMULATOR_PRESETS.map(p => (
                        <option key={p.value} value={p.value}>{p.label}</option>
                      ))}
                    </select>
                  </div>
                </div>

                <div className="device-list">
                  {devices.map((d, i) => (
                    <div
                      key={d.name}
                      className={`device-item ${i === selectedDeviceIndex ? 'selected' : ''}`}
                      onClick={() => setSelectedDeviceIndex(i)}
                    >
                      <span className={`safety-icon ${d.safety}`}>●</span>
                      <span>{d.name}</span>
                    </div>
                  ))}
                </div>

                <div className="visual-graphic" id="visual-guide" style={{ marginTop: 8, textAlign: 'center', padding: 15, minHeight: 120, display: 'flex', alignItems: 'center', justifyContent: 'center', flexDirection: 'column', background: 'rgba(0,0,0,0.2)', borderRadius: 6 }}>
                  {!selectedInputKey && <div style={{ color: '#666', fontSize: 12 }}>Click any input to see visual guide</div>}
                  {selectedInputKey && (
                    <>
                      {selectedInputKey.startsWith('D-') && (
                        <>
                          <div style={{ color: '#14c27a', fontSize: 13, marginBottom: 10, fontWeight: 'bold' }}>D-Pad {selectedInputKey.split('-')[1]}</div>
                          <div className="visual-graphic dpad-visual">
                            <div className={`dpad-arrow ${pressedButtons.has('D-UP') ? 'active' : ''}`} style={{ top: 0, left: 35, borderRadius: '4px 4px 0 0' }} />
                            <div className={`dpad-arrow ${pressedButtons.has('D-DOWN') ? 'active' : ''}`} style={{ bottom: 0, left: 35, borderRadius: '0 0 4px 4px' }} />
                            <div className={`dpad-arrow ${pressedButtons.has('D-LEFT') ? 'active' : ''}`} style={{ left: 0, top: 35, borderRadius: '4px 0 0 4px' }} />
                            <div className={`dpad-arrow ${pressedButtons.has('D-RIGHT') ? 'active' : ''}`} style={{ right: 0, top: 35, borderRadius: '0 4px 4px 0' }} />
                            <div style={{ position: 'absolute', width: 30, height: 30, background: 'rgba(20, 194, 122, 0.1)', border: '2px solid #14c27a', top: 35, left: 35 }} />
                          </div>
                        </>
                      )}

                      {(selectedInputKey.startsWith('LS-') || selectedInputKey === 'L3') && (
                        <>
                          <div style={{ color: '#14c27a', fontSize: 13, marginBottom: 10, fontWeight: 'bold' }}>{selectedInputKey === 'L3' ? 'Left Stick Press' : `Left Stick ${selectedInputKey.split('-')[1]}`}</div>
                          <div className="visual-graphic stick-visual" style={{ position: 'relative', width: 100, height: 100, margin: '0 auto' }}>
                            <div style={{ position: 'absolute', width: 8, height: 40, background: pressedButtons.has('LS-UP') ? '#14c27a' : 'rgba(20, 194, 122, 0.2)', top: 10, left: '50%', transform: 'translateX(-50%)', borderRadius: 4 }} />
                            <div style={{ position: 'absolute', width: 8, height: 40, background: pressedButtons.has('LS-DOWN') ? '#14c27a' : 'rgba(20, 194, 122, 0.2)', bottom: 10, left: '50%', transform: 'translateX(-50%)', borderRadius: 4 }} />
                            <div style={{ position: 'absolute', width: 40, height: 8, background: pressedButtons.has('LS-LEFT') ? '#14c27a' : 'rgba(20, 194, 122, 0.2)', left: 10, top: '50%', transform: 'translateY(-50%)', borderRadius: 4 }} />
                            <div style={{ position: 'absolute', width: 40, height: 8, background: pressedButtons.has('LS-RIGHT') ? '#14c27a' : 'rgba(20, 194, 122, 0.2)', right: 10, top: '50%', transform: 'translateY(-50%)', borderRadius: 4 }} />
                            <div style={{ position: 'absolute', width: 30, height: 30, background: pressedButtons.has('L3') ? '#14c27a' : 'rgba(20, 194, 122, 0.3)', borderRadius: '50%', top: '50%', left: '50%', transform: 'translate(-50%, -50%)', border: '2px solid #14c27a', boxShadow: pressedButtons.has('L3') ? '0 0 20px rgba(20,194,122,0.8)' : '0 0 10px rgba(20,194,122,0.3)' }} />
                          </div>
                        </>
                      )}

                      {(selectedInputKey.startsWith('RS-') || selectedInputKey === 'R3') && (
                        <>
                          <div style={{ color: '#14c27a', fontSize: 13, marginBottom: 10, fontWeight: 'bold' }}>{selectedInputKey === 'R3' ? 'Right Stick Press' : `Right Stick ${selectedInputKey.split('-')[1]}`}</div>
                          <div className="visual-graphic stick-visual" style={{ position: 'relative', width: 100, height: 100, margin: '0 auto' }}>
                            <div style={{ position: 'absolute', width: 8, height: 40, background: pressedButtons.has('RS-UP') ? '#14c27a' : 'rgba(20, 194, 122, 0.2)', top: 10, left: '50%', transform: 'translateX(-50%)', borderRadius: 4 }} />
                            <div style={{ position: 'absolute', width: 8, height: 40, background: pressedButtons.has('RS-DOWN') ? '#14c27a' : 'rgba(20, 194, 122, 0.2)', bottom: 10, left: '50%', transform: 'translateX(-50%)', borderRadius: 4 }} />
                            <div style={{ position: 'absolute', width: 40, height: 8, background: pressedButtons.has('RS-LEFT') ? '#14c27a' : 'rgba(20, 194, 122, 0.2)', left: 10, top: '50%', transform: 'translateY(-50%)', borderRadius: 4 }} />
                            <div style={{ position: 'absolute', width: 40, height: 8, background: pressedButtons.has('RS-RIGHT') ? '#14c27a' : 'rgba(20, 194, 122, 0.2)', right: 10, top: '50%', transform: 'translateY(-50%)', borderRadius: 4 }} />
                            <div style={{ position: 'absolute', width: 30, height: 30, background: pressedButtons.has('R3') ? '#14c27a' : 'rgba(20, 194, 122, 0.3)', borderRadius: '50%', top: '50%', left: '50%', transform: 'translate(-50%, -50%)', border: '2px solid #14c27a', boxShadow: pressedButtons.has('R3') ? '0 0 20px rgba(20,194,122,0.8)' : '0 0 10px rgba(20,194,122,0.3)' }} />
                          </div>
                        </>
                      )}

                      {(['A', 'B', 'X', 'Y'].includes(selectedInputKey)) && (
                        <>
                          <div style={{ color: '#14c27a', fontSize: 13, marginBottom: 10, fontWeight: 'bold' }}>Face Button {selectedInputKey}</div>
                          <div className="visual-graphic" style={{ position: 'relative', width: 120, height: 120, margin: '0 auto' }}>
                            <div className={`button-visual ${pressedButtons.has('Y') ? 'active' : ''}`} style={{ position: 'absolute', top: 0, left: 40 }}>
                              <span style={{ position: 'absolute', top: '50%', left: '50%', transform: 'translate(-50%, -50%)', color: '#14c27a', fontWeight: 'bold' }}>Y</span>
                            </div>
                            <div className={`button-visual ${pressedButtons.has('X') ? 'active' : ''}`} style={{ position: 'absolute', top: 40, left: 0 }}>
                              <span style={{ position: 'absolute', top: '50%', left: '50%', transform: 'translate(-50%, -50%)', color: '#14c27a', fontWeight: 'bold' }}>X</span>
                            </div>
                            <div className={`button-visual ${pressedButtons.has('B') ? 'active' : ''}`} style={{ position: 'absolute', top: 40, right: 0 }}>
                              <span style={{ position: 'absolute', top: '50%', left: '50%', transform: 'translate(-50%, -50%)', color: '#14c27a', fontWeight: 'bold' }}>B</span>
                            </div>
                            <div className={`button-visual ${pressedButtons.has('A') ? 'active' : ''}`} style={{ position: 'absolute', bottom: 0, left: 40 }}>
                              <span style={{ position: 'absolute', top: '50%', left: '50%', transform: 'translate(-50%, -50%)', color: '#14c27a', fontWeight: 'bold' }}>A</span>
                            </div>
                          </div>
                        </>
                      )}

                      {(['L1', 'R1'].includes(selectedInputKey)) && (
                        <>
                          <div style={{ color: '#14c27a', fontSize: 13, marginBottom: 10, fontWeight: 'bold' }}>Shoulder Button {selectedInputKey}</div>
                          <div className="visual-graphic">
                            <div className={`trigger-visual ${pressedButtons.has('L1') ? 'active' : ''}`} style={{ display: 'inline-block', marginRight: 10 }}>
                              <span style={{ position: 'relative', top: 3, color: '#14c27a', fontSize: 11, fontWeight: 'bold' }}>L1</span>
                            </div>
                            <div className={`trigger-visual ${pressedButtons.has('R1') ? 'active' : ''}`} style={{ display: 'inline-block' }}>
                              <span style={{ position: 'relative', top: 3, color: '#14c27a', fontSize: 11, fontWeight: 'bold' }}>R1</span>
                            </div>
                          </div>
                        </>
                      )}

                      {(['L2', 'R2'].includes(selectedInputKey)) && (
                        <>
                          <div style={{ color: '#14c27a', fontSize: 13, marginBottom: 10, fontWeight: 'bold' }}>Trigger {selectedInputKey}</div>
                          <div className="visual-graphic">
                            <div className={`trigger-visual ${pressedButtons.has('L2') ? 'active' : ''}`} style={{ height: 40, display: 'inline-block', marginRight: 10 }}>
                              <span style={{ position: 'relative', top: 8, color: '#14c27a', fontSize: 11, fontWeight: 'bold' }}>L2</span>
                            </div>
                            <div className={`trigger-visual ${pressedButtons.has('R2') ? 'active' : ''}`} style={{ height: 40, display: 'inline-block' }}>
                              <span style={{ position: 'relative', top: 8, color: '#14c27a', fontSize: 11, fontWeight: 'bold' }}>R2</span>
                            </div>
                          </div>
                        </>
                      )}

                      {(['START', 'SELECT', 'HOME'].includes(selectedInputKey)) && (
                        <>
                          <div style={{ color: '#14c27a', fontSize: 13, marginBottom: 10, fontWeight: 'bold' }}>{selectedInputKey} Button</div>
                          <div className="visual-graphic">
                            <div className="button-visual active" style={{ width: 50, borderRadius: 8 }}>
                              <span style={{ position: 'absolute', top: '50%', left: '50%', transform: 'translate(-50%, -50%)', color: '#14c27a', fontSize: 10, fontWeight: 'bold' }}>{selectedInputKey}</span>
                            </div>
                          </div>
                        </>
                      )}
                    </>
                  )}
                </div>
              </div>

              {/* Right: Mapping Grid */}
              <div className="controller-panel">
                <div className="panel-header">
                  <div className="panel-title">{`${shortDeviceName}  ${emulatorPresetLabel}`}</div>
                  <div className="panel-controls">
                    <select
                      id="emulator-preset"
                      value={emulatorPreset}
                      onChange={e => setEmulatorPreset(e.target.value)}
                    >
                      {EMULATOR_PRESETS.map(p => (
                        <option key={p.value} value={p.value}>{p.label}</option>
                      ))}
                    </select>
                  </div>
                </div>
                <div className="mapping-grid">
                  <Section title="D-Pad">
                    {['D-UP','D-DOWN','D-LEFT','D-RIGHT'].map(k => (
                      <div className="mapping-row" key={k}>
                        <div className="input-label">
                          <div>{k}</div>
                          {getConfigKey(k) && <div className="config-key">{getConfigKey(k)}</div>}
                        </div>
                        <input
                          className={`input-field ${isKeySupported(k) ? '' : 'unsupported'} ${appliedKeys.includes(k) ? 'applied' : ''} ${capturingKey===k ? 'capturing' : ''} ${pressedButtons.has(k) ? 'button-pressed' : ''}`}
                          readOnly
                          value={mappings[currentPlayer][k]}
                          onClick={() => isKeySupported(k) && startMapping(k)}
                          onFocus={() => setSelectedInputKey(k)}
                          placeholder={capturingKey===k ? `Press input for ${k}...` : (getConfigKey(k) || '')}
                        />
                      </div>
                    ))}
                  </Section>

                  <Section title="Left Stick">
                    {['LS-UP','LS-DOWN','LS-LEFT','LS-RIGHT','L3'].map(k => (
                      <div className="mapping-row" key={k}>
                        <div className="input-label">{k}{getConfigKey(k) && <span className="config-key">{getConfigKey(k)}</span>}</div>
                        <input
                          className={`input-field ${isKeySupported(k) ? '' : 'unsupported'} ${appliedKeys.includes(k) ? 'applied' : ''} ${capturingKey===k ? 'capturing' : ''} ${pressedButtons.has(k) ? 'button-pressed' : ''}`}
                          readOnly
                          value={mappings[currentPlayer][k]}
                          onClick={() => isKeySupported(k) && startMapping(k)}
                          onFocus={() => setSelectedInputKey(k)}
                          placeholder={capturingKey===k ? `Press input for ${k}...` : (getConfigKey(k) || '')}
                        />
                      </div>
                    ))}
                  </Section>

                  <Section title="Right Stick">
                    {['RS-UP','RS-DOWN','RS-LEFT','RS-RIGHT','R3'].map(k => (
                      <div className="mapping-row" key={k}>
                        <div className="input-label">{k}{getConfigKey(k) && <span className="config-key">{getConfigKey(k)}</span>}</div>
                        <input
                          className={`input-field ${isKeySupported(k) ? '' : 'unsupported'} ${appliedKeys.includes(k) ? 'applied' : ''} ${capturingKey===k ? 'capturing' : ''} ${pressedButtons.has(k) ? 'button-pressed' : ''}`}
                          readOnly
                          value={mappings[currentPlayer][k]}
                          onClick={() => isKeySupported(k) && startMapping(k)}
                          onFocus={() => setSelectedInputKey(k)}
                          placeholder={capturingKey===k ? `Press input for ${k}...` : (getConfigKey(k) || '')}
                        />
                      </div>
                    ))}
                  </Section>

                  <Section title="Face Buttons">
                    {['A','B','X','Y'].map(k => (
                      <div className="mapping-row" key={k}>
                        <div className="input-label">{k}{getConfigKey(k) && <span className="config-key">{getConfigKey(k)}</span>}</div>
                        <input
                          className={`input-field ${isKeySupported(k) ? '' : 'unsupported'} ${appliedKeys.includes(k) ? 'applied' : ''} ${capturingKey===k ? 'capturing' : ''} ${pressedButtons.has(k) ? 'button-pressed' : ''}`}
                          readOnly
                          value={mappings[currentPlayer][k]}
                          onClick={() => isKeySupported(k) && startMapping(k)}
                          onFocus={() => setSelectedInputKey(k)}
                          placeholder={capturingKey===k ? `Press input for ${k}...` : (getConfigKey(k) || '')}
                        />
                      </div>
                    ))}
                  </Section>

                  <Section title="Shoulders & Triggers">
                    {['L1','R1','L2','R2'].map(k => (
                      <div className="mapping-row" key={k}>
                        <div className="input-label">{k}{getConfigKey(k) && <span className="config-key">{getConfigKey(k)}</span>}</div>
                        <input
                          className={`input-field ${isKeySupported(k) ? '' : 'unsupported'} ${appliedKeys.includes(k) ? 'applied' : ''} ${capturingKey===k ? 'capturing' : ''} ${pressedButtons.has(k) ? 'button-pressed' : ''}`}
                          readOnly
                          value={mappings[currentPlayer][k]}
                          onClick={() => isKeySupported(k) && startMapping(k)}
                          onFocus={() => setSelectedInputKey(k)}
                          placeholder={capturingKey===k ? `Press input for ${k}...` : (getConfigKey(k) || '')}
                        />
                      </div>
                    ))}
                  </Section>

                  <Section title="System">
                    {['START','SELECT','HOME'].map(k => (
                      <div className="mapping-row" key={k}>
                        <div className="input-label">{k}{getConfigKey(k) && <span className="config-key">{getConfigKey(k)}</span>}</div>
                        <input
                          className={`input-field ${isKeySupported(k) ? '' : 'unsupported'} ${pressedButtons.has(k) ? 'button-pressed' : ''}`}
                          readOnly
                          value={mappings[currentPlayer][k]}
                          onClick={() => isKeySupported(k) && startMapping(k)}
                          onFocus={() => setSelectedInputKey(k)}
                        />
                      </div>
                    ))}
                  </Section>
                </div>
              </div>
            </div>

            <div className="controls-bar">
              <button className="ctrl-btn" onClick={scanDevices}>Scan Devices</button>
              <button className="ctrl-btn" onClick={testInputs}>Test Inputs</button>
              <button className="ctrl-btn secondary" onClick={loadProfile}>Load Profile</button>
              <button className="ctrl-btn secondary" onClick={saveProfile}>Save Profile</button>
              <button className="ctrl-btn" onClick={copyPlayerConfig}>Copy to All Players</button>
              <button className="ctrl-btn" onClick={validateMapping}>Validate Mapping</button>
              <button className="ctrl-btn warning" onClick={dryRun}>Dry Run</button>
              <button className="ctrl-btn success" onClick={applyChanges}>Apply Changes</button>
              <button className="ctrl-btn secondary" onClick={exportConfig}>Export</button>
              <button className="ctrl-btn secondary" onClick={() => alert('Import (mock)')}>Import</button>
              <button className="ctrl-btn danger" onClick={resetMappings}>Reset</button>
            </div>
          </div>

          {/* Chat toggle and panel */}
          <button className="chat-toggle-btn" onClick={() => setChatOpen(true)} title="Open Assistant Chat">💬</button>
          <div className={`chat-panel ${chatOpen ? 'open' : ''}`}>
            <div className="chat-header">
              <div className="chat-header-title">Wizard Assistant</div>
              <button className="chat-close-btn" onClick={() => setChatOpen(false)} title="Close">✕</button>
            </div>
            <div className="chat-mascot-area">
              <img src="/wiz-avatar.jpeg" alt="Controller Wizard Mascot" className="wizard-mascot" />
            </div>
            <div className="chat-messages" ref={chatContainerRef}>
              {messages.map((m, i) => (
                <div key={i} className={`chat-message ${m.type}`}>{m.content}</div>
              ))}
            </div>
            <div className="chat-input-area">
              <div className="chat-input-container">
                <textarea
                  className="chat-input"
                  placeholder="Ask the wizard for help..."
                  value={chatInput}
                  onChange={e => setChatInput(e.target.value)}
                  onKeyDown={onKeyDownChat}
                  ref={chatInputRef}
                />
                <button className="chat-btn" onClick={sendChat} title="Send">➤</button>
                <button
                  className={`chat-btn mic-btn ${micRecording ? 'recording' : ''}`}
                  onClick={handleToggleMic}
                  title={micRecording ? 'Stop Recording' : 'Voice Input'}
                >
                  🎤
                </button>
              </div>
            </div>
          </div>
        </div>
      </div>
    </div>
  )
}

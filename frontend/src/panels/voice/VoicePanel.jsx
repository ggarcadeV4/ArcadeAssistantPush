import React, { useCallback, useEffect, useRef, useState, useMemo } from 'react'
import { PanelShell } from '../_kit'
import { EngineeringBaySidebar } from '../_kit/EngineeringBaySidebar'
import '../_kit/EngineeringBaySidebar.css'
import './voice.css'
import { getConsent, getPrimaryProfile, previewConsent, applyConsent, previewProfile, applyProfile } from '../../services/profileClient'
import { speakAsVicky, stopSpeaking } from '../../services/ttsClient'
import { startPlayerSession } from '../../services/playerTrackingClient'
import { chat as aiChat } from '../../services/aiClient'
import { useProfileContext } from '../../context/ProfileContext'
import { buildVickySystemPrompt } from './vickyPrompt'
import useGemSpeech from '../../hooks/useGemSpeech'
import { getGatewayUrl } from '../../services/gateway'

// Use gateway port 8787 in dev mode, or current origin in production
const GATEWAY = window.location.port === '5173' ? getGatewayUrl() : window.location.origin

// Helper functions - must be defined before component
const buildDefaultPlayers = () => ([
  { user: 'None', controller: 'Joystick 1' },
  { user: 'None', controller: 'Joystick 2' },
  { user: 'None', controller: 'Joystick 3' },
  { user: 'None', controller: 'Joystick 4' }
])

const createDefaultPreferences = () => ({
  voiceAssignments: {},
  vocabulary: '',
  players: buildDefaultPlayers()
})

const normalizePlayerId = (raw = '', fallback = 'guest') => {
  const source = String(raw || '').trim().toLowerCase()
  if (!source) return fallback
  const cleaned = source
    .replace(/\s+/g, '_')
    .replace(/[^a-z0-9_-]/g, '')
    .replace(/_+/g, '_')
    .replace(/^_+|_+$/g, '')
  return cleaned || fallback
}

const resolvePrimaryPlayerSlot = (players = [], displayName = '') => {
  const normalizedName = String(displayName || '').trim().toLowerCase()
  if (normalizedName) {
    const exactMatch = players.findIndex(player => String(player?.user || '').trim().toLowerCase() === normalizedName)
    if (exactMatch >= 0) return exactMatch
  }
  const assignedSeat = players.findIndex(player => {
    const user = String(player?.user || '').trim().toLowerCase()
    return user && user !== 'none' && user !== 'guest'
  })
  return assignedSeat >= 0 ? assignedSeat : 0
}

const toSessionPlayers = (players = []) => {
  const seats = []
  for (let index = 0; index < 4; index += 1) {
    const slot = players[index] || {}
    const position = index + 1
    const seat = `P${position}`
    const user = String(slot.user || 'None').trim() || 'None'
    const occupied = user.toLowerCase() !== 'none'
    const name = occupied ? user : `Open Seat ${position}`
    seats.push({
      id: occupied ? normalizePlayerId(user, `player_${position}`) : `guest_p${position}`,
      name,
      user,
      controller: slot.controller || `Joystick ${position}`,
      position,
      seat,
      occupied
    })
  }
  return seats
}
const defaultVocabularyText = 'I call the cabinet "the machine"\nPrefer scanline filter at 50%\nAlways play with sound at 60%'
const DEFAULT_USER_OPTIONS = ['None', 'Dad', 'Mom', 'Kid Y', 'Kid Z', 'Guest']

/** Vicky persona config for EngineeringBaySidebar */
const VICKY_PERSONA = {
  id: 'vicky',
  name: 'VICKY',
  icon: '\uD83C\uDFA4',
  icon2: '\uD83D\uDDE3\uFE0F',
  accentColor: '#c8ff00',
  accentGlow: 'rgba(200, 255, 0, 0.35)',
  scannerLabel: 'LISTENING...',
  voiceProfile: 'vicky',
  emptyHint: 'Ask Vicky about voice settings, profiles, or speech recognition.',
  chips: [
    { id: 'profiles', label: 'Show profiles', prompt: 'Show me all user voice profiles.' },
    { id: 'tts', label: 'Test TTS', prompt: 'Read a test sentence aloud so I can hear the TTS voice.' },
    { id: 'vocab', label: 'Custom vocabulary', prompt: 'Help me set up custom vocabulary for voice commands.' },
    { id: 'consent', label: 'Privacy settings', prompt: 'Show me the current voice consent and privacy settings.' },
  ],
};
const ADD_USER_OPTION_VALUE = '__add_user__'

export default function VoicePanel() {
  // Voice panel state
  const [chatOpen, setChatOpen] = useState(false)
  const [messages, setMessages] = useState([
    { role: 'assistant', text: 'Hi! I\'m your Voice Assistant. You can type or use voice commands to interact with me. How can I help you today?' }
  ])
  const [input, setInput] = useState('')
  const [warn, setWarn] = useState('')
  const [consent, setConsent] = useState({ accepted: false, consentVersion: '2.0', scopes: [] })
  const [showConsent, setShowConsent] = useState(false)
  const [consentReady, setConsentReady] = useState(false)
  const [showTerms, setShowTerms] = useState(false)
  const [agreeNetwork, setAgreeNetwork] = useState(false)
  const [agreeLeaderboard, setAgreeLeaderboard] = useState(false)
  const [agreeContact, setAgreeContact] = useState(false)
  const [consentError, setConsentError] = useState('')
  const [consentSaving, setConsentSaving] = useState(false)
  const [profile, setProfile] = useState(() => ({
    displayName: '',
    initials: '',
    favoriteColor: '#c8ff00',
    avatar: '',
    userId: '',
    preferences: createDefaultPreferences()
  }))
  const { profile: sharedProfile, refreshProfile } = useProfileContext()

  // Session management state
  const [players, setPlayers] = useState(() => buildDefaultPlayers())
  const [customUsers, setCustomUsers] = useState([])

  // Voice settings state
  const [vocabText, setVocabText] = useState(defaultVocabularyText)
  const [voiceAssignments, setVoiceAssignments] = useState({})

  const [shareInFlight, setShareInFlight] = useState(null)
  const [shareFeedback, setShareFeedback] = useState('')
  const [saveToast, setSaveToast] = useState('')
  const [isSaving, setIsSaving] = useState(false)
  const [addUserModal, setAddUserModal] = useState({ open: false, playerIndex: null, value: '' })

  // Refs
  const vocabRef = useRef(null)
  const welcomedProfileRef = useRef('')
  const handoffProcessedRef = useRef(null)

  const [isChatLoading, setIsChatLoading] = useState(false)
  const [isSpeaking, setIsSpeaking] = useState(false)
  const [autoStopEnabled, setAutoStopEnabled] = useState(true) // User can toggle this
  const primaryUserId = sharedProfile?.userId || profile.userId || 'guest'
  const primaryUserName = ((sharedProfile?.displayName || profile.displayName || 'Guest').trim()) || 'Guest'
  const [tendenciesData, setTendenciesData] = useState(null)
  const [tendenciesStatus, setTendenciesStatus] = useState('idle')
  const userOptions = useMemo(() => {
    const extras = customUsers.filter(name => !DEFAULT_USER_OPTIONS.includes(name))
    return [...DEFAULT_USER_OPTIONS, ...extras]
  }, [customUsers])
  const sessionPlayers = useMemo(() => toSessionPlayers(players), [players])

  // ---- Try voice lighting command via SSE (returns tts_response if recognized) ----
  const tryLightingCommand = useCallback(async (text) => {
    try {
      const response = await fetch(`${GATEWAY}/api/voice/lighting-command`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ transcript: text, user_id: primaryUserId })
      })
      if (!response.ok) return null

      // Read SSE stream for final result
      const reader = response.body.getReader()
      const decoder = new TextDecoder()
      let lastEvent = null

      while (true) {
        const { done, value } = await reader.read()
        if (done) break
        const chunk = decoder.decode(value, { stream: true })
        // Parse SSE lines: "data: {...}\n\n"
        const lines = chunk.split('\n').filter(l => l.startsWith('data: '))
        for (const line of lines) {
          try {
            const data = JSON.parse(line.slice(6))
            lastEvent = data
          } catch { /* skip malformed lines */ }
        }
      }

      // Check if the command was recognized and completed
      if (lastEvent?.status === 'complete' && lastEvent?.success) {
        return lastEvent  // Has tts_response, intent, etc.
      }
      if (lastEvent?.status === 'error' && lastEvent?.suggestion) {
        return null  // Not a lighting command Ã¢â‚¬â€ fall through to AI chat
      }
      return null
    } catch (err) {
      console.debug('[VoicePanel] Lighting command endpoint unavailable:', err.message)
      return null  // Backend down or error Ã¢â‚¬â€ fall through to AI chat
    }
  }, [primaryUserId])


  // Chat functionality
  const addMessage = useCallback((text, role) => {
    setMessages(prev => [...prev, { role, text: String(text ?? '') }])
  }, [])

  // ---- Voice transcription callback (wires useGemSpeech Ã¢â€ â€™ AI chat) ----
  const handleVoiceTranscript = useCallback((text) => {
    if (!text) return
    // Display as user message
    addMessage(text, 'user')

    setIsChatLoading(true)

    // Step 1: Try as a lighting command first (SSE endpoint)
    tryLightingCommand(text).then(async (cmdResult) => {
      if (cmdResult) {
        // Lighting command recognized and applied Ã¢â‚¬â€ speak the confirmation
        const confirmText = cmdResult.tts_response || 'Lighting command applied.'
        addMessage(confirmText, 'assistant')
        try {
          setIsSpeaking(true)
          await speakAsVicky(confirmText)
        } catch (ttsError) {
          console.error('[VoicePanel] TTS playback failed:', ttsError)
        } finally {
          setIsSpeaking(false)
        }
        return  // Done Ã¢â‚¬â€ don't fall through to AI chat
      }

      // Step 2: Not a lighting command Ã¢â‚¬â€ send to AI chat (existing flow)
      const profileName = (sharedProfile?.displayName || profile.displayName || '').trim() || 'Guest'
      const hasProfileName = Boolean((sharedProfile?.displayName || profile.displayName || '').trim())
      const profileContext = {
        name: profileName,
        userId: sharedProfile?.userId || profile.userId || 'profile',
        initials: sharedProfile?.initials || profile.initials,
        favoriteColor: sharedProfile?.favoriteColor || profile.favoriteColor,
        preferences: sharedProfile?.preferences || profile.preferences
      }

      try {
        const response = await aiChat({
          provider: 'claude',
          model: 'claude-3-5-haiku-20241022',
          scope: 'state',
          messages: [
            { role: 'system', content: buildVickySystemPrompt(profileName, hasProfileName) },
            { role: 'user', content: text }
          ],
          metadata: {
            panel: 'voice',
            actionType: 'voice_transcript',
            profile: profileContext,
            currentPlayers: players
          }
        })

        if (response) {
          const assistantText =
            typeof response?.message === 'string'
              ? response.message
              : (response?.message?.content ?? response?.response ?? 'Ready.')
          addMessage(String(assistantText), 'assistant')
          try {
            setIsSpeaking(true)
            await speakAsVicky(String(assistantText))
          } catch (ttsError) {
            console.error('[VoicePanel] TTS playback failed:', ttsError)
          } finally {
            setIsSpeaking(false)
          }
        }
      } catch (error) {
        addMessage('Sorry, I encountered an error processing your request.', 'assistant')
        console.error('[VoicePanel] Voice transcript AI error:', error)
      }
    }).catch((error) => {
      addMessage('Sorry, I encountered an error processing your request.', 'assistant')
      console.error('[VoicePanel] Voice command pipeline error:', error)
    }).finally(() => {
      setIsChatLoading(false)
    })
  }, [addMessage, players, profile, sharedProfile, tryLightingCommand])

  // ---- Gem Speech Hook ----
  const { isRecording, wsConnected, lastTranscript, warning: speechWarning, toggleMic } = useGemSpeech({
    autoStopEnabled,
    panelName: 'voice',
    onTranscript: handleVoiceTranscript
  })

  // Unified phase indicator: Listening > Thinking > Speaking > Idle
  const currentPhase = useMemo(() => {
    if (isSpeaking) return { label: 'Speaking', icon: '\uD83D\uDD0A', className: 'phase-speaking' }
    if (isChatLoading) return { label: 'Thinking', icon: '\uD83E\uDDE0', className: 'phase-thinking' }
    if (isRecording) return { label: 'Listening', icon: '\uD83C\uDFA4', className: 'phase-listening' }
    return { label: 'Idle', icon: '\uD83D\uDCA4', className: 'phase-idle' }
  }, [isSpeaking, isChatLoading, isRecording])

  // Surface hook warnings into VoicePanel's warn state
  useEffect(() => {
    if (speechWarning) setWarn(speechWarning)
  }, [speechWarning])


  const sendMessage = useCallback(async () => {
    const text = input.trim()
    if (!text) return

    addMessage(text, 'user')
    setInput('')

    const savedName = (sharedProfile?.displayName || profile.displayName || '').trim()
    const normalized = text.toLowerCase()
    const nameQuestion =
      normalized.includes('my name') ||
      normalized.includes('profile name') ||
      normalized.includes('who am i') ||
      normalized.includes('who i am') ||
      normalized.includes('do you know who i am') ||
      normalized.includes('do you know me') ||
      normalized.includes('know who i am') ||
      normalized.includes('what is my name') ||
      normalized.includes('what am i called')

    const profileQuestion =
      normalized.includes('what profile') ||
      normalized.includes('which profile') ||
      normalized.includes('current profile') ||
      normalized.includes('profile am i using') ||
      normalized.includes('profile am i in')

    if (nameQuestion || profileQuestion) {
      if (savedName) {
        addMessage(`Your profile name is ${savedName}.`, 'assistant')
      } else {
        addMessage('I do not see a saved profile name yet. Open the profile section above to set one, then I will remember it automatically.', 'assistant')
      }
      return
    }

    try {
      setIsChatLoading(true)
      const profileName = (sharedProfile?.displayName || profile.displayName || '').trim() || 'Guest'
      const hasProfileName = Boolean((sharedProfile?.displayName || profile.displayName || '').trim())
      const profileContext = {
        name: profileName,
        userId: sharedProfile?.userId || profile.userId || 'profile',
        initials: sharedProfile?.initials || profile.initials,
        favoriteColor: sharedProfile?.favoriteColor || profile.favoriteColor,
        preferences: sharedProfile?.preferences || profile.preferences
      }

      const response = await aiChat({
        provider: 'claude',
        model: 'claude-3-5-haiku-20241022',
        scope: 'state',
        messages: [
          { role: 'system', content: buildVickySystemPrompt(profileName, hasProfileName) },
          { role: 'user', content: text }
        ],
        metadata: {
          panel: 'voice',
          actionType: 'chat',
          profile: profileContext,
          currentPlayers: players
        }
      })

      if (response) {
        const assistantText =
          typeof response?.message === 'string'
            ? response.message
            : (response?.message?.content ?? response?.response ?? 'Ready.')
        addMessage(String(assistantText), 'assistant')

        // Speak the response using Vicky's voice
        try {
          await speakAsVicky(String(assistantText))
        } catch (ttsError) {
          console.error('[VoicePanel] TTS playback failed:', ttsError)
          // Don't show warning here since text chat can work without TTS
        }
      }
    } catch (error) {
      const errorMessage = 'Sorry, I encountered an error processing your request.'
      addMessage(errorMessage, 'assistant')
      console.error('[VoicePanel] sendMessage error:', error)
    }
    finally {
      setIsChatLoading(false)
    }
  }, [input, players, profile, sharedProfile, addMessage])

  // Stop any ongoing TTS when this panel unmounts
  useEffect(() => () => { try { stopSpeaking() } catch { } }, [])

  // Session management
  const handleCopySetup = useCallback(async () => {
    try {
      const setupData = { players, timestamp: new Date().toISOString() }
      const link = `${window.location.origin}/assistants?agent=voice#setup=${btoa(JSON.stringify(setupData))}`

      if (navigator.clipboard?.writeText) {
        await navigator.clipboard.writeText(link)
        addMessage('Setup link copied to clipboard!', 'assistant')
      }
    } catch (error) {
      addMessage('Failed to copy setup link.', 'assistant')
    }
  }, [players, addMessage])

  const handleStartSession = useCallback(async () => {
    const activePlayers = players.filter(p => p.user !== 'None')
    addMessage(`Starting session with ${activePlayers.length} player(s): ${activePlayers.map(p => p.user).join(', ')}`, 'assistant')
    try {
      const fallbackUserId = (primaryUserId || profile.userId || profile.initials || primaryUserName || 'guest').trim()
      const resolvedUserId = (fallbackUserId || 'guest').slice(0, 8)
      await startPlayerSession({
        playerName: primaryUserName,
        playerId: resolvedUserId,
        players: sessionPlayers,
        panel: 'voice'
      })
    } catch (sessionError) {
      console.warn('[Voice Panel] Failed to start ScoreKeeper session:', sessionError)
    }
  }, [players, addMessage, primaryUserId, primaryUserName, sessionPlayers])

  // Handoff effect (handles Dewey Ã¢â€ â€™ Voice context handoff)
  useEffect(() => {
    const urlParams = new URLSearchParams(window.location.search)
    const handoffContext = urlParams.get('context')
    const hasHandoff = Boolean((handoffContext || '').trim())
    const noHandoff = urlParams.has('nohandoff')
    const shouldHandoff = hasHandoff && !noHandoff

    if (shouldHandoff && handoffContext !== handoffProcessedRef.current) {
      const welcomeMsg = `Hi! Dewey told me: "${handoffContext}"\n\nI'm Vicky, your voice assistant. I can help you with microphone setup, voice commands, and audio settings. What would you like me to help with?`
      handoffProcessedRef.current = handoffContext

      setMessages(prev => [...prev, { role: 'assistant', content: welcomeMsg, timestamp: Date.now() }])
      setChatOpen(true)
      speakAsVicky(welcomeMsg).catch(err => {
        console.warn('[VoicePanel] URL handoff TTS failed:', err)
      })
    }

    // Check for JSON handoff from Dewey (only when arriving via Dewey URL context)
    if (shouldHandoff) (async () => {
      try {
        const deviceId = window.AA_DEVICE_ID || (() => {
          console.warn('[Vicky] window.AA_DEVICE_ID not available, ' +
            'falling back to cabinet-001. Cabinet identity may not be unique.')
          return 'cabinet-001'
        })()
        const response = await fetch('/api/local/dewey/handoff/voice', {
          method: 'GET',
          headers: {
            'Content-Type': 'application/json',
            'x-device-id': deviceId,
            'x-panel': 'voice',
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
            const welcomeMsg = `Dewey briefed me: "${summaryText}". I'm Vicky, ready to help with your voice setup!`

            setMessages(prev => [...prev, { role: 'assistant', content: welcomeMsg, timestamp: Date.now() }])
            setChatOpen(true)
            speakAsVicky(welcomeMsg).catch(err => {
              console.warn('[VoicePanel] JSON handoff TTS failed:', err)
            })
          }
        }
      } catch (err) {
        console.warn('[VoicePanel] Handoff fetch failed:', err)
      }
    })()
  }, [])

  // Auto-resize vocab textarea
  useEffect(() => {
    if (vocabRef.current) {
      vocabRef.current.style.height = 'auto'
      vocabRef.current.style.height = vocabRef.current.scrollHeight + 'px'
    }
  }, [vocabText])

  // Surface hook warnings in VoicePanel's warn state
  useEffect(() => {
    if (speechWarning) setWarn(speechWarning)
  }, [speechWarning])

  // Welcome the user when profile loads or changes
  useEffect(() => {
    const profileName = (sharedProfile?.displayName || '').trim()
    if (!profileName) return
    if (welcomedProfileRef.current === profileName) return
    welcomedProfileRef.current = profileName

    startPlayerSession({
      playerName: profileName,
      playerId: sharedProfile?.userId || 'guest',
      players: sessionPlayers,
      panel: 'voice'
    }).then(() => {
      console.log('[VoicePanel] ScoreKeeper session started for:', profileName)
    }).catch((err) => {
      console.warn('[VoicePanel] Failed to auto-start session:', err)
    })

    const welcomeMessage = `Welcome, ${profileName}! I'm Vicky, your voice assistant. How can I help you today?`
    addMessage(welcomeMessage, 'assistant')

    // Speak the welcome message
    speakAsVicky(welcomeMessage).catch((err) => {
      console.error('[VoicePanel] Failed to speak welcome message:', err)
    })
  }, [sharedProfile?.displayName, sharedProfile?.userId, addMessage, sessionPlayers])

  // ---- Doc & LoRa Real-time Event Listener ----
  useEffect(() => {
    let socket = null
    let reconnectTimer = null

    const connectDocWs = () => {
      // Use the same GATEWAY logic but switch to ws/wss protocol
      const wsUrl = GATEWAY.replace(/^http/, 'ws') + '/api/doc/ws/events'
      console.log('[VoicePanel] Connecting to Doc Health stream:', wsUrl)

      try {
        socket = new WebSocket(wsUrl)

        socket.onopen = () => {
          console.log('[VoicePanel] Connected to Doc Health WebSocket')
          socket.send('ping')
        }

        socket.onmessage = async (event) => {
          try {
            const data = JSON.parse(event.data)

            // Handle Remediation Events (LoRa)
            if (data.type === 'remediation') {
              const { game, result } = data
              if (result?.success) {
                const msg = `LoRa detected a crash in ${game}. Applying a JIT workaround: ${result.fix_detail || 'CLI flag injection'}. Re-launching now.`
                addMessage(msg, 'assistant')
                await speakAsVicky(msg)
              } else {
                const msg = `LoRa failed to repair ${game}. The game engine might require manual surgery. I've logged the crash report for Doc.`
                addMessage(msg, 'assistant')
                await speakAsVicky(msg)
              }
            }

            // Handle Hardware Detection Events (Doc)
            if (data.type === 'board_detected') {
              const { board_name } = data
              const msg = `Doc has detected a new ${board_name || 'arcade controller'}. Machine bio updated.`
              addMessage(msg, 'assistant')
              await speakAsVicky(msg)
            }

          } catch (e) {
            console.warn('[VoicePanel] Failed to parse Doc event:', e)
          }
        }

        socket.onclose = () => {
          console.log('[VoicePanel] Doc Health WS closed. Retrying in 5s...')
          reconnectTimer = setTimeout(connectDocWs, 5000)
        }

        socket.onerror = (err) => {
          console.error('[VoicePanel] Doc Health WS error:', err)
          socket.close()
        }
      } catch (err) {
        console.error('[VoicePanel] WebSocket setup failed:', err)
      }
    }

    connectDocWs()

    return () => {
      if (socket) socket.close()
      if (reconnectTimer) clearTimeout(reconnectTimer)
    }
  }, [addMessage])

  const quickCommands = {
    galaga: 'I pronounce "Galaga" as [guh-LAH-guh]',
    fighter: 'When I say "fighter", I mean Street Fighter II',
    continues: 'I call continues "extra guys"',
    cabinet: 'I call the cabinet "the machine"'
  }

  const addQuickCommand = useCallback((type) => {
    const command = quickCommands[type]
    if (vocabText.includes(command)) {
      addMessage('This command is already in your vocabulary!', 'assistant')
      return
    }
    setVocabText(prev => prev + '\n' + command)
  }, [vocabText, addMessage])

  const handlePlayerUserChange = useCallback((playerIndex, selectedValue) => {
    if (selectedValue === ADD_USER_OPTION_VALUE) {
      setAddUserModal({ open: true, playerIndex, value: '' })
      return
    }
    setPlayers(prev => {
      const next = [...prev]
      next[playerIndex] = { ...next[playerIndex], user: selectedValue }
      return next
    })
  }, [])

  const handleAddUserConfirm = useCallback(() => {
    const cleaned = (addUserModal.value || '').trim()
    if (!cleaned) return
    const playerIndex = addUserModal.playerIndex
    setPlayers(prev => {
      const next = [...prev]
      next[playerIndex] = { ...next[playerIndex], user: cleaned }
      return next
    })
    setCustomUsers(prev => (prev.includes(cleaned) ? prev : [...prev, cleaned]))
    addMessage(`Added ${cleaned} to Player ${playerIndex + 1}.`, 'assistant')
    setAddUserModal({ open: false, playerIndex: null, value: '' })
  }, [addUserModal, addMessage])

  // Load consent/profile on mount
  useEffect(() => {
    let isActive = true
    ;(async () => {
      try {
        const [c, primary] = await Promise.all([
          getConsent().catch(() => ({ accepted: false })),
          getPrimaryProfile().catch(() => ({ profile: {}, exists: false }))
        ])
        if (!isActive) return
        const accepted = !!(c?.accepted || c?.consent?.accepted)
        const primaryProfile = primary?.profile || {}
        const primaryName = String(primaryProfile.display_name || primaryProfile.displayName || '').trim()
        const isReturningPlayer = Boolean(primaryName) && !/^guest$/i.test(primaryName)
        setConsent(c?.consent || { accepted: false, consentVersion: '1.0', scopes: [] })
        setShowConsent(!(accepted && isReturningPlayer))
      } catch {
        if (!isActive) return
        setShowConsent(true)
      } finally {
        if (isActive) setConsentReady(true)
      }
    })()
    return () => {
      isActive = false
    }
  }, [])

  useEffect(() => {
    if (!sharedProfile) return
    const prefs = sharedProfile.preferences || {}
    const normalizedPlayers = Array.isArray(prefs.players) && prefs.players.length
      ? prefs.players.map(player => ({
        user: player?.user || 'Player',
        controller: player?.controller || 'Not Assigned'
      }))
      : buildDefaultPlayers()
    const normalizedAssignments = { ...(prefs.voiceAssignments || {}) }
    const hasSavedVocabulary = Object.prototype.hasOwnProperty.call(prefs || {}, 'vocabulary')
    const vocabularyFromProfile = typeof prefs.vocabulary === 'string' ? prefs.vocabulary : ''

    setPlayers(normalizedPlayers)
    setVoiceAssignments(normalizedAssignments)
    setVocabText(hasSavedVocabulary ? vocabularyFromProfile : defaultVocabularyText)
    setProfile({
      displayName: sharedProfile.displayName || '',
      initials: sharedProfile.initials || (sharedProfile.displayName || '').slice(0, 2).toUpperCase(),
      favoriteColor: sharedProfile.favoriteColor || '#c8ff00',
      avatar: sharedProfile.avatar || '',
      userId: sharedProfile.userId || '',
      preferences: {
        voiceAssignments: normalizedAssignments,
        vocabulary: vocabularyFromProfile,
        players: normalizedPlayers
      }
    })
  }, [sharedProfile])

  useEffect(() => {
    if (!primaryUserId) return
    let cancelled = false
    setTendenciesStatus('loading')
    fetch(`/profiles/${primaryUserId}/tendencies.json`, { cache: 'no-store' })
      .then((resp) => {
        if (!resp.ok) throw new Error('not found')
        return resp.json()
      })
      .then((data) => {
        if (cancelled) return
        setTendenciesData(data)
        setTendenciesStatus('ready')
      })
      .catch(() => {
        if (cancelled) return
        setTendenciesData(null)
        setTendenciesStatus('empty')
      })
    return () => {
      cancelled = true
    }
  }, [primaryUserId])

  const formatTendencyLabel = (key = '') => {
    return key.replace(/[_-]/g, ' ').replace(/\b\w/g, char => char.toUpperCase())
  }

  const formatTendencyValue = (value) => {
    if (Array.isArray(value)) return value.join(', ')
    if (value && typeof value === 'object') {
      return Object.entries(value).map(([k, v]) => `${formatTendencyLabel(k)}: ${v}`).join(' | ')
    }
    return String(value ?? '')
  }

  const tendencyEntries = useMemo(() => {
    if (!tendenciesData || typeof tendenciesData !== 'object') return []
    return Object.entries(tendenciesData).slice(0, 8)
  }, [tendenciesData])

  useEffect(() => {
    if (!sharedProfile?.displayName) return
    if (welcomedProfileRef.current === sharedProfile.displayName) return
    welcomedProfileRef.current = sharedProfile.displayName
    addMessage(`Profile loaded: ${sharedProfile.displayName}.`, 'assistant')
  }, [sharedProfile?.displayName, addMessage])

  const canApplyConsent = agreeNetwork && agreeLeaderboard

  const handleApplyConsent = useCallback(async () => {
    try {
      setConsentError('')
      setConsentSaving(true)
      console.log('[Voice Panel] Applying consent...')
      const payload = {
        accepted: true,
        consentVersion: '1.0',
        scopes: [
          ...(agreeNetwork ? ['network_participation', 'activity_tracking'] : []),
          ...(agreeLeaderboard ? ['leaderboard_public'] : []),
          ...(agreeContact ? ['contact_optin'] : []),
        ]
      }
      console.log('[Voice Panel] Consent payload:', payload)
      await previewConsent(payload)
      console.log('[Voice Panel] Preview successful')
      await applyConsent(payload)
      console.log('[Voice Panel] Apply successful')
      setConsent({ ...payload })
      setShowConsent(false)
      setConsentError('')
    } catch (e) {
      console.error('[Voice Panel] Consent error:', e)
      setConsentError('Failed to save consent. Please try again.')
    } finally {
      setConsentSaving(false)
    }
  }, [agreeNetwork, agreeLeaderboard, agreeContact])

  const handleSaveProfile = useCallback(async () => {
    try {
      setIsSaving(true)
      console.log('[Voice Panel] Saving and broadcasting primary profile...')

      const preferencesPayload = {
        ...(profile.preferences || {}),
        voiceAssignments,
        vocabulary: vocabText,
        players
      }

      const fallbackUserId = (profile.userId || profile.initials || profile.displayName || primaryUserName || 'guest').trim()
      const resolvedUserId = (fallbackUserId || 'guest').slice(0, 8)

      const resolvedDisplayName = (profile.displayName || primaryUserName || 'Guest').trim() || 'Guest'
      const normalizedVocabulary = vocabText
        .split('\n')
        .map(line => line.trim())
        .filter(Boolean)
      const primaryPlayerSlot = resolvePrimaryPlayerSlot(players, resolvedDisplayName)
      const primaryPlayer = players[primaryPlayerSlot] || { controller: 'Not Assigned' }
      const profilePayload = {
        user_id: resolvedUserId,
        display_name: resolvedDisplayName,
        initials: profile.initials || 'PL',
        voice_prefs: voiceAssignments,
        vocabulary: normalizedVocabulary,
        training_phrases: [],
        player_position: `P${primaryPlayerSlot + 1}`,
        controller_assignment: primaryPlayer.controller || 'Not Assigned',
        custom_vocabulary: normalizedVocabulary,
        consent_active: !!consent?.accepted
      }

      console.log('[Voice Panel] Primary profile payload:', profilePayload)

      // Call the new broadcast endpoint
      const response = await fetch(`${GATEWAY}/api/local/profile/primary`, {
        method: 'PUT',
        headers: {
          'Content-Type': 'application/json',
          'x-panel': 'voice',
          'x-scope': 'state'
        },
        body: JSON.stringify(profilePayload)
      })

      if (!response.ok) {
        const errorData = await response.json().catch(() => ({}))
        throw new Error(errorData.error || 'Failed to save primary profile')
      }

      console.log('[Voice Panel] Primary profile saved and broadcast successfully')

      // Also update the local profile using the old method for compatibility
      const legacyPayload = {
        ...profile,
        displayName: profilePayload.display_name,
        initials: profilePayload.initials,
        userId: resolvedUserId,
        preferences: preferencesPayload
      }

      await previewProfile(legacyPayload)
      await applyProfile(legacyPayload)
      refreshProfile()
      setProfile(legacyPayload)

      // Update ScoreKeeper session context (Vicky is source of truth)
      try {
        await startPlayerSession({
          playerName: profilePayload.display_name,
          playerId: profilePayload.user_id,
          players: sessionPlayers,
          panel: 'voice'
        })
      } catch (sessionError) {
        console.warn('[Voice Panel] Failed to start ScoreKeeper session:', sessionError)
      }

      // Show success toast
      setSaveToast('Primary user saved and broadcast to Arcade Assistant')
      addMessage('Profile saved and broadcast to all agents!', 'assistant')

      console.log('[Vicky] Profile broadcast complete:', profilePayload)

      // Auto-hide toast after 4 seconds
      setTimeout(() => setSaveToast(''), 4000)
    } catch (e) {
      console.error('[Voice Panel] Profile save error:', e)
      setSaveToast(`Error: ${e.message || 'Failed to save profile'}`)
      addMessage('Failed to save profile.', 'assistant')

      // Auto-hide error toast after 6 seconds
      setTimeout(() => setSaveToast(''), 6000)
    } finally {
      setIsSaving(false)
    }
  }, [profile, voiceAssignments, vocabText, players, primaryUserId, addMessage, refreshProfile, sessionPlayers])

  const forwardTranscript = useCallback(async (target) => {
    const transcript = (lastTranscript || '').trim()
    if (!transcript) {
      setWarn('No transcript available to share yet.')
      return
    }
    setShareFeedback('')
    setShareInFlight(target)
    const profileName = profile.displayName || 'Guest'
    const profileId = profile.userId || 'profile'
    try {
      if (target === 'launchbox') {
        const response = await fetch('/api/launchbox/chat', {
          method: 'POST',
          headers: {
            'Content-Type': 'application/json',
            'x-user-profile': profileId,
            'x-user-name': profileName
          },
          body: JSON.stringify({
            message: `[Forwarded from Vicky for ${profileName}]\n${transcript}`,
            context: {
              forwardedBy: 'voice',
              players,
              vocabulary: vocabText,
              consentAccepted: !!consent?.accepted
            },
            profile: {
              id: profileId,
              name: profileName
            }
          })
        })
        const body = await response.json().catch(() => ({}))
        if (!response.ok) {
          throw new Error(body?.error || 'LaunchBox chat rejected transcript')
        }
        if (body?.response) {
          addMessage(`LoRa replied: ${body.response}`, 'assistant')
        } else {
          addMessage('Transcript sent to LaunchBox LoRa.', 'assistant')
        }
        setShareFeedback('Transcript shared with LaunchBox LoRa.')
        return
      }

      const systemPrompt = [
        'You are Dewey, the upbeat AI concierge for the arcade.',
        `A transcript was forwarded by Vicky for ${profileName}.`,
        'Acknowledge it briefly and offer a helpful follow-up suggestion.'
      ].join(' ')
      const result = await aiChat({
        provider: 'gemini',
        messages: [
          { role: 'system', content: systemPrompt },
          { role: 'user', content: transcript }
        ],
        metadata: {
          panel: 'dewey',
          forwarded_by: 'voice',
          actionType: 'transcript_forward'
        }
      })
      const reply = result?.message || result?.response || result?.content
      if (reply) {
        addMessage(`Dewey replied: ${reply}`, 'assistant')
      } else {
        addMessage('Transcript sent to Dewey.', 'assistant')
      }
      setShareFeedback('Transcript shared with Dewey.')
    } catch (error) {
      console.error('[VoicePanel] Failed to share transcript', error)
      setWarn(error?.message || 'Failed to share transcript. Try again.')
    } finally {
      setShareInFlight(null)
    }
  }, [lastTranscript, profile, players, vocabText, consent, addMessage])

  useEffect(() => {
    if (!shareFeedback) return
    const timer = setTimeout(() => setShareFeedback(''), 4000)
    return () => clearTimeout(timer)
  }, [shareFeedback])

  return (
    <div className="eb-layout">
      <div className="eb-layout__main">
        <PanelShell
          title="Voice Assistant"
          subtitle="Personalization & AI Training Hub"
          icon={
            <img
              src="/vicky-avatar.jpeg"
              alt="Vicky"
              style={{
                width: '48px',
                height: '48px',
                borderRadius: '50%',
                border: '2px solid rgba(0, 229, 255, 0.4)',
                boxShadow: '0 0 12px rgba(200, 255, 0, 0.4)',
                objectFit: 'cover'
              }}
            />
          }
          headerActions={
            <button
              className="chat-toggle-btn"
              onClick={() => setChatOpen(prev => !prev)}
              title={chatOpen ? "Close AI Chat" : "Open AI Chat Assistant"}
              aria-label={chatOpen ? "Close AI Chat" : "Open AI Chat Assistant"}
              aria-pressed={chatOpen}
              style={{ color: '#ffffff', fontSize: '15px', fontWeight: 700 }}
            >
              <span className="chat-icon">{chatOpen ? '\u2715' : '\uD83D\uDCAC'}</span>
              <span className="chat-label">{chatOpen ? 'Close Chat' : 'Chat with AI'}</span>
            </button>
          }
        >
          <div className="voice-panel">
            {showConsent && (
              <div className="consent-overlay" role="dialog" aria-modal="true" aria-label="Permissions & Consent" style={{ position: 'fixed', inset: 0, background: 'rgba(5,8,16,0.92)', zIndex: 50, display: 'flex', alignItems: 'center', justifyContent: 'center' }}>
                <div style={{ width: '720px', maxWidth: '95vw', maxHeight: '90vh', overflowY: 'auto', background: '#0b1020', border: '1px solid #243144', borderRadius: 12, padding: '28px 32px', color: '#e5e7eb' }}>
                  <h2 style={{ marginTop: 0, color: '#c8ff00', fontSize: '1.4em' }}>Welcome to the Arcade Assistant Network</h2>
                  <p style={{ marginTop: 8, marginBottom: 16, fontSize: '1em', lineHeight: 1.7, color: '#d1d5db' }}>
                    This cabinet is powered by <strong style={{ color: '#ffffff' }}>Arcade Assistant</strong>, built by <strong style={{ color: '#ffffff' }}>G&G Arcade</strong>.
                    By opting in below, you agree to connect this cabinet to the Arcade Assistant Network - enabling shared leaderboards,
                    score syncing across cabinets, and personalized AI features. <strong style={{ color: '#c8ff00' }}>Opting in is completely optional.</strong> The
                    cabinet works fully offline without it.
                  </p>

                  <div style={{ background: 'rgba(200,255,0,0.06)', border: '1px solid rgba(200,255,0,0.2)', borderRadius: 8, padding: '14px 18px', marginBottom: 16 }}>
                    <p style={{ margin: '0 0 8px', fontWeight: 700, color: '#c8ff00', fontSize: '0.95em' }}>What We Collect (if you opt in):</p>
                    <ul style={{ margin: 0, paddingLeft: 20, lineHeight: 1.8, fontSize: '0.92em' }}>
                      <li>Display name and initials you provide</li>
                      <li>Game scores and timestamps</li>
                      <li>Cabinet ID (for cross-cabinet syncing)</li>
                      <li>Basic session data (player count, game played)</li>
                    </ul>
                  </div>

                  <div style={{ background: 'rgba(0,229,255,0.06)', border: '1px solid rgba(0,229,255,0.15)', borderRadius: 8, padding: '14px 18px', marginBottom: 20 }}>
                    <p style={{ margin: '0 0 8px', fontWeight: 700, color: '#00e5ff', fontSize: '0.95em' }}>What We Do NOT Collect:</p>
                    <ul style={{ margin: 0, paddingLeft: 20, lineHeight: 1.8, fontSize: '0.92em' }}>
                      <li>Real names, government IDs, or biometric data</li>
                      <li>Payment information or financial data</li>
                      <li>Permanent voice recordings (audio is processed transiently)</li>
                      <li>Location data or device identifiers beyond cabinet ID</li>
                    </ul>
                  </div>

                  <div style={{ marginBottom: 16, display: 'flex', flexDirection: 'column', gap: 12 }}>
                    <label style={{ display: 'flex', alignItems: 'flex-start', gap: 10, cursor: 'pointer', padding: '10px 14px', background: 'rgba(255,255,255,0.03)', border: '1px solid rgba(255,255,255,0.08)', borderRadius: 8 }}>
                      <input type="checkbox" checked={agreeNetwork} onChange={(e) => setAgreeNetwork(e.target.checked)} style={{ marginTop: 3, accentColor: '#c8ff00' }} />
                      <span><strong style={{ color: '#ffffff' }}>Join the Arcade Assistant Network</strong> - I consent to having my display name, scores, and session data shared across connected cabinets operated by G&G Arcade.</span>
                    </label>
                    <label style={{ display: 'flex', alignItems: 'flex-start', gap: 10, cursor: 'pointer', padding: '10px 14px', background: 'rgba(255,255,255,0.03)', border: '1px solid rgba(255,255,255,0.08)', borderRadius: 8 }}>
                      <input type="checkbox" checked={agreeLeaderboard} onChange={(e) => setAgreeLeaderboard(e.target.checked)} style={{ marginTop: 3, accentColor: '#c8ff00' }} />
                      <span><strong style={{ color: '#ffffff' }}>Public Leaderboards</strong> - I agree that my display name and scores may appear on publicly visible leaderboards within the Arcade Assistant Network.</span>
                    </label>
                    <label style={{ display: 'flex', alignItems: 'flex-start', gap: 10, cursor: 'pointer', padding: '10px 14px', background: 'rgba(255,255,255,0.03)', border: '1px solid rgba(255,255,255,0.08)', borderRadius: 8 }}>
                      <input type="checkbox" checked={agreeContact} onChange={(e) => setAgreeContact(e.target.checked)} style={{ marginTop: 3, accentColor: '#c8ff00' }} />
                      <span><strong style={{ color: '#ffffff' }}>Communications (Optional)</strong> - I agree to receive occasional updates, event notifications, or promotions from G&G Arcade via email or SMS. I can unsubscribe at any time.</span>
                    </label>
                  </div>

                  <p style={{ fontSize: '0.82em', color: '#9ca3af', lineHeight: 1.6, marginBottom: 4 }}>
                    By clicking "I Agree," you confirm that you have read and accept the <span style={{ color: '#93c5fd', cursor: 'pointer', textDecoration: 'underline' }} onClick={() => setShowTerms(true)}>Terms of Service & Privacy Policy</span>.
                    Your consent is recorded with a timestamp and can be revoked at any time via <strong>Settings -&gt; Permissions</strong>.
                    G&G Arcade reserves the right to update these terms; material changes will require renewed consent.
                    This cabinet is intended for use in a public arcade environment. If you are under the age of 16, please ask a parent or guardian before opting in.
                  </p>

                  {consentError && (
                    <div style={{ marginTop: 12, padding: '8px 12px', background: 'rgba(239,68,68,0.15)', border: '1px solid #ef4444', borderRadius: 6, color: '#fca5a5', display: 'flex', alignItems: 'center', gap: 8 }}>
                      <span>{consentError}</span>
                      <button type="button" onClick={() => setConsentError('')} style={{ background: 'none', border: 'none', color: '#fca5a5', cursor: 'pointer', padding: '0 4px', fontSize: '1.1em' }} aria-label="Dismiss error">x</button>
                    </div>
                  )}

                  <div style={{ display: 'flex', gap: 12, marginTop: 18, alignItems: 'center' }}>
                    <button className="btn" disabled={!canApplyConsent || consentSaving} onClick={handleApplyConsent} aria-label="Agree and continue">{consentSaving ? 'Saving...' : 'I Agree'}</button>
                    <button className="btn btn-secondary" onClick={() => { setShowConsent(false); setWarn(''); }} aria-label="Continue offline">Continue Offline</button>
                    <button type="button" style={{ marginLeft: 'auto', background: 'none', border: 'none', color: '#93c5fd', cursor: 'pointer', textDecoration: 'underline', fontSize: '0.9em' }} onClick={() => setShowTerms(true)}>Full Terms & Privacy -&gt;</button>
                  </div>
                </div>
              </div>
            )}

            {/* Terms & Privacy Modal */}
            {showTerms && (
              <div className="terms-overlay" role="dialog" aria-modal="true" aria-label="Terms and Privacy" style={{ position: 'fixed', inset: 0, background: 'rgba(5,8,16,0.95)', zIndex: 60, display: 'flex', alignItems: 'center', justifyContent: 'center' }}>
                <div style={{ width: '800px', maxWidth: '95vw', maxHeight: '90vh', background: '#0b1020', border: '1px solid #243144', borderRadius: 8, padding: 24, color: '#e5e7eb', display: 'flex', flexDirection: 'column' }}>
                  <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 16 }}>
                    <h2 style={{ margin: 0, color: '#c8ff00' }}>Terms & Privacy (Local-First)</h2>
                    <button type="button" onClick={() => setShowTerms(false)} style={{ background: 'none', border: 'none', color: '#9ca3af', fontSize: '1.5em', cursor: 'pointer' }} aria-label="Close">x</button>
                  </div>
                  <div style={{ flex: 1, overflowY: 'auto', fontSize: '0.9em', lineHeight: 1.6 }}>
                    <p><strong>Operator / Publisher:</strong> G & G Arcade ("G&G," "we," "us")<br />
                      <strong>Software:</strong> Arcade Assistant<br />
                      <strong>Version:</strong> v2.0 | <strong>Effective:</strong> 2026-03-05</p>

                    <h3 style={{ color: '#93c5fd', marginTop: 16 }}>1) Local-First Default</h3>
                    <p>The Software functions fully offline. No account required for local play. Declining consent does not block basic cabinet use. Online Features are optional.</p>

                    <h3 style={{ color: '#93c5fd', marginTop: 16 }}>2) Consent & Opt-In Model</h3>
                    <p><strong>Requires consent:</strong> Public leaderboards, score syncing, display name visibility, cabinet ID for syncing, optional communications.</p>
                    <p><strong>Does NOT require consent:</strong> Local gameplay, local scores/profiles, basic cabinet operation.</p>

                    <h3 style={{ color: '#93c5fd', marginTop: 16 }}>3) Data We Collect</h3>
                    <p><strong>Local-only by default:</strong> Profiles, scores, settings stored on cabinet.</p>
                    <p><strong>If you opt into Online Features:</strong> Display name, game titles, scores/timestamps, cabinet ID, basic config metadata.</p>
                    <p><strong>We do NOT collect:</strong> Government IDs, biometrics, payment data, real names (unless typed), permanent voice recordings (unless enabled).</p>

                    <h3 style={{ color: '#93c5fd', marginTop: 16 }}>4) Voice & Audio</h3>
                    <p>Voice features are optional. Audio is processed transiently for voice commands. We do not use voice data to identify individuals or sell voice data. Public-space reminder: avoid speaking sensitive information.</p>

                    <h3 style={{ color: '#93c5fd', marginTop: 16 }}>5) Third-Party Services</h3>
                    <p>Online Features may use third-party providers (hosting, databases, cloud AI). Their privacy practices are governed by their own terms.</p>

                    <h3 style={{ color: '#93c5fd', marginTop: 16 }}>6) Scores & Leaderboards</h3>
                    <p>Scores may be moderated, hidden, or removed. Leaderboards are not guaranteed permanent. Offline scores may not sync retroactively.</p>

                    <h3 style={{ color: '#93c5fd', marginTop: 16 }}>7) User Responsibilities</h3>
                    <p>Do not use for unlawful conduct, cheating, or interfering with systems. Cabinet owners responsible for safe operation and installed content.</p>

                    <h3 style={{ color: '#93c5fd', marginTop: 16 }}>8) Ownership & Licensing</h3>
                    <p>Software owned by G&G Arcade. Limited license granted for cabinet use. ROMs/game content are owner's responsibility.</p>

                    <h3 style={{ color: '#93c5fd', marginTop: 16 }}>9) Warranty Disclaimer</h3>
                    <p>Software provided "AS IS." No guarantee of uninterrupted operation or permanent data retention.</p>

                    <h3 style={{ color: '#93c5fd', marginTop: 16 }}>10) Limitation of Liability</h3>
                    <p>G&G not liable for hardware damage, data loss, third-party outages, or indirect damages.</p>

                    <h3 style={{ color: '#93c5fd', marginTop: 16 }}>11) Privacy Choices</h3>
                    <p>Disable Online Features anytime. Request deletion via contact. Local data deletable via cabinet settings.</p>

                    <h3 style={{ color: '#93c5fd', marginTop: 16 }}>12) Changes</h3>
                    <p>Terms may update. Material changes require renewed consent.</p>

                    <h3 style={{ color: '#93c5fd', marginTop: 16 }}>13) Contact</h3>
                    <p>Questions or concerns: <strong>greg@ggarcade.net</strong></p>
                  </div>
                  <div style={{ marginTop: 16, textAlign: 'right' }}>
                    <button className="btn" onClick={() => setShowTerms(false)}>Close</button>
                  </div>
                </div>
              </div>
            )}

            {!consentReady && (
              <section className="section">
                <div className="tendencies-note">Loading privacy settings...</div>
              </section>
            )}

            <div style={{ display: consentReady && !showConsent ? undefined : 'none' }}>
            {/* Add User Name Modal */}
            {addUserModal.open && (
              <div role="dialog" aria-modal="true" aria-label="Add new user" style={{ position: 'fixed', inset: 0, background: 'rgba(5,8,16,0.88)', zIndex: 55, display: 'flex', alignItems: 'center', justifyContent: 'center' }}>
                <div style={{ width: '420px', maxWidth: '90vw', background: '#0b1020', border: '1px solid #243144', borderRadius: 12, padding: '24px 28px', color: '#e5e7eb' }}>
                  <h3 style={{ margin: '0 0 8px', color: '#c8ff00', fontSize: '1.15em' }}>Add New Player Name</h3>
                  <p style={{ margin: '0 0 16px', fontSize: '0.9em', color: '#9ca3af' }}>
                    Enter a name for Player {addUserModal.playerIndex !== null ? addUserModal.playerIndex + 1 : ''}:
                  </p>
                  <input
                    type="text"
                    autoFocus
                    value={addUserModal.value}
                    onChange={(e) => setAddUserModal(prev => ({ ...prev, value: e.target.value }))}
                    onKeyDown={(e) => { if (e.key === 'Enter') handleAddUserConfirm() }}
                    placeholder="e.g. Alex, Coach, GamerTag..."
                    maxLength={24}
                    style={{
                      width: '100%', padding: '10px 14px', background: 'rgba(255,255,255,0.06)',
                      border: '1px solid rgba(200,255,0,0.3)', borderRadius: 8, color: '#ffffff',
                      fontSize: '1em', fontFamily: 'inherit', outline: 'none', boxSizing: 'border-box'
                    }}
                  />
                  <div style={{ display: 'flex', gap: 12, marginTop: 18, justifyContent: 'flex-end' }}>
                    <button className="btn btn-secondary" onClick={() => setAddUserModal({ open: false, playerIndex: null, value: '' })}>Cancel</button>
                    <button className="btn" disabled={!(addUserModal.value || '').trim()} onClick={handleAddUserConfirm}>Add Player</button>
                  </div>
                </div>
              </div>
            )}

            {/* Toast Notification */}
            {saveToast && (
              <div
                className="save-toast"
                role="status"
                aria-live="polite"
                style={{
                  position: 'fixed',
                  top: '20px',
                  right: '20px',
                  zIndex: 1000,
                  background: saveToast.startsWith('Error') ? '#dc2626' : '#10b981',
                  color: '#ffffff',
                  padding: '12px 20px',
                  borderRadius: '8px',
                  boxShadow: '0 4px 12px rgba(0, 0, 0, 0.3)',
                  fontWeight: '500',
                  maxWidth: '400px'
                }}
              >
                {saveToast}
              </div>
            )}

            {/* Live Transcription */}
            <section className="section">
              <div className="section-header">
                <h2>Live Transcription</h2>
                <span className="badge">WS</span>
              </div>
              {warn && (
                <div className="text-sm" style={{ color: '#fbbf24', marginBottom: 8, display: 'flex', alignItems: 'center', gap: 8 }} role="status" aria-live="polite">
                  <span>{warn}</span>
                  <button type="button" onClick={() => setWarn('')} style={{ background: 'none', border: 'none', color: '#fbbf24', cursor: 'pointer', padding: '0 4px', fontSize: '1.1em' }} aria-label="Dismiss warning">x</button>
                </div>
              )}
              <div className="voice-transcript-box" style={{ padding: '8px', border: '1px solid #374151', borderRadius: 6, background: '#0b1020' }}>
                <div className={`vicky-phase-badge ${currentPhase.className}`}>
                  <span className="phase-icon">{currentPhase.icon}</span>
                  <span className="phase-label">{currentPhase.label}</span>
                </div>
              </div>
              <div style={{ display: 'flex', gap: '12px', marginTop: 12, flexWrap: 'wrap', alignItems: 'center' }}>
                <button
                  className="btn btn-secondary"
                  onClick={() => forwardTranscript('launchbox')}
                  disabled={shareInFlight === 'launchbox'}
                >
                  {shareInFlight === 'launchbox' ? 'Sending to LoRa...' : 'Send to LaunchBox LoRa'}
                </button>
                <button
                  className="btn btn-secondary"
                  onClick={() => forwardTranscript('dewey')}
                  disabled={shareInFlight === 'dewey'}
                >
                  {shareInFlight === 'dewey' ? 'Sending to Dewey...' : 'Send to Dewey'}
                </button>
                {shareFeedback && (
                  <span style={{ fontSize: '13px', color: '#a5f3fc' }}>{shareFeedback}</span>
                )}
              </div>
            </section>

            {/* Player Overview */}
            <section className="section player-overview-section">
              <div className="section-header">
                <h2>Player Overview</h2>
                <span className="badge">Session Context</span>
              </div>
              <div className="player-overview-grid">
                <div className="overview-tile tendencies">
                  <div className="tile-header">
                    <h3>{`${primaryUserName}'s Tendencies`}</h3>
                    <p className="tile-subtitle">Read-only insights</p>
                  </div>
                  {tendenciesStatus === 'loading' && <p className="tendencies-note">Loading tendencies...</p>}
                  {tendenciesStatus === 'empty' && (
                    <p className="tendencies-note">No tendencies saved yet. They will appear here once recorded.</p>
                  )}
                  {tendenciesStatus === 'ready' && tendencyEntries.length === 0 && (
                    <p className="tendencies-note">No tendencies saved yet.</p>
                  )}
                  {tendencyEntries.length > 0 && (
                    <ul className="tendencies-list">
                      {tendencyEntries.map(([key, value]) => (
                        <li key={key}>
                          <span className="label">{formatTendencyLabel(key)}</span>
                          <span className="value">{formatTendencyValue(value)}</span>
                        </li>
                      ))}
                    </ul>
                  )}
                </div>
                <div className="overview-tile permissions">
                  <div className="tile-header">
                    <h3>Permissions</h3>
                    <p className="tile-subtitle">Consent &amp; device access</p>
                  </div>
                  <p className="tendencies-note">
                    {consent?.accepted
                      ? 'Consent is active for this session.'
                      : 'Consent required to sync recordings and transcripts.'}
                  </p>
                  <button className="btn btn-secondary" onClick={() => setShowConsent(true)}>
                    Review Permissions
                  </button>
                </div>
              </div>
            </section>

            {/* Current Session */}
            <section className="section">
              <div className="section-header">
                <h2>Current Session</h2>
              </div>
              <div className="player-grid">
                {/* Arcade-authentic layout: P3/P4 top row, P1/P2 bottom row */}
                {[2, 3, 0, 1].map((index) => {
                  const player = players[index]
                  return (
                    <div key={index} className="player-slot">
                      <div className="player-header">
                        <div className="player-number">P{index + 1}</div>
                        <div className="player-label">Player {index + 1}</div>
                      </div>
                      <div className="form-group">
                        <label>User</label>
                        <select
                          className="form-control"
                          value={player.user}
                          onChange={(e) => handlePlayerUserChange(index, e.target.value)}
                        >
                          {userOptions.map(option => (
                            <option key={option} value={option}>
                              {option}
                            </option>
                          ))}
                          <option value={ADD_USER_OPTION_VALUE}>+ Add user</option>
                        </select>
                      </div>
                      <div className="form-group">
                        <label>Controller</label>
                        <select
                          className="form-control"
                          value={player.controller}
                          onChange={(e) => setPlayers(prev => {
                            const next = [...prev]
                            next[index] = { ...next[index], controller: e.target.value }
                            return next
                          })}
                        >
                          <option value="Not Assigned">Not Assigned</option>
                          <option value="Joystick 1">Joystick 1</option>
                          <option value="Joystick 2">Joystick 2</option>
                          <option value="Joystick 3">Joystick 3</option>
                          <option value="Joystick 4">Joystick 4</option>
                          <option value="Xbox Pad 1">Xbox Pad 1</option>
                          <option value="Xbox Pad 2">Xbox Pad 2</option>
                          <option value="Keyboard">Keyboard</option>
                        </select>
                      </div>
                    </div>
                  )
                })}
              </div>
              <div className="action-bar">
                <button className="btn btn-secondary" onClick={handleCopySetup}>
                  Copy Setup Link
                </button>
                <button className="btn" onClick={handleStartSession}>Start Session</button>
              </div>
            </section>

            {/* Primary User Tendencies */}
            <section className="section">
              <div className="section-header">
                <h2>{primaryUserName}'s Tendencies</h2>
                <span className="badge">Auto-Tracked</span>
              </div>
              {tendenciesStatus === 'loading' && (
                <div className="tendencies-note">Loading tendencies...</div>
              )}
              {tendenciesStatus === 'empty' && (
                <div className="tendencies-note">
                  No tendencies recorded yet. Play some games to build your profile!
                </div>
              )}
              {tendenciesStatus === 'ready' && tendenciesData && (
                <div className="tendencies-grid">
                  {tendenciesData.favorite_game && (
                    <div className="tendency-card">
                      <div className="tendency-label">Favorite Game</div>
                      <div className="tendency-value">{tendenciesData.favorite_game}</div>
                    </div>
                  )}
                  {tendenciesData.favorite_genre && (
                    <div className="tendency-card">
                      <div className="tendency-label">Favorite Genre</div>
                      <div className="tendency-value">{tendenciesData.favorite_genre}</div>
                    </div>
                  )}
                  {tendenciesData.total_sessions && (
                    <div className="tendency-card">
                      <div className="tendency-label">Total Sessions</div>
                      <div className="tendency-value">{tendenciesData.total_sessions}</div>
                    </div>
                  )}
                  {tendenciesData.peak_play_time && (
                    <div className="tendency-card">
                      <div className="tendency-label">Peak Play Time</div>
                      <div className="tendency-value">{tendenciesData.peak_play_time}</div>
                    </div>
                  )}
                  {tendenciesData.most_used_platform && (
                    <div className="tendency-card">
                      <div className="tendency-label">Most Used Platform</div>
                      <div className="tendency-value">{tendenciesData.most_used_platform}</div>
                    </div>
                  )}
                </div>
              )}
            </section>

            {/* Primary User */}
            <section className="section">
              <div className="section-header">
                <h2>Primary User</h2>
                <p className="section-subtitle">
                  This is the main profile Arcade Assistant will operate under for this session.
                </p>
                <div className="current-profile-pill">
                  <span className="pill-label">Current Profile</span>
                  <span className="pill-value">
                    {sharedProfile?.displayName || profile.displayName || 'Guest'}
                  </span>
                </div>
              </div>
              <div className="form-group">
                <label>Custom Vocabulary</label>
                <div className="quick-commands">
                  {Object.keys(quickCommands).map(cmd => (
                    <button key={cmd} className="quick-command-btn" onClick={() => addQuickCommand(cmd)}>
                      + {cmd === 'galaga' ? '"Galaga" pronunciation' :
                        cmd === 'fighter' ? '"Fighter" means SF2' :
                          cmd === 'continues' ? 'Continues = Extra guys' :
                            'Cabinet nickname'}
                    </button>
                  ))}
                </div>
                <textarea
                  ref={vocabRef}
                  className="form-control"
                  value={vocabText}
                  onChange={(e) => setVocabText(e.target.value)}
                  placeholder="e.g., 'I call the cabinet the machine', 'When I say fighter, I mean Street Fighter'"
                  rows={3}
                />
              </div>
              <div className="form-grid">
                <div className="form-group">
                  <label>Display Name</label>
                  <input className="form-control" value={profile.displayName} onChange={(e) => setProfile(p => ({ ...p, displayName: e.target.value }))} placeholder="e.g., Dad" />
                </div>
                <div className="form-group">
                  <label>Initials</label>
                  <input className="form-control" value={profile.initials} onChange={(e) => setProfile(p => ({ ...p, initials: e.target.value }))} placeholder="e.g., DAD" />
                </div>
              </div>
              <div className="action-bar">
                <button
                  className="btn"
                  onClick={handleSaveProfile}
                  disabled={isSaving}
                >
                  {isSaving ? 'Saving & Broadcasting...' : 'Save & Broadcast'}
                </button>
              </div>
            </section>
            </div>
          </div>
        </PanelShell>
      </div>

      {/* Vicky AI Chat Sidebar */}
      <div
        className={"eb-chat-backdrop " + (chatOpen ? "eb-chat-backdrop--visible" : "")}
        onClick={() => setChatOpen(false)}
      />
      <div className={"eb-chat-drawer " + (chatOpen ? "eb-chat-drawer--open" : "") }>
        <button
          type="button"
          className="eb-chat-drawer__close"
          onClick={() => setChatOpen(false)}
          aria-label="Close Vicky chat"
        >
          X
        </button>
        <EngineeringBaySidebar persona={VICKY_PERSONA} />
      </div>
    </div>
  )
}

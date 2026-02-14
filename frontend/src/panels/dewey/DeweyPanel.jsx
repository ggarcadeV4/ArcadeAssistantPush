import React, { useState, useEffect, useRef, useMemo, useCallback } from 'react'
import { useNavigate } from 'react-router-dom'
import './DeweyPanel.css'
import { chat as aiChat } from '../../services/aiClient'
import { speakAsDewey, stopSpeaking, isSpeaking } from '../../services/ttsClient'
import { useProfileContext } from '../../context/ProfileContext'
import { getHeadlines } from '../../services/newsClient'
import TriviaExperience from './trivia/TriviaExperience'
import GamingNews from './news/GamingNews'

const MAX_HISTORY_MESSAGES = 12

const AGENT_SUMMARY = [
  'Available specialists:',
  '* Vicky - voice macros and general introductions.',
  '* LoRa - LaunchBox librarian for launching/importing games.',
  '* Controller Chuck - controller remapping and hardware pairing.',
  '* LED Blinky - cabinet & LED lighting scenes.',
  '* Gunner - light gun calibration.',
  '* Scorekeeper Sam - tournaments, stats, and leaderboards.',
  '* Doc - diagnostics and health monitoring.',
  '* Wiz - modding, scripting, and automations.'
].join('\n')

const PANEL_CAPABILITIES = [
  {
    id: 'interface',
    label: 'Arcade Interface (Diagnostics)',
    keywords: [
      // General terms
      'button', 'buttons', 'joystick', 'stick', 'control', 'controls',
      // Specific arcade hardware
      'arcade button', 'arcade buttons', 'arcade stick', 'arcade joystick',
      'cabinet controls', 'control panel', 'panel button', 'cabinet button',
      // Issues
      'button not working', 'button stuck', 'button sticking', 'button broken',
      'joystick broken', 'control not working', 'broken button'
    ]
  },
  {
    id: 'controller_chuck',
    label: 'Controller Chuck (Pin Mapping)',
    keywords: [
      // Specific to pin mapping and wiring
      'encoder', 'pin mapping', 'wiring', 'ipac', 'ultimarc',
      'remap', 'map button', 'button mapping', 'pin assignment'
    ]
  },
  {
    id: 'console_wizard',
    label: 'Console Wizard',
    keywords: ['controller', 'game controller', 'gamepad', 'xbox', 'playstation', 'ps4', 'ps5', '8bitdo', '8-bitdo', 'handheld controller', 'emulator', 'retroarch', 'nes', 'snes', 'controller profile', 'console config', 'xinput', 'dinput', 'controller not working', 'my controller']
  },
  {
    id: 'gunner',
    label: 'Gunner (Lightguns)',
    keywords: [
      'gun', 'guns', 'lightgun', 'light gun', 'shooting',
      'aim', 'aiming', 'crosshair', 'calibration', 'calibrate',
      'gun not hitting', 'gun not accurate', 'gun broken', 'gun not working'
    ]
  },
  {
    id: 'led-blinky',
    label: 'LED Blinky',
    keywords: [
      'led', 'leds', 'light', 'lights', 'lighting',
      'button lights', 'button light', 'colors', 'color',
      'blinky', 'brightness', 'dim', 'not lit'
    ]
  },
  {
    id: 'launchbox',
    label: 'LaunchBox LoRa',
    keywords: [
      'game', 'games', 'launch', 'play', 'launchbox',
      'library', 'rom', 'roms', 'import', 'platform',
      'find a game', 'show me games', 'random game'
    ]
  },
  {
    id: 'scorekeeper',
    label: 'ScoreKeeper Sam',
    keywords: [
      'score', 'scores', 'tournament', 'leaderboard', 'ranking',
      'high score', 'points', 'stats', 'statistics', 'competition',
      'bracket', 'match', 'champion', 'winner'
    ]
  },
  {
    id: 'voice',
    label: 'Vicky Voice',
    keywords: [
      'voice', 'microphone', 'mic', 'speak', 'talk',
      'voice control', 'voice assistant', 'vicky',
      'speech', 'listen', 'hearing', 'audio input'
    ]
  },
  {
    id: 'system-health',
    label: 'Doc (System Health)',
    keywords: [
      'slow', 'lag', 'lagging', 'stutter', 'stuttering',
      'performance', 'fps', 'framerate', 'freeze', 'freezing',
      'cpu', 'memory', 'ram', 'temperature', 'overheating',
      'hot', 'crash', 'crashing', 'error', 'errors',
      'diagnostics', 'diagnostic', 'check', 'system', 'health',
      'status', 'monitor', 'monitoring', 'computer', 'pc',
      'problem', 'issue', 'wrong', 'broken', 'fix',
      'troubleshoot', 'debug', 'hardware', 'software',
      'technical', 'help', 'not working', 'failing'
    ]
  }
]

const getPanelRecommendationsFromText = (text = '') => {
  const lower = (text || '').toLowerCase()
  const matches = []

  for (const panel of PANEL_CAPABILITIES) {
    const hit = panel.keywords.some(kw => lower.includes(kw))
    if (hit) matches.push(panel)
  }

  const unique = []
  const seen = new Set()
  for (const panel of matches) {
    if (!seen.has(panel.id)) {
      seen.add(panel.id)
      unique.push(panel)
    }
  }
  const result = unique.slice(0, 3)
  console.log('[Dewey] Panel recommendations for:', text, '→', result.map(p => p.label))
  return result
}

const htmlToPlainText = (value = '') => {
  if (!value) return ''
  return value
    .replace(/<br\s*\/?>/gi, '\n')
    .replace(/<\/?[^>]+(>|$)/g, '')
    .replace(/&nbsp;/gi, ' ')
    .replace(/\r/g, '')
    .replace(/\n{3,}/g, '\n\n')
    .trim()
}

const formatAssistantResponse = (value = '') => {
  if (!value) return ''
  return value.trim().replace(/\n/g, '<br>')
}

// Build a concise handoff summary using the last two sentences
// and cap to a reasonable length for clean chips/URLs.
const buildHandoffSummary = (text = '', opts = {}) => {
  const { maxChars = 200, maxSentences = 2 } = opts || {}
  const t = (text || '').trim()
  if (!t) return ''

  // Split into sentence-like chunks, preserving end punctuation.
  const chunks = t.match(/[^.!?]+[.!?]*/g) || [t]
  const selected = chunks.slice(Math.max(0, chunks.length - maxSentences))
  let summary = (selected.join(' ') || t).trim()

  if (summary.length > maxChars) {
    const slice = summary.slice(0, maxChars)
    const lastSpace = slice.lastIndexOf(' ')
    summary = (lastSpace > 0 ? slice.slice(0, lastSpace) : slice) + '...'
  }
  return summary
}

const buildSystemPrompt = (user) => {
  const prefs = user?.preferences || {}
  const preferenceLines = []

  if (prefs.genres?.length) {
    preferenceLines.push(`Favorite genres: ${prefs.genres.join(', ')}.`)
  }
  if (prefs.franchises?.length) {
    preferenceLines.push(`Favorite franchises: ${prefs.franchises.join(', ')}.`)
  }
  if (prefs.keywords?.length) {
    preferenceLines.push(`Key interests: ${prefs.keywords.join(', ')}.`)
  }

  const preferenceSummary = preferenceLines.length > 0
    ? preferenceLines.join(' ')
    : 'No saved preferences yet - ask quick follow-ups to learn their tastes.'

  return [
    'You are Dewey, the upbeat AI concierge for G&G Arcade.',
    'Your job is to QUICKLY route users to the right specialist - do not ask qualifying questions.',
    `Current user: ${user?.name || 'Guest'}. ${preferenceSummary}`,
    AGENT_SUMMARY,
    'Guidelines:',
    '- Keep replies SHORT (1-2 sentences max, under 40 words)',
    '- For technical issues (controllers, LEDs, guns, performance), acknowledge the issue and tell them a specialist chip will appear below',
    '- DO NOT ask follow-up questions - let the specialists handle details',
    '- The UI will automatically show specialist chips based on keywords in the user message',
    '- For gaming chat, news, or trivia, respond normally with 2-3 sentences',
    'Examples:',
    '- User: "my button is broken" → "That sounds like a controller issue! Click the Controller Chuck chip below and he\'ll help you troubleshoot."',
    '- User: "light gun not working" → "Gunner can help with that! Click his chip below to get your gun calibrated."',
    '- User: "recommend a game" → [Give normal recommendation response]'
  ].join('\n')
}

const buildClaudeMessages = ({ history, systemPrompt, userText }) => {
  const trimmedUser = htmlToPlainText(userText)
  const chatHistory = (history || [])
    .filter(msg => msg.role === 'user' || msg.role === 'dewey')
    .slice(-MAX_HISTORY_MESSAGES)
    .map(msg => ({
      role: msg.role === 'user' ? 'user' : 'assistant',
      content: htmlToPlainText(msg.text)
    }))

  const payload = [{ role: 'system', content: systemPrompt }, ...chatHistory]
  if (!chatHistory.length || chatHistory[chatHistory.length - 1]?.content !== trimmedUser) {
    payload.push({ role: 'user', content: trimmedUser })
  }
  return payload
}

export default function DeweyPanel() {
  // Get shared profile from context
  const { profile: sharedProfile } = useProfileContext()
  const navigate = useNavigate()

  // State management
  const [triviaMode, setTriviaMode] = useState(false)
  const [newsMode, setNewsMode] = useState(false)
  const [isRecording, setIsRecording] = useState(false)
  const [isDeweyResponding, setIsDeweyResponding] = useState(false)
  const [isLoading, setIsLoading] = useState(false)
  const [voiceEnabled, setVoiceEnabled] = useState(true)
  const [messages, setMessages] = useState([
    {
      role: 'dewey',
      text: "Hey there! I'm Dewey, your gaming companion. ??<br><br>I can chat about gaming culture, recommend games based on your interests, share the latest gaming news, and tell you all about G&G Arcade!<br><br>What would you like to talk about today?",
      timestamp: new Date()
    }
  ])
  const [input, setInput] = useState('')
  const [currentUser, setCurrentUser] = useState({
    id: 'guest',
    name: 'Guest',
    preferences: {
      genres: [],
      franchises: [],
      keywords: []
    }
  })
  const [showTypingIndicator, setShowTypingIndicator] = useState(false)
  const [speechSupported, setSpeechSupported] = useState(true)
  const [hasMicrophone, setHasMicrophone] = useState(true)
  const [micDetectionReady, setMicDetectionReady] = useState(false)
  const [recommendedPanels, setRecommendedPanels] = useState([])
  const [handoffText, setHandoffText] = useState('')

  // Refs
  const messagesContainerRef = useRef(null)
  const inputRef = useRef(null)
  const messagesRef = useRef(messages)
  const recognitionRef = useRef(null)
  const lastTranscriptRef = useRef('')
  const processingTranscriptRef = useRef(false)
  const micStatusAlertsRef = useRef({
    unsupportedNotified: false,
    lastMicAvailable: true
  })
  const micAccessGrantedRef = useRef(false)
  const micAccessRequestRef = useRef(null)

  // User data (TODO: Load from Supabase)
  const userData = {
    guest: { id: 'guest', name: 'Guest', preferences: { genres: [], franchises: [], keywords: [] } },
    dad: {
      id: 'dad',
      name: 'Dad',
      preferences: {
        genres: ['fighting', 'arcade', 'shmup'],
        franchises: ['Street Fighter', 'Mortal Kombat'],
        keywords: ['FGC', 'competitive']
      }
    },
    mom: { id: 'mom', name: 'Mom', preferences: { genres: ['puzzle', 'casual'], franchises: [], keywords: [] } },
    tim: {
      id: 'tim',
      name: 'Tim',
      preferences: {
        genres: ['fps', 'action'],
        franchises: ['Call of Duty', 'Rainbow Six'],
        keywords: ['multiplayer', 'competitive']
      }
    },
    sarah: { id: 'sarah', name: 'Sarah', preferences: { genres: ['rpg', 'adventure'], franchises: ['Zelda', 'Pokemon'], keywords: [] } }
  }

  const userOptions = useMemo(() => {
    const base = [
      { id: 'guest', label: '👤 Guest' },
      { id: 'dad', label: '👤 Dad' },
      { id: 'mom', label: '👤 Mom' },
      { id: 'tim', label: '👤 Tim' },
      { id: 'sarah', label: '👤 Sarah' }
    ]
    const sharedId = sharedProfile?.userId
    const sharedName = sharedProfile?.displayName
    if (sharedId && sharedName && !base.some(opt => opt.id === sharedId)) {
      base.unshift({ id: sharedId, label: `👤 ${sharedName} (Vicky)` })
    }
    return base
  }, [sharedProfile])

  const systemPrompt = useMemo(() => buildSystemPrompt(currentUser), [currentUser])

  // Sync shared profile to currentUser
  useEffect(() => {
    if (sharedProfile?.displayName) {
      setCurrentUser({
        id: sharedProfile.userId || 'guest',
        name: sharedProfile.displayName || 'Guest',
        preferences: {
          genres: sharedProfile.preferences?.genres || [],
          franchises: sharedProfile.preferences?.franchises || [],
          keywords: sharedProfile.preferences?.keywords || []
        }
      })
    }
  }, [sharedProfile])

  // Auto-scroll to bottom when messages change
  useEffect(() => {
    if (messagesContainerRef.current) {
      messagesContainerRef.current.scrollTop = messagesContainerRef.current.scrollHeight
    }
  }, [messages, showTypingIndicator])

  // Auto-focus input on load
  useEffect(() => {
    if (inputRef.current) {
      inputRef.current.focus()
    }
  }, [])

  // User Profile Management
  const switchUser = (event) => {
    const selectedValue = event.target.value

    if (selectedValue === 'new') {
      createNewProfile()
      // Reset to current user after modal closes
      event.target.value = currentUser.id
      return
    }

    loadUserProfile(selectedValue)
  }

  const loadUserProfile = (userId) => {
    // TODO: Replace with actual Supabase call
    let user = userData[userId]
    if (!user && sharedProfile?.userId === userId) {
      user = {
        id: sharedProfile.userId || 'guest',
        name: sharedProfile.displayName || 'Guest',
        preferences: {
          genres: sharedProfile.preferences?.genres || [],
          franchises: sharedProfile.preferences?.franchises || [],
          keywords: sharedProfile.preferences?.keywords || []
        }
      }
    }
    if (!user) {
      user = userData.guest
    }
    setCurrentUser(user)

    // Welcome message for user
    if (userId !== 'guest') {
      addSystemMessage(`Welcome back, ${user.name}! Your preferences have been loaded.`)
    }
  }

  const createNewProfile = () => {
    // TODO: Implement profile creation modal/flow
    const profileName = prompt('Enter profile name:')

    if (profileName && profileName.trim()) {
      // TODO: Save to Supabase
      alert(`Profile "${profileName}" would be created and saved to Supabase.\n\n(Integrate with your Supabase database)`)
    }
  }

  // Add System Message (for notifications)
  const pushMessage = (message) => {
    setMessages(prev => {
      const next = [...prev, message]
      messagesRef.current = next
      return next
    })
  }

  useEffect(() => {
    messagesRef.current = messages
  }, [messages])

  const addSystemMessage = (text) => {
    pushMessage({
      role: 'system',
      text,
      timestamp: new Date()
    })
  }

  // Add Message to Chat
  const addMessage = (text, role, extra = {}) => {
    pushMessage({
      role,
      text,
      timestamp: new Date(),
      ...extra
    })
  }

  // Detect available microphones so we can warn users if none are present
  useEffect(() => {
    if (typeof navigator === 'undefined' || !navigator.mediaDevices?.enumerateDevices) {
      return
    }

    let cancelled = false
    const mediaDevices = navigator.mediaDevices

    const detectMicrophones = async () => {
      try {
        const devices = await mediaDevices.enumerateDevices()
        if (cancelled) return
        const hasAudioInput = devices.some(device => device.kind === 'audioinput')
        setHasMicrophone(hasAudioInput)
        setMicDetectionReady(true)
      } catch (error) {
        if (cancelled) return
        console.warn('Microphone detection failed:', error)
        setMicDetectionReady(false)
      }
    }

    detectMicrophones()

    const handleDeviceChange = () => detectMicrophones()

    if (typeof mediaDevices.addEventListener === 'function') {
      mediaDevices.addEventListener('devicechange', handleDeviceChange)
    } else if ('ondevicechange' in mediaDevices) {
      mediaDevices.ondevicechange = handleDeviceChange
    }

    return () => {
      cancelled = true
      if (typeof mediaDevices.removeEventListener === 'function') {
        mediaDevices.removeEventListener('devicechange', handleDeviceChange)
      } else if ('ondevicechange' in mediaDevices) {
        mediaDevices.ondevicechange = null
      }
    }
  }, [])

  // Surface a one-time warning if the browser does not expose speech recognition
  useEffect(() => {
    if (!speechSupported && !micStatusAlertsRef.current.unsupportedNotified) {
      addSystemMessage('Speech recognition is not supported in this browser. Please use Chrome, Edge, or Safari.')
      micStatusAlertsRef.current.unsupportedNotified = true
    }
  }, [speechSupported])

  // Let the user know when no microphones are detected (and only when the state changes)
  useEffect(() => {
    if (!micDetectionReady) return

    const previouslyAvailable = micStatusAlertsRef.current.lastMicAvailable
    if (previouslyAvailable && !hasMicrophone) {
      addSystemMessage('No microphone detected. Please connect a microphone to use voice input.')
    }
    micStatusAlertsRef.current.lastMicAvailable = hasMicrophone
  }, [micDetectionReady, hasMicrophone])

  // Send Message Function
  const sendMessage = () => {
    const message = input.trim()

    if (message && !isDeweyResponding) {
      addMessage(message, 'user')
      setInput('')

      // Dewey starts responding
      deweyRespond(message)
    }
  }

  // Dewey Response Handler
  const deweyRespond = async (userMessage, metadata = {}) => {
    const trimmed = typeof userMessage === 'string' ? userMessage.trim() : ''
    if (!trimmed) return

    // Don't clear recommendations immediately - let them persist until we have new ones
    setIsDeweyResponding(true)
    setIsLoading(true)

    try {
      // Check if user is asking about gaming news
      const newsKeywords = ['news', 'headlines', 'announcement', 'latest', 'recent', 'gaming news', 'whats new', "what's new", 'happening in gaming']
      const isAboutNews = newsKeywords.some(keyword => trimmed.toLowerCase().includes(keyword))

      let enhancedSystemPrompt = systemPrompt

      // Fetch real headlines if asking about news
      if (isAboutNews) {
        try {
          const newsData = await getHeadlines({ limit: 10 })
          if (newsData.headlines && newsData.headlines.length > 0) {
            const headlinesSummary = newsData.headlines
              .slice(0, 10)
              .map((h, i) => `${i + 1}. ${h.source}: "${h.title}" (${h.published_relative})`)
              .join('\n')

            enhancedSystemPrompt = systemPrompt + '\n\n' +
              '=== CURRENT GAMING HEADLINES (Real-time RSS) ===\n' +
              headlinesSummary + '\n' +
              '=== END HEADLINES ===\n\n' +
              'Reference these actual headlines when discussing gaming news. Be specific about sources and recency.'
          }
        } catch (err) {
          console.warn('Failed to fetch news for context:', err)
          // Continue without headlines rather than failing the whole response
        }
      }

      const claudeMessages = buildClaudeMessages({
        history: messagesRef.current,
        systemPrompt: enhancedSystemPrompt,
        userText: trimmed
      })

      const response = await aiChat({
        provider: 'gpt',
        scope: 'state',
        messages: claudeMessages,
        temperature: 0.4,
        max_tokens: 500,
        metadata: {
          panel: 'dewey',
          persona: 'dewey',
          userId: currentUser.id,
          profileName: currentUser.name,
          model: 'gpt-4o-mini',
          ...metadata
        }
      })

      const reply = response?.message?.content || response?.response || ''
      const nextRecommendations = getPanelRecommendationsFromText(trimmed)
      
      // Update recommendations and context
      if (nextRecommendations.length > 0) {
        // New recommendations found - update them
        setRecommendedPanels(nextRecommendations)

        // Build concise summary from the user's last message:
        // last two sentences, capped at ~200 characters.
        const summary = buildHandoffSummary(trimmed, { maxChars: 200, maxSentences: 2 })
        if (summary) setHandoffText(summary)
      }
      // If no new recommendations, keep existing ones (don't clear unless user changes topic)
      const formatted = formatAssistantResponse(
        reply || "I'm still reaching out to the arcade braintrust. Mind rephrasing that?"
      )
      addMessage(formatted, 'dewey')

      // Speak the response if voice is enabled
      if (voiceEnabled && reply) {
        const plainTextReply = htmlToPlainText(reply)
        speakAsDewey(plainTextReply).catch(err => {
          console.warn('TTS failed:', err)
        })
      }

      return response
    } catch (error) {
      console.error('Dewey chat error', error)
      setRecommendedPanels([])
      setHandoffText('')
      const fallback = (() => {
        const messageText = typeof error?.message === 'string' ? error.message : ''
        if (error?.code === 'NOT_CONFIGURED' || /not configured/i.test(messageText)) {
          return 'AI service not configured. Please add API keys in settings.'
        }
        if (messageText) return messageText
        return 'I ran into a glitch while phoning the other agents.'
      })()
      addMessage(`I'm having trouble connecting right now. ${fallback}`, 'dewey', { isError: true })
      return null
    } finally {
      setIsLoading(false)
      setIsDeweyResponding(false)
    }
  }

  const initializeSpeechRecognition = () => {
    if (typeof window === 'undefined') return null
    const SpeechRecognition = window.SpeechRecognition || window.webkitSpeechRecognition
    if (!SpeechRecognition) {
      setSpeechSupported(false)
      return null
    }

    try {
      const recognition = new SpeechRecognition()
      recognition.continuous = false
      recognition.interimResults = true
      recognition.lang = 'en-US'
      recognition.maxAlternatives = 1

      recognition.onresult = (event) => {
        const result = event.results[event.results.length - 1]
        const transcript = result[0].transcript

        if (!result.isFinal) {
          console.log('?? Interim:', transcript)
          setInput(transcript)
          return
        }

        console.log('?? Final Transcribed:', transcript)

        if (processingTranscriptRef.current || transcript === lastTranscriptRef.current) {
          console.log('?? Duplicate transcript ignored')
          return
        }

        processingTranscriptRef.current = true
        lastTranscriptRef.current = transcript
        setInput(transcript)
        setIsRecording(false)

        setTimeout(() => {
          if (transcript.trim()) {
            addMessage(transcript, 'user')
            setInput('')
            deweyRespond(transcript).finally(() => {
              setTimeout(() => {
                processingTranscriptRef.current = false
              }, 1000)
            })
          } else {
            processingTranscriptRef.current = false
          }
        }, 100)
      }

      recognition.onerror = (event) => {
        console.error('Speech recognition error:', event.error)
        setIsRecording(false)
        processingTranscriptRef.current = false

        if (event.error === 'not-allowed') {
          addSystemMessage('Microphone permission denied. Please allow microphone access.')
        } else if (event.error === 'no-speech') {
          addSystemMessage('No speech detected. Please try again.')
        } else if (event.error !== 'aborted') {
          addSystemMessage(`Speech recognition error: ${event.error}`)
        }
      }

      recognition.onend = () => {
        setIsRecording(false)
      }

      recognitionRef.current = recognition
      setSpeechSupported(true)
      return recognition
    } catch (error) {
      console.error('Failed to initialize speech recognition:', error)
      setSpeechSupported(false)
      return null
    }
  }

  // Handle Enter Key
  const handleKeyPress = (event) => {
    if (event.key === 'Enter' && !isDeweyResponding) {
      sendMessage()
    }
  }

  // Initialize Web Speech API
  useEffect(() => {
    initializeSpeechRecognition()
    return () => {
      if (recognitionRef.current) {
        try {
          recognitionRef.current.abort()
        } catch {}
      }
      // Ensure any ongoing speech is stopped when leaving the panel
      try { stopSpeaking() } catch {}
    }
  }, [])

  // Voice Input with Recording State
  const startVoice = () => {
    if (!isRecording) {
      // Stop any ongoing TTS so mic capture is not fighting playback
      try { stopSpeaking() } catch {}
      const recognitionInstance = recognitionRef.current || initializeSpeechRecognition()

      if (!recognitionInstance) {
        if (!micStatusAlertsRef.current.unsupportedNotified) {
          addSystemMessage('Speech recognition is not supported in this browser. Please use Chrome, Edge, or Safari.')
          micStatusAlertsRef.current.unsupportedNotified = true
        }
        setIsRecording(false)
        return
      }

      setIsRecording(true)
      console.log('?? Recording started...')

      try {
        recognitionInstance.start()
      } catch (error) {
        console.error('Failed to start recognition:', error)
        setIsRecording(false)
        addSystemMessage('Failed to start voice recognition. Please try again.')
      }
    } else {
      stopRecording()
    }
  }

  const stopRecording = () => {
    if (recognitionRef.current) {
      recognitionRef.current.stop()
    }
    setIsRecording(false)
    console.log('?? Recording stopped')
  }

  // Quick Action Functions
  const triggerQuickAction = (promptText, metadata) => {
    if (isDeweyResponding) return

    addMessage(promptText, 'user')
    deweyRespond(promptText, metadata)
  }

  const getNewsHeadlines = () => {
    setNewsMode(true)
  }

  const getRecommendations = () => {
    triggerQuickAction(
      'Can you recommend some games for me?',
      { action: 'recommendations' }
    )
  }

  const aboutArcade = () => {
    triggerQuickAction(
      'Tell me about G&G Arcade and what is happening there right now.',
      { action: 'arcade-overview' }
    )
  }

  const getGameTrivia = () => {
    setTriviaMode(true)
  }

  const showPreferences = () => {
    if (isDeweyResponding) return

    if (currentUser.id === 'guest') {
      addSystemMessage('Select a user profile to view preferences, or create a new profile.')
      return
    }

    // Display current user preferences
    const prefs = currentUser.preferences
    let prefsText = `?? ${currentUser.name}'s Gaming Preferences:<br><br>`
    prefsText += `Favorite Genres: ${prefs.genres.length > 0 ? prefs.genres.join(', ') : '[Not set]'}<br>`
    prefsText += `Favorite Franchises: ${prefs.franchises.length > 0 ? prefs.franchises.join(', ') : '[Not set]'}<br>`
    prefsText += `Interests: ${prefs.keywords.length > 0 ? prefs.keywords.join(', ') : '[Not set]'}<br><br>`
    prefsText += `Tell me about games you like and I'll remember them for next time!`

    addMessage("Show me my preferences", 'user')
    setShowTypingIndicator(true)

    setTimeout(() => {
      setShowTypingIndicator(false)
      addMessage(prefsText, 'dewey')
    }, 800)
  }

  async function sendHandoffToServer(targetPanelId, handoffText) {
    try {
      console.log('[Dewey] Sending handoff to server:', { target: targetPanelId, summary: handoffText })
      const response = await fetch('/api/local/dewey/handoff', {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
          'x-panel': 'dewey',
          'x-device-id': 'CAB-0001',
          'x-scope': 'state'
        },
        body: JSON.stringify({
          target: targetPanelId,
          summary: handoffText,
          timestamp: new Date().toISOString()
        })
      })
      console.log('[Dewey] Handoff response:', response.status, response.ok)
    } catch (error) {
      console.error('[Dewey] Handoff send failed:', error)
    }
  }

  const handleOpenPanel = useCallback(async (panel) => {
    if (!panel?.id) return
    console.log('[Dewey] Opening panel:', panel.label, 'ID:', panel.id, 'with context:', handoffText)
    await sendHandoffToServer(panel.id, handoffText)
    const contextParam = handoffText ? `&context=${encodeURIComponent(handoffText)}` : ''
    const url = `/assistants?agent=${encodeURIComponent(panel.id)}${contextParam}`
    console.log('[Dewey] Navigating to URL:', url)
    console.log('[Dewey] Agent parameter will be:', panel.id)
    navigate(url)
  }, [navigate, handoffText])

  // Format timestamp
  const formatTime = (date) => {
    return date.toLocaleTimeString('en-US', {
      hour: '2-digit',
      minute: '2-digit'
    })
  }

  const defaultInputHint = 'Press Enter to send ��� Use quick buttons for common requests'
  const micStatusMessage = !speechSupported
    ? 'Voice input is not supported in this browser.'
    : (micDetectionReady && !hasMicrophone)
      ? 'No microphone detected. Connect a microphone to use voice input.'
      : ''
  const micButtonTitle = micStatusMessage || (isRecording ? 'Stop voice input' : 'Start voice input')
  const inputHintText = micStatusMessage || defaultInputHint
  const shouldShowHandoff = recommendedPanels.length > 0 && Boolean(handoffText)

  return (
    <div className="dewey-panel-wrapper">
      {triviaMode ? (
        <TriviaExperience
          currentUser={currentUser}
          onExit={() => setTriviaMode(false)}
        />
      ) : newsMode ? (
        <GamingNews
          onExit={() => setNewsMode(false)}
        />
      ) : (
        <div className="panel-container">
          {/* Header with User Selection */}
          <div className="header">
          <div className={`avatar ${isDeweyResponding ? 'speaking' : ''}`}>
            <img src="/dewey-avatar.jpeg" alt="Dewey" className="avatar-img" />
          </div>
          <div className="header-info">
            <div className="header-title">
              <h1>Dewey</h1>
              <span className="status-dot"></span>
            </div>
            <div className="subtitle">Your Gaming Companion</div>
          </div>
          <div className="user-selector-wrapper">
            <span style={{ fontSize: '11px', textTransform: 'uppercase', letterSpacing: '0.08em', color: '#88c0ff' }}>
              Chat Profile
            </span>
            <button
              className={`voice-toggle-btn ${voiceEnabled ? 'active' : 'muted'}`}
              onClick={() => {
                if (voiceEnabled) {
                  stopSpeaking()
                }
                setVoiceEnabled(!voiceEnabled)
              }}
              title={voiceEnabled ? 'Voice enabled - Click to mute' : 'Voice muted - Click to enable'}
            >
              <img
                src="/dewey-voice-profile.png"
                alt="Voice preference"
                className="voice-toggle-icon"
              />
            </button>
            <select className="user-selector" value={currentUser.id} onChange={switchUser} aria-label="Select chat profile">
              {userOptions.map(option => (
                <option key={option.id} value={option.id}>{option.label}</option>
              ))}
              <option value="new" style={{ borderTop: '1px solid #00d4ff' }}>? Create New Profile</option>
            </select>
          </div>
        </div>

        {/* Info Bar */}
        <div className="info-bar">
          <span>?? Gaming Chat Mode</span>
          <span>Online & Ready</span>
        </div>

        {/* Chat Messages Area */}
        <div className="chat-messages" ref={messagesContainerRef}>
          {messages.map((msg, idx) => {
            if (msg.role === 'system') {
              return (
                <div
                  key={idx}
                  style={{
                    background: 'rgba(0, 212, 255, 0.05)',
                    border: '1px solid rgba(0, 212, 255, 0.2)',
                    borderRadius: '8px',
                    padding: '10px 14px',
                    fontSize: '12px',
                    color: '#88c0ff',
                    textAlign: 'center',
                    margin: '10px auto',
                    maxWidth: '80%'
                  }}
                >
                  {msg.text}
                </div>
              )
            }

            const msgClassNames = ['message', msg.role]
            if (msg.isError) msgClassNames.push('error')

            return (
              <div key={idx} className={msgClassNames.join(' ')} aria-live="polite">
                <span dangerouslySetInnerHTML={{ __html: msg.text }}></span>
                <div className="message-time">{formatTime(msg.timestamp)}</div>
              </div>
            )
          })}

          {isLoading && (
            <div className="message dewey loading">
              <div className="message-content">
                <span className="typing-indicator">Dewey is thinking...</span>
              </div>
            </div>
          )}

          {/* Typing Indicator */}
          {showTypingIndicator && (
            <div className="typing-indicator">
              <div className="typing-dot"></div>
              <div className="typing-dot"></div>
              <div className="typing-dot"></div>
            </div>
          )}
        </div>

        {shouldShowHandoff && (
          <div className="handoff-section">
            <div className="handoff-title">Dewey suggests these helpers:</div>
            <div className="handoff-subtitle">
              When you open one, you can tell them:
            </div>
            <div className="handoff-quote">
              {handoffText}
            </div>
            <div className="handoff-chips" role="list">
              {recommendedPanels.map(panel => (
                <button
                  key={panel.id}
                  type="button"
                  className="handoff-chip"
                  onClick={() => handleOpenPanel(panel)}
                >
                  {panel.label}
                </button>
              ))}
            </div>
          </div>
        )}

        {/* Quick Action Buttons */}
        <div className="quick-actions">
          <button className="quick-btn" onClick={getNewsHeadlines}>
            <div className="btn-icon-container">
              <img
                src="/dewey-news.png"
                alt="Arcade news"
                className="btn-icon-image"
              />
            </div>
            <div className="btn-label">News</div>
          </button>

          <button className="quick-btn" onClick={getRecommendations}>
            <div className="btn-icon-container">
              <img
                src="/dewey-recommend.png"
                alt="Game recommendations"
                className="btn-icon-image"
              />
            </div>
            <div className="btn-label">Recommend</div>
          </button>

          <button className="quick-btn" onClick={aboutArcade}>
            <div className="btn-icon-container">
              <img
                src="/dewey-arcade.png"
                alt="G&G Arcade status"
                className="btn-icon-image"
              />
            </div>
            <div className="btn-label" aria-hidden="true"></div>
          </button>

          <button className="quick-btn" onClick={getGameTrivia}>
            <div className="btn-icon-container">
              <img
                src="/dewey-trivia.png"
                alt="Gaming trivia"
                className="btn-icon-image"
              />
            </div>
            <div className="btn-label">Trivia</div>
          </button>

          <button className="quick-btn" onClick={showPreferences}>
            <div className="btn-icon-container">
              <img
                src="/dewey-preferences.png"
                alt="Profile preferences"
                className="btn-icon-image"
              />
            </div>
            <div className="btn-label">Preferences</div>
          </button>
        </div>

        {/* Input Area */}
        <div className="input-area">
          <div className="input-wrapper">
            <button
              className={`mic-btn ${isRecording ? 'recording' : ''}`}
              onClick={startVoice}
              title={micButtonTitle}
              aria-label={micButtonTitle}
              aria-pressed={isRecording}
              type="button"
              disabled={isDeweyResponding || !speechSupported}
            >
              <img
                src="/dewey-mic.png"
                alt=""
                aria-hidden="true"
                className="mic-icon"
              />
            </button>
            <input
              ref={inputRef}
              type="text"
              className="chat-input"
              value={input}
              onChange={(e) => setInput(e.target.value)}
              onKeyPress={handleKeyPress}
              placeholder="Ask Dewey anything about gaming..."
              autoComplete="off"
              disabled={isDeweyResponding}
            />
            <button
              className="send-btn"
              onClick={sendMessage}
              title="Send Message"
              disabled={isDeweyResponding || !input.trim()}
            >
              ?
            </button>
          </div>
          <div className="input-hint">{inputHintText}</div>
        </div>
        </div>
      )}
    </div>
  )
}







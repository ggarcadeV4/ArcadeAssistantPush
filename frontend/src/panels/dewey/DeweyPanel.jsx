import React, { useState, useEffect, useRef, useMemo, useCallback } from 'react'
import { useNavigate } from 'react-router-dom'
import './DeweyPanel.css'
import { chat as aiChat } from '../../services/aiClient'
import { speakAsDewey, stopSpeaking, isSpeaking } from '../../services/ttsClient'
import { useProfileContext } from '../../context/ProfileContext'
import { useGemSpeech } from '../../hooks/useGemSpeech'
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

/**
 * Parse a DEWEY_MEDIA JSON payload from the AI response.
 * Convention: <!--DEWEY_MEDIA:{...}-->
 * Returns { cleanText, gallery, lore }
 */
const parseMediaPayload = (rawText) => {
  const result = { cleanText: rawText, gallery: null, lore: null }
  if (!rawText) return result

  const mediaRegex = /<!--DEWEY_MEDIA:(\{[\s\S]*?})-->/
  const match = rawText.match(mediaRegex)
  if (!match) return result

  try {
    const payload = JSON.parse(match[1])
    result.cleanText = rawText.replace(match[0], '').trim()
    if (Array.isArray(payload.gallery) && payload.gallery.length > 0) {
      result.gallery = payload.gallery
    }
    if (payload.lore && payload.lore.title && payload.lore.body) {
      result.lore = payload.lore
    }
  } catch (err) {
    console.warn('Failed to parse DEWEY_MEDIA payload:', err)
  }
  return result
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
    'You are Dewey, the upbeat AI concierge and Arcade Historian for G&G Arcade.',
    'Your job is to QUICKLY route users to the right specialist - do not ask qualifying questions.',
    `Current user: ${user?.name || 'Guest'}. ${preferenceSummary}`,
    AGENT_SUMMARY,
    'Guidelines:',
    '- Keep replies SHORT (1-2 sentences max, under 40 words)',
    '- For technical issues (controllers, LEDs, guns, performance), acknowledge the issue and tell them a specialist chip will appear below',
    '- DO NOT ask follow-up questions - let the specialists handle details',
    '- The UI will automatically show specialist chips based on keywords in the user message',
    '- For gaming chat, news, or trivia, respond normally with 2-3 sentences',
    '',
    '=== ARCADE HISTORIAN MEDIA MODE ===',
    'When the user asks about a specific arcade game, era, or gaming history topic, you MUST append a structured JSON block to your response using this exact format:',
    '<!--DEWEY_MEDIA:{"gallery":[{"title":"GAME NAME","maker":"Publisher","year":"1980","genre":"Genre","description":"One-sentence description.","badges":["Tag1","Year"],"image":"/arcade-gallery/placeholder.jpg"}],"lore":{"title":"Era or Topic Title","body":"2-3 sentence historical context."}}-->',
    'Rules for DEWEY_MEDIA:',
    '- Include 1-3 gallery items when discussing specific games',
    '- Include a lore block when discussing eras, history, or cultural impact',
    '- The JSON must be valid. Use double quotes for keys and string values',
    '- Place the <!--DEWEY_MEDIA:...--> block at the END of your response, after visible text',
    '- Do NOT include the JSON block for non-gaming topics, technical support, or greetings',
    '- For image field, use "/arcade-gallery/" + lowercase-kebab-case game name + ".jpg"',
    '',
    'Examples:',
    '- User: "my button is broken" → "That sounds like a controller issue! Click the Controller Chuck chip below and he\'ll help you troubleshoot."',
    '- User: "light gun not working" → "Gunner can help with that! Click his chip below to get your gun calibrated."',
    '- User: "tell me about pac-man" → "Pac-Man changed everything! Toru Iwatani\'s 1980 masterpiece shifted arcades from shooters to mass appeal.\n<!--DEWEY_MEDIA:{"gallery":[{"title":"PAC-MAN","maker":"Namco","year":"1980","genre":"Maze Chase","description":"The yellow pie-chart that ate the world.","badges":["Iconic","1980"],"image":"/arcade-gallery/pac-man.jpg"}],"lore":{"title":"The Golden Age: 1978-1983","body":"The Golden Age saw arcades transform from novelty to cultural phenomenon, driven by hits like Space Invaders, Pac-Man, and Donkey Kong."}}-->"'
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
  // Get shared profile from context (reactive tenancy)
  const { profile: sharedProfile } = useProfileContext()
  const navigate = useNavigate()

  // State management
  const [triviaMode, setTriviaMode] = useState(false)
  const [newsMode, setNewsMode] = useState(false)
  const [isDeweyResponding, setIsDeweyResponding] = useState(false)
  const [isLoading, setIsLoading] = useState(false)
  const [voiceEnabled, setVoiceEnabled] = useState(true)
  const [messages, setMessages] = useState([
    {
      role: 'dewey',
      text: "Hey there! I'm Dewey, your gaming companion. 🎮<br><br>I can chat about gaming culture, recommend games based on your interests, share the latest gaming news, and tell you all about G&G Arcade!<br><br>What would you like to talk about today?",
      timestamp: new Date()
    }
  ])
  const [input, setInput] = useState('')
  const [showTypingIndicator, setShowTypingIndicator] = useState(false)
  const [recommendedPanels, setRecommendedPanels] = useState([])
  const [handoffText, setHandoffText] = useState('')

  // Media Stage state
  const [galleryItems, setGalleryItems] = useState([])
  const [activeCardIndex, setActiveCardIndex] = useState(0)
  const [loreText, setLoreText] = useState(null)

  // Refs
  const messagesContainerRef = useRef(null)
  const inputRef = useRef(null)
  const messagesRef = useRef(messages)

  // ProfileContext-driven identity (no hardcoded user map)
  const currentUser = useMemo(() => ({
    id: sharedProfile?.userId || 'guest',
    name: sharedProfile?.displayName || 'Guest',
    preferences: {
      genres: sharedProfile?.preferences?.genres || [],
      franchises: sharedProfile?.preferences?.franchises || [],
      keywords: sharedProfile?.preferences?.keywords || []
    }
  }), [sharedProfile])

  const systemPrompt = useMemo(() => buildSystemPrompt(currentUser), [currentUser])

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

  // ========================================
  // useGemSpeech — Gem Architecture STT
  // ========================================
  const handleGemTranscript = useCallback((text) => {
    if (text.trim() && !isDeweyResponding) {
      addMessage(text, 'user')
      setInput('')
      deweyRespond(text)
    }
  }, [isDeweyResponding])

  const {
    isRecording, wsConnected, lastTranscript, warning: speechWarning,
    toggleMic, startRecording, stopRecording
  } = useGemSpeech({
    panelName: 'dewey',
    autoStopEnabled: true,
    onTranscript: handleGemTranscript
  })

  // ========================================
  // HANDOFF LISTENERS (Inbound Events)
  // ========================================
  useEffect(() => {
    const handleTranscriptForward = (e) => {
      const { transcript, source } = e.detail || {}
      if (transcript) {
        addSystemMessage(`[${source || 'Panel'}] forwarded: "${transcript}"`)
        deweyRespond(transcript, { forwarded_by: source })
      }
    }

    const handleSessionBriefing = (e) => {
      const { summary, source } = e.detail || {}
      if (summary) {
        addSystemMessage(`Session briefing from ${source || 'system'}: ${summary}`)
      }
    }

    window.addEventListener('transcript_forward', handleTranscriptForward)
    window.addEventListener('session_briefing', handleSessionBriefing)

    return () => {
      window.removeEventListener('transcript_forward', handleTranscriptForward)
      window.removeEventListener('session_briefing', handleSessionBriefing)
    }
  }, [])

  // Check URL params for handoff context on mount
  useEffect(() => {
    const params = new URLSearchParams(window.location.search)
    const context = params.get('context')
    if (context) {
      addSystemMessage(`Handoff context received`)
      deweyRespond(decodeURIComponent(context), { source: 'handoff' })
    }
  }, [])

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

      const rawReply = response?.message?.content || response?.response || ''
      const nextRecommendations = getPanelRecommendationsFromText(trimmed)

      // Parse gallery / lore media payload from AI response
      const { cleanText: reply, gallery, lore } = parseMediaPayload(rawReply)

      // Populate media stage state
      if (gallery) {
        setGalleryItems(gallery)
        setActiveCardIndex(0)
      }
      if (lore) {
        setLoreText(lore)
      }

      // Update recommendations and context
      if (nextRecommendations.length > 0) {
        setRecommendedPanels(nextRecommendations)
        const summary = buildHandoffSummary(trimmed, { maxChars: 200, maxSentences: 2 })
        if (summary) setHandoffText(summary)
      }

      const formatted = formatAssistantResponse(
        reply || "I'm still reaching out to the arcade braintrust. Mind rephrasing that?"
      )
      addMessage(formatted, 'dewey')

      // Speak the response if voice is enabled (use clean text, not raw)
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

  // Handle Enter Key
  const handleKeyPress = (event) => {
    if (event.key === 'Enter' && !isDeweyResponding) {
      sendMessage()
    }
  }

  // Cleanup TTS on unmount
  useEffect(() => {
    return () => {
      try { stopSpeaking() } catch { }
    }
  }, [])

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
  const speechSupported = typeof navigator !== 'undefined' && !!navigator.mediaDevices
  const micStatusMessage = !speechSupported
    ? 'Voice input is not supported in this browser.'
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
        <>
          {/* === FLOATING HEADER (Identity Pinned) === */}
          <header className="dewey-header-float">
            <div className="dewey-header-pill">
              <div className="identity-section">
                <div className="identity-avatar">
                  <img src="/dewey-avatar.jpeg" alt="Dewey" />
                </div>
                <span className="identity-label">Identity Pinned</span>
              </div>
              <div className="session-section">
                <div className="session-info">
                  <span className="session-label">Historian Session</span>
                  <span className="session-user">{currentUser.name}</span>
                </div>
                <button
                  className="settings-btn"
                  onClick={() => {
                    if (voiceEnabled) stopSpeaking()
                    setVoiceEnabled(!voiceEnabled)
                  }}
                  title={voiceEnabled ? 'Voice enabled' : 'Voice muted'}
                >
                  <span className="material-symbols-outlined">
                    {voiceEnabled ? 'volume_up' : 'volume_off'}
                  </span>
                </button>
              </div>
            </div>
          </header>

          {/* === MAIN CANVAS === */}
          <main className="dewey-main">
            <div className="dewey-canvas" ref={messagesContainerRef}>

              {/* Gallery Carousel (shown when galleryItems exist) */}
              {galleryItems.length > 0 && (
                <div className="gallery-row">
                  {/* Left Side Card */}
                  {galleryItems[activeCardIndex - 1] && (
                    <div
                      className="gallery-card-side"
                      onClick={() => setActiveCardIndex(activeCardIndex - 1)}
                    >
                      <span className="card-year">{galleryItems[activeCardIndex - 1].year}</span>
                      <div className="card-image-wrap">
                        <img src={galleryItems[activeCardIndex - 1].image} alt={galleryItems[activeCardIndex - 1].title} />
                        <div className="card-meta">
                          <h3>{galleryItems[activeCardIndex - 1].title}</h3>
                          <p>{galleryItems[activeCardIndex - 1].maker}</p>
                        </div>
                      </div>
                    </div>
                  )}

                  {/* Active (Center) Card */}
                  {galleryItems[activeCardIndex] && (
                    <div className="gallery-card-active">
                      <div className="card-badges">
                        {galleryItems[activeCardIndex].badges?.map((badge, i) => (
                          <span key={i} className={`badge ${i === 0 ? 'badge-primary' : 'badge-secondary'}`}>
                            {badge}
                          </span>
                        ))}
                      </div>
                      <div className="card-image-wrap">
                        <img src={galleryItems[activeCardIndex].image} alt={galleryItems[activeCardIndex].title} />
                        <div className="card-footer">
                          <h2>{galleryItems[activeCardIndex].title}</h2>
                          <div className="card-meta-row">
                            <span className="card-maker">{galleryItems[activeCardIndex].maker}</span>
                            <span className="dot-sep"></span>
                            <span className="card-genre">{galleryItems[activeCardIndex].genre}</span>
                          </div>
                          <p className="card-desc">{galleryItems[activeCardIndex].description}</p>
                          <div className="card-actions">
                            <button className="inspect-btn">Inspect</button>
                            <button className="fav-btn">
                              <span className="material-symbols-outlined" style={{ fontSize: '14px' }}>favorite</span>
                            </button>
                          </div>
                        </div>
                      </div>
                      <div className="card-inner-glow"></div>
                    </div>
                  )}

                  {/* Right Side Card */}
                  {galleryItems[activeCardIndex + 1] && (
                    <div
                      className="gallery-card-side"
                      onClick={() => setActiveCardIndex(activeCardIndex + 1)}
                    >
                      <span className="card-year">{galleryItems[activeCardIndex + 1].year}</span>
                      <div className="card-image-wrap">
                        <img src={galleryItems[activeCardIndex + 1].image} alt={galleryItems[activeCardIndex + 1].title} />
                        <div className="card-meta">
                          <h3>{galleryItems[activeCardIndex + 1].title}</h3>
                          <p>{galleryItems[activeCardIndex + 1].maker}</p>
                        </div>
                      </div>
                    </div>
                  )}
                </div>
              )}

              {/* Era Analysis / Lore Text */}
              {loreText && (
                <div className="era-analysis">
                  <h3 className="era-title">{loreText.title}</h3>
                  <p className="era-body">{loreText.body}</p>
                </div>
              )}

              {/* Chat Messages */}
              <div className="dewey-chat-messages">
                {messages.map((msg, idx) => {
                  if (msg.role === 'system') {
                    return <div key={idx} className="system-msg">{msg.text}</div>
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

                {showTypingIndicator && (
                  <div className="typing-indicator">
                    <div className="typing-dot"></div>
                    <div className="typing-dot"></div>
                    <div className="typing-dot"></div>
                  </div>
                )}
              </div>

              {/* Handoff Section */}
              {shouldShowHandoff && (
                <div className="dewey-handoff">
                  <div className="handoff-title">Dewey suggests these helpers:</div>
                  <div className="handoff-subtitle">When you open one, you can tell them:</div>
                  <div className="handoff-quote">{handoffText}</div>
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

              {/* === INTERACTION HUB === */}
              <div className="dewey-hub">
                <div className="dewey-hub-inner">

                  {/* Dewey Branding */}
                  <div className="dewey-branding">
                    <div className="dewey-orb avatar-glow-layers">
                      <img src="/dewey-avatar.jpeg" alt="Dewey" />
                    </div>
                    <div className="branding-text">
                      <p className="branding-sub">Archive System Online</p>
                      <h2 className="branding-title">Dewey: The Arcade Historian</h2>
                    </div>
                  </div>

                  {/* Glass Pill Input */}
                  <div className="dewey-input-container">
                    <div className="dewey-input-glow">
                      <div className="dewey-input-bar">
                        <div className="input-left">
                          <span className="material-symbols-outlined voice-icon">graphic_eq</span>
                          <input
                            ref={inputRef}
                            type="text"
                            className="chat-input"
                            value={input}
                            onChange={(e) => setInput(e.target.value)}
                            onKeyPress={handleKeyPress}
                            placeholder="Tell me about the first arcade hit."
                            autoComplete="off"
                            disabled={isDeweyResponding}
                          />
                        </div>
                        <div className="input-right">
                          <button
                            className="voice-status"
                            onClick={toggleMic}
                            title={isRecording ? 'Stop recording' : 'Start voice input'}
                            type="button"
                          >
                            <div className={`voice-dot ${isRecording ? 'recording' : wsConnected ? '' : 'inactive'}`}></div>
                            <span className={`voice-label ${isRecording ? 'recording' : wsConnected ? '' : 'inactive'}`}>
                              {isRecording ? 'Recording' : wsConnected ? 'Active' : 'Offline'}
                            </span>
                          </button>
                          <button
                            className="send-btn"
                            onClick={sendMessage}
                            title="Send Message"
                            disabled={isDeweyResponding || !input.trim()}
                          >
                            <span className="material-symbols-outlined">send</span>
                          </button>
                        </div>
                      </div>
                    </div>
                    {speechWarning && <div className="dewey-speech-warning">{speechWarning}</div>}
                  </div>

                  {/* Quick Action Pills */}
                  <div className="dewey-pills">
                    <button className="pill-starter" onClick={getNewsHeadlines}>
                      <span className="material-symbols-outlined" style={{ color: 'var(--primary)', fontSize: '14px' }}>newspaper</span>
                      <span className="pill-label">Gaming News</span>
                    </button>
                    <button className="pill-starter" onClick={getRecommendations}>
                      <span className="material-symbols-outlined" style={{ color: 'var(--secondary)', fontSize: '14px' }}>auto_awesome</span>
                      <span className="pill-label">Recommended</span>
                    </button>
                    <button className="pill-starter" onClick={aboutArcade}>
                      <span className="material-symbols-outlined" style={{ color: 'var(--primary)', fontSize: '14px' }}>sports_esports</span>
                      <span className="pill-label">G&G Arcade</span>
                    </button>
                    <button className="pill-starter" onClick={getGameTrivia}>
                      <span className="material-symbols-outlined" style={{ color: 'var(--secondary)', fontSize: '14px' }}>psychology</span>
                      <span className="pill-label">Trivia</span>
                    </button>
                  </div>

                </div>
              </div>

            </div>
          </main>

          {/* === TELEMETRY FOOTER === */}
          <footer className="dewey-footer">
            <div className="dewey-footer-inner">
              <div className="status-group">
                <div className="status-item">
                  <span className="status-dot-primary"></span>
                  <span>{wsConnected ? 'Sub-Space Link Active' : 'Link Standby'}</span>
                </div>
                <div className="status-item">
                  <span className="status-dot-secondary"></span>
                  <span>Archive Ready</span>
                </div>
              </div>
              <div className="status-group">
                <span>Protocol 9.04.1</span>
              </div>
            </div>
          </footer>
        </>
      )}
    </div>
  )
}







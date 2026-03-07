import React, { useState, useEffect, useRef, useMemo, useCallback } from 'react'
import { useNavigate } from 'react-router-dom'
import './DeweyPanel.css'
import { chat as aiChat } from '../../services/aiClient'
import { speakAsDewey, stopSpeaking, isSpeaking } from '../../services/ttsClient'
import { useProfileContext } from '../../context/ProfileContext'
import useGemSpeech from '../../hooks/useGemSpeech'
import { getHeadlines } from '../../services/newsClient'
import TriviaExperience from './trivia/TriviaExperience'
import GamingNews from './news/GamingNews'
import { searchArcadeLore } from '../../services/deweySearchClient'


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

// Parse structured ```json blocks from AI response, returning { text, media }
const parseMediaPayload = (raw = '') => {
  const jsonBlockRe = /```json\s*([\s\S]*?)```/g
  let media = null
  let text = raw

  const match = jsonBlockRe.exec(raw)
  if (match) {
    try {
      media = JSON.parse(match[1].trim())
    } catch (e) {
      console.warn('[Dewey] Failed to parse media JSON block:', e)
    }
    // Strip the JSON block from the visible text
    text = raw.replace(match[0], '').trim()
  }
  return { text, media }
}

// Default gallery items shown before any game query
const DEFAULT_GALLERY = [
  { title: 'Donkey Kong', publisher: 'Nintendo', year: '1981', genre: 'Platform', image: '/dewey-trivia.png', description: 'Shigeru Miyamoto\'s debut masterpiece introduced Jumpman and the princess-rescue formula.' },
  { title: 'PAC-MAN', publisher: 'Namco', year: '1980', genre: 'Maze Chase', image: '/dewey-arcade.png', description: 'The yellow pie-chart that ate the world. Toru Iwatani\'s masterpiece shifted arcades from shooters to mass appeal.', tags: ['Iconic'] },
  { title: 'Galaga', publisher: 'Namco', year: '1981', genre: 'Fixed Shooter', image: '/dewey-recommend.png', description: 'The sequel to Galaxian perfected the fixed-shooter formula with its dual-ship capture mechanic.' }
]

const DEFAULT_LORE = 'The Golden Age of Arcade Games was a peak era of arcade video game popularity, innovation, and earnings. From space shooters to maze chases, these cabinets defined a generation\'s culture.'
const DEFAULT_ERA = 'Era Analysis: 1978-1983'

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
    'You are Dewey, the Arcade Historian and AI concierge for G&G Arcade.',
    'You synthesize technical lore and media on demand about arcade games, cabinets, and gaming history.',
    `Current user: ${user?.name || 'Guest'}. ${preferenceSummary}`,
    AGENT_SUMMARY,
    '',
    '=== YOUR CAPABILITIES ===',
    'You have a VISUAL GALLERY built into your interface that automatically displays arcade cabinet images, game screenshots, and technical specs.',
    'When you talk about a game, the gallery AUTOMATICALLY fetches and shows real images of the arcade cabinet, flyer art, and gameplay screenshots.',
    'You CAN and DO show images. NEVER say you cannot show images or pictures. The gallery handles it visually.',
    'When a user asks to see a cabinet or what a game looks like, confidently describe it AND know that the gallery above your response is showing them the actual image.',
    '',
    '=== MEDIA MODE ===',
    'When the user asks about a SPECIFIC game or arcade cabinet, you MUST include a ```json metadata block at the END of your response.',
    'The JSON block should contain an array of 1-3 game objects with these fields:',
    '  { "title": "Game Name", "publisher": "Publisher", "year": "1980", "genre": "Genre",',
    '    "cpu": "Z80 @ 3.072 MHz", "resolution": "224x288", "description": "2-3 sentence lore",',
    '    "tags": ["Iconic", "Golden Age"], "era": "Era title", "eraDescription": "Era summary" }',
    'The first item is the PRIMARY game (shown as the center card). Include 1-2 related games as side cards.',
    'Outside the JSON block, write a SHORT conversational response (2-3 sentences).',
    'Reference the gallery: say things like "Check out the gallery above!" or "I\'ve pulled up the cabinet for you" or "Take a look at that classic artwork above."',
    '',
    '=== ROUTING MODE ===',
    'For technical issues (controllers, LEDs, guns, performance), acknowledge briefly and note a specialist chip will appear.',
    'For general chat, news, or trivia, respond normally with 2-3 sentences.',
    '',
    'Guidelines:',
    '- Keep conversational replies SHORT (2-3 sentences, under 60 words)',
    '- NEVER say you cannot show images, pictures, or visuals — your gallery does this automatically',
    '- DO NOT ask follow-up questions for technical issues - let specialists handle details',
    '- The UI will automatically show specialist chips based on keywords',
    '- For game queries, ALWAYS include the ```json block so the gallery can render',
    '- Be enthusiastic about showing off arcade history — you are a museum curator with a digital exhibit'
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
  const [galleryItems, setGalleryItems] = useState(DEFAULT_GALLERY)
  const [loreText, setLoreText] = useState(DEFAULT_LORE)
  const [eraTitle, setEraTitle] = useState(DEFAULT_ERA)
  const [showGallery, setShowGallery] = useState(false)
  const [activeCardIndex, setActiveCardIndex] = useState(0)
  const [techBriefing, setTechBriefing] = useState(null)
  const [techBriefingLoading, setTechBriefingLoading] = useState(false)
  const [isExpanded, setIsExpanded] = useState(false)
  const isFetchingMore = useRef(false)


  // Refs
  const isMounted = useRef(true)
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

  // Stop TTS when panel unmounts (prevents audio echo after exit)
  useEffect(() => {
    return () => {
      stopSpeaking()
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

  // Speech warnings are handled by useGemSpeech onError callback
  // No legacy browser SpeechRecognition warnings needed

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
      // Detect if this is a lore/game query → trigger parallel search
      const loreKeywords = [
        'tell me about', 'what is', 'what was', 'history of', 'who made',
        'when was', 'how did', 'cabinet', 'arcade game', 'arcade machine',
        'pac-man', 'pacman', 'donkey kong', 'galaga', 'space invaders',
        'street fighter', 'mortal kombat', 'asteroids', 'centipede',
        'defender', 'robotron', 'tempest', 'joust', 'dig dug',
        'frogger', 'q*bert', 'qbert', 'missile command', 'battlezone',
        'dragon\'s lair', 'tron', 'punch-out', 'double dragon',
        'golden axe', 'out run', 'after burner', 'r-type',
        'metal slug', 'neo geo', 'cps', 'mvs', 'jamma',
        'specs', 'cpu', 'hardware', 'pcb', 'release year', 'developer'
      ]
      const lower = trimmed.toLowerCase()
      const isLoreQuery = loreKeywords.some(kw => lower.includes(kw))

      // Fire search in parallel if it looks like a lore query
      let searchPromise = null
      if (isLoreQuery) {
        console.log('[Dewey] Lore query detected, firing parallel search:', trimmed)
        searchPromise = searchArcadeLore(trimmed).catch(err => {
          console.warn('[Dewey] Search failed:', err)
          return { items: [] }
        })
      }

      // Check if user is asking about gaming news
      const newsKeywords = ['news', 'headlines', 'announcement', 'latest', 'recent', 'gaming news', 'whats new', "what's new", 'happening in gaming']
      const isAboutNews = newsKeywords.some(keyword => lower.includes(keyword))

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
        provider: 'gemini',
        scope: 'state',
        messages: claudeMessages,
        temperature: 0.4,
        max_tokens: 800,
        metadata: {
          panel: 'dewey',
          persona: 'dewey',
          userId: currentUser.id,
          profileName: currentUser.name,
          model: 'gemini-2.0-flash',
          ...metadata
        }
      })

      const rawReply = response?.message?.content || response?.response || ''

      // Parse media payload: strip ```json blocks and populate gallery
      const { text: cleanReply, media } = parseMediaPayload(rawReply)

      // Resolve parallel search if it was fired
      let searchItems = []
      if (searchPromise) {
        const searchResult = await searchPromise
        searchItems = searchResult?.items || []
      }

      // Populate gallery: prefer search results, fall back to inline media payload
      const gallerySource = searchItems.length > 0 ? searchItems : (media ? (Array.isArray(media) ? media : [media]) : [])
      if (gallerySource.length > 0 && gallerySource[0].title) {
        console.log('[Dewey] Gallery populated:', gallerySource.map(g => g.title))
        setGalleryItems(gallerySource.map(g => ({
          title: g.title || 'Unknown',
          publisher: g.publisher || g.developer || '',
          year: String(g.year || ''),
          genre: g.genre || '',
          cpu: g.cpu || '',
          resolution: g.resolution || '',
          description: g.description || '',
          tags: Array.isArray(g.tags) ? g.tags : [],
          image: g.image || ''
        })))
        if (gallerySource[0].eraDescription) setLoreText(gallerySource[0].eraDescription)
        if (gallerySource[0].era) setEraTitle(gallerySource[0].era)
        setShowGallery(true)
      }

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
        cleanReply || "I'm still reaching out to the arcade braintrust. Mind rephrasing that?"
      )
      addMessage(formatted, 'dewey')

      // Speak the response if voice is enabled and component is still mounted
      if (voiceEnabled && cleanReply && isMounted.current) {
        const plainTextReply = htmlToPlainText(cleanReply)
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


  // Cleanup TTS on unmount
  useEffect(() => {
    isMounted.current = true
    return () => {
      isMounted.current = false
      try { stopSpeaking() } catch { }
    }
  }, [])

  // Handle Enter Key
  const handleKeyPress = (event) => {
    if (event.key === 'Enter' && !isDeweyResponding) {
      sendMessage()
    }
  }

  // Voice Input with Recording State
  const startVoice = () => {
    if (!isRecording) {
      try { stopSpeaking() } catch { }
      startRecording()
    } else {
      stopRecording()
    }
  }

  // Vicky Handoff Listener: listen for transcript_forward and session_briefing on /ws/session
  useEffect(() => {
    if (typeof window === 'undefined') return

    const isSecure = window.location.protocol === 'https:'
    const host = window.location.port === '5173' ? 'localhost:8787' : window.location.host
    const scheme = isSecure ? 'wss' : 'ws'
    const wsUrl = `${scheme}://${host}/ws/session`

    let alive = true
    let ws = null
    let backoff = 2000

    const connectVicky = () => {
      if (!alive) return
      try {
        ws = new WebSocket(wsUrl)
        ws.onopen = () => {
          console.log('[Dewey] Vicky handoff listener connected')
          backoff = 2000
        }
        ws.onmessage = (event) => {
          try {
            const msg = JSON.parse(event.data || '{}')
            if (msg.type === 'transcript_forward' && msg.text) {
              console.log('[Dewey] Vicky transcript forwarded:', msg.text)
              addMessage(msg.text, 'user', { source: 'vicky' })
              deweyRespond(msg.text, { source: 'vicky_handoff' })
            } else if (msg.type === 'session_briefing' && msg.summary) {
              console.log('[Dewey] Vicky session briefing:', msg.summary)
              addSystemMessage(`Vicky briefing: ${msg.summary}`)
            }
          } catch { /* ignore */ }
        }
        ws.onclose = () => {
          if (!alive) return
          setTimeout(connectVicky, backoff)
          backoff = Math.min(backoff * 2, 30000)
        }
        ws.onerror = () => { try { ws.close() } catch { } }
      } catch {
        setTimeout(connectVicky, backoff)
        backoff = Math.min(backoff * 2, 30000)
      }
    }

    connectVicky()

    return () => {
      alive = false
      if (ws) try { ws.close() } catch { }
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

  // Carousel Rotation: click a side card to rotate it to center
  const rotateCarousel = useCallback((clickedIndex) => {
    if (clickedIndex === activeCardIndex || galleryItems.length < 2) return
    const item = galleryItems[clickedIndex]
    if (!item) return

    // Reorder: clicked item becomes index 0 (center)
    const reordered = [item, ...galleryItems.filter((_, i) => i !== clickedIndex)]
    setGalleryItems(reordered)
    setActiveCardIndex(0)
    setTechBriefing(null)

    // Update lore text to match the new center card
    if (item.eraDescription) setLoreText(item.eraDescription)
    if (item.era) setEraTitle(item.era)
    else setEraTitle(`${item.title} · ${item.year}`)

    console.log('[Dewey] Carousel rotated to:', item.title)
  }, [galleryItems, activeCardIndex])

  // Stat Expansion: click a data point on the active card for deeper lore
  const fetchTechBriefing = useCallback(async (statType, game) => {
    if (techBriefingLoading || !game?.title) return
    setTechBriefingLoading(true)
    setTechBriefing(null)

    const queryMap = {
      year: `Tell me about the arcade industry in ${game.year} when ${game.title} was released. What else came out that year?`,
      publisher: `Tell me about ${game.publisher} as an arcade game developer. What were their most important contributions?`,
      cpu: `Explain the ${game.cpu || 'hardware'} used in the ${game.title} arcade cabinet. What made this hardware special for its time?`,
      genre: `Deep dive into the ${game.genre} genre in arcade gaming. How did ${game.title} define or evolve it?`
    }
    const query = queryMap[statType] || `Tell me more about ${game.title} ${statType}`

    console.log('[Dewey] Tech briefing requested:', statType, game.title)

    try {
      const result = await searchArcadeLore(query)
      const briefingItem = result?.items?.[0]
      if (briefingItem) {
        setTechBriefing({
          statType,
          title: `Technical Briefing: ${statType === 'cpu' ? game.cpu : statType === 'year' ? game.year : statType === 'publisher' ? game.publisher : game.genre}`,
          content: briefingItem.description || briefingItem.eraDescription || '',
          game: game.title
        })
        if (briefingItem.eraDescription) setLoreText(briefingItem.eraDescription)
        if (briefingItem.era) setEraTitle(briefingItem.era)
      }

      // HES Integration: if the deep-dive relates to hardware/maintenance, generate Doc chip
      const hardwareKeywords = ['cpu', 'hardware', 'pcb', 'board', 'chip', 'processor', 'capacitor', 'monitor', 'crt', 'power supply']
      const isHardwareRelated = statType === 'cpu' || hardwareKeywords.some(kw => query.toLowerCase().includes(kw))
      if (isHardwareRelated) {
        setRecommendedPanels(prev => {
          const hasDoc = prev.some(p => p.id === 'system-health')
          if (hasDoc) return prev
          return [...prev, { id: 'system-health', label: 'Doc (Hardware Diagnostics)' }]
        })
        setHandoffText(`Hardware deep-dive on ${game.title}: ${game.cpu || 'arcade PCB'}`)
      }
    } catch (err) {
      console.warn('[Dewey] Tech briefing failed:', err)
      setTechBriefing({ statType, title: 'Briefing Unavailable', content: 'Could not fetch deeper lore at this time.', game: game.title })
    } finally {
      setTechBriefingLoading(false)
    }
  }, [techBriefingLoading])

  // Hero Card Expansion: toggle expanded view of the active card
  const toggleExpand = useCallback(() => {
    setIsExpanded(prev => !prev)
  }, [])

  // Category Navigation: click a badge to search for related games
  const categorySearch = useCallback(async (category, value, currentGame) => {
    if (!value || isDeweyResponding) return

    const queryMap = {
      year: `Show me other iconic arcade games from ${value}`,
      publisher: `Show me the best arcade games made by ${value}`,
      genre: `Show me classic ${value} arcade games`
    }
    const query = queryMap[category] || `Show me arcade games related to ${value}`

    console.log('[Dewey] Category search:', category, value)
    setIsLoading(true)
    setIsExpanded(false)
    setTechBriefing(null)

    try {
      const result = await searchArcadeLore(query)
      if (result?.items?.length > 0) {
        setGalleryItems(result.items.map(g => ({
          title: g.title || 'Unknown',
          publisher: g.publisher || '',
          year: String(g.year || ''),
          genre: g.genre || '',
          cpu: g.cpu || '',
          resolution: g.resolution || '',
          description: g.description || '',
          tags: Array.isArray(g.tags) ? g.tags : [],
          image: g.image || ''
        })))
        if (result.items[0].eraDescription) setLoreText(result.items[0].eraDescription)
        if (result.items[0].era) setEraTitle(result.items[0].era)
        setActiveCardIndex(0)
        setShowGallery(true)
        addSystemMessage(`Showing ${category}: ${value}`)
      }
    } catch (err) {
      console.warn('[Dewey] Category search failed:', err)
    } finally {
      setIsLoading(false)
    }
  }, [isDeweyResponding])

  // Infinite Carousel: fetch more items when reaching the last card
  const fetchMoreCarouselItems = useCallback(async () => {
    if (isFetchingMore.current || galleryItems.length === 0) return
    isFetchingMore.current = true

    const lastItem = galleryItems[galleryItems.length - 1]
    const query = `Show me 3 arcade games related to ${lastItem.title} from the ${lastItem.era || 'same era'}`

    console.log('[Dewey] Infinite carousel: fetching more items related to', lastItem.title)

    try {
      const result = await searchArcadeLore(query)
      if (result?.items?.length > 0) {
        const newItems = result.items
          .filter(g => !galleryItems.some(existing => existing.title.toLowerCase() === (g.title || '').toLowerCase()))
          .map(g => ({
            title: g.title || 'Unknown',
            publisher: g.publisher || '',
            year: String(g.year || ''),
            genre: g.genre || '',
            cpu: g.cpu || '',
            resolution: g.resolution || '',
            description: g.description || '',
            tags: Array.isArray(g.tags) ? g.tags : [],
            image: g.image || ''
          }))

        if (newItems.length > 0) {
          setGalleryItems(prev => [...prev, ...newItems])
          console.log('[Dewey] Infinite carousel: added', newItems.length, 'items:', newItems.map(g => g.title))
        }
      }
    } catch (err) {
      console.warn('[Dewey] Infinite carousel fetch failed:', err)
    } finally {
      isFetchingMore.current = false
    }
  }, [galleryItems])

  // Trigger infinite fetch when rotating to the last card
  useEffect(() => {
    if (showGallery && galleryItems.length > 0) {
      // If the current center card is the last or second-to-last, prefetch more
      const isNearEnd = galleryItems.length <= 3
      if (isNearEnd && !isFetchingMore.current) {
        fetchMoreCarouselItems()
      }
    }
  }, [galleryItems.length, showGallery, fetchMoreCarouselItems])

  // HES Drill Down: generate persistent LoRa + Sam chips when gallery is active
  useEffect(() => {
    if (!showGallery || galleryItems.length === 0) return
    const primary = galleryItems[0]
    if (!primary?.title) return

    const hesChips = []
    // LoRa chip for library management
    if (!recommendedPanels.some(p => p.id === 'launchbox')) {
      hesChips.push({ id: 'launchbox', label: `LoRa: Find "${primary.title}" in Library` })
    }
    // Sam chip for historical high scores
    if (!recommendedPanels.some(p => p.id === 'scorekeeper')) {
      hesChips.push({ id: 'scorekeeper', label: `Sam: ${primary.title} High Scores` })
    }

    if (hesChips.length > 0) {
      setRecommendedPanels(prev => {
        const merged = [...prev]
        for (const chip of hesChips) {
          if (!merged.some(p => p.id === chip.id)) merged.push(chip)
        }
        return merged
      })
      setHandoffText(`Exploring ${primary.title} (${primary.year}) — ${primary.publisher}`)
    }
  }, [showGallery, galleryItems, recommendedPanels])

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
    <div className="dewey-historian">
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
          {/* Ambient background blobs */}
          <div className="dh-ambient">
            <div className="dh-ambient-cyan"></div>
            <div className="dh-ambient-lime"></div>
          </div>

          {/* Floating header pill */}
          <header className="dh-header">
            <div className="glass-pill dh-header-inner">
              <div className="dh-header-identity">
                <div className="dh-header-avatar">
                  <img src="/dewey-avatar.jpeg" alt="Dewey" />
                </div>
                <div className="dh-profile-select-wrap">
                  <span className="dh-profile-select-tag">Identity</span>
                  <span className="dh-profile-select" aria-label="Current profile">
                    {currentUser.name || 'Guest'}
                  </span>
                </div>
              </div>
              <div className="dh-header-session">
                <div className="dh-header-session-info">
                  <span className="dh-header-session-tag">Historian Session</span>
                  <span className="dh-header-session-user">{currentUser.name || 'Guest Archeologist'}</span>
                </div>
              </div>
            </div>
          </header>

          {/* Main scrollable content */}
          <main className="dh-main">
            <div className="dh-scroll-area" ref={messagesContainerRef}>

              {/* Gallery carousel — shown when a lore search returns results */}
              {showGallery && galleryItems.length > 0 && (() => {
                const primary = galleryItems[0]
                const showLeft = galleryItems.length >= 2 ? galleryItems[1] : null
                const showRight = galleryItems.length >= 3 ? galleryItems[2] : null

                return (
                  <>
                    {/* Dim overlay when expanded */}
                    {isExpanded && <div className="dh-expand-overlay" onClick={toggleExpand}></div>}

                    <div className={`dh-gallery ${isExpanded ? 'dh-gallery-expanded' : ''}`}>
                      {showLeft && !isExpanded && (
                        <div className="dh-card-side" onClick={() => rotateCarousel(1)} role="button" tabIndex={0} aria-label={`View ${showLeft.title}`}>
                          <div className="dh-card-year-badge">{showLeft.year}</div>
                          <div className="dh-card-img-wrap">
                            <div className="dh-card-gradient-up"></div>
                            {showLeft.image && <img src={showLeft.image} alt={showLeft.title} />}
                            <div className="dh-card-side-info">
                              <h3>{showLeft.title}</h3>
                              <p>{showLeft.publisher}</p>
                            </div>
                          </div>
                        </div>
                      )}
                      {primary && (
                        <div className={`dh-card-active ${isExpanded ? 'dh-card-hero-expanded' : ''}`}>
                          <div className="dh-card-active-tags">
                            {primary.tags?.map((tag, i) => (
                              <div key={i} className={`${i === 0 ? 'dh-tag-cyan' : 'dh-tag-lime'} dh-stat-click`}
                                onClick={() => categorySearch(i === 0 ? 'genre' : 'year', i === 0 ? primary.genre : primary.year, primary)}
                                title={`Browse more ${i === 0 ? primary.genre : primary.year} games`}>
                                {tag}
                              </div>
                            ))}
                            {primary.year && (
                              <div className="dh-tag-lime dh-stat-click"
                                onClick={() => categorySearch('year', primary.year, primary)}
                                title={`Browse more games from ${primary.year}`}>
                                {primary.year}
                              </div>
                            )}
                          </div>
                          <div className="dh-card-img-wrap">
                            <div className="dh-card-gradient-down"></div>
                            {primary.image && <img src={primary.image} alt={primary.title} />}
                            <div className="dh-card-active-overlay">
                              <h2>{primary.title}</h2>
                              <div className="dh-card-active-meta">
                                <span className="dh-publisher dh-stat-click"
                                  onClick={() => categorySearch('publisher', primary.publisher, primary)}
                                  title={`Browse more games by ${primary.publisher}`}>
                                  {primary.publisher}
                                </span>
                                <span className="dh-dot"></span>
                                <span className="dh-genre dh-stat-click"
                                  onClick={() => categorySearch('genre', primary.genre, primary)}
                                  title={`Browse more ${primary.genre} games`}>
                                  {primary.genre}
                                </span>
                                {primary.cpu && (
                                  <>
                                    <span className="dh-dot"></span>
                                    <span className="dh-genre dh-stat-click dh-cpu-stat"
                                      onClick={() => fetchTechBriefing('cpu', primary)}
                                      title="Click for hardware deep-dive">
                                      {primary.cpu}
                                    </span>
                                  </>
                                )}
                              </div>
                              <p className="dh-card-active-desc">{primary.description}</p>
                              {/* Expanded tech specs */}
                              {isExpanded && (
                                <div className="dh-expanded-specs">
                                  {primary.resolution && (
                                    <div className="dh-spec-row">
                                      <span className="material-symbols-outlined" style={{ fontSize: 14 }}>monitor</span>
                                      <span>Resolution: {primary.resolution}</span>
                                    </div>
                                  )}
                                  {primary.cpu && (
                                    <div className="dh-spec-row">
                                      <span className="material-symbols-outlined" style={{ fontSize: 14 }}>memory</span>
                                      <span>CPU: {primary.cpu}</span>
                                    </div>
                                  )}
                                  <div className="dh-spec-row">
                                    <span className="material-symbols-outlined" style={{ fontSize: 14 }}>business</span>
                                    <span>Developer: {primary.publisher}</span>
                                  </div>
                                  <div className="dh-spec-row">
                                    <span className="material-symbols-outlined" style={{ fontSize: 14 }}>calendar_month</span>
                                    <span>Released: {primary.year}</span>
                                  </div>
                                </div>
                              )}
                              {/* Inspect / Collapse button */}
                              <div className="dh-card-active-actions">
                                <button className="dh-btn-inspect" onClick={toggleExpand}>
                                  {isExpanded ? 'Collapse' : 'Inspect'}
                                </button>
                              </div>
                            </div>
                          </div>
                          <div className="dh-card-active-border"></div>
                        </div>
                      )}
                      {showRight && (
                        <div className="dh-card-side" onClick={() => rotateCarousel(2)} role="button" tabIndex={0} aria-label={`View ${showRight.title}`}>
                          <div className="dh-card-year-badge">{showRight.year}</div>
                          <div className="dh-card-img-wrap">
                            <div className="dh-card-gradient-up"></div>
                            {showRight.image && <img src={showRight.image} alt={showRight.title} />}
                            <div className="dh-card-side-info">
                              <h3>{showRight.title}</h3>
                              <p>{showRight.publisher}</p>
                            </div>
                          </div>
                        </div>
                      )}
                    </div>
                    <div className="dh-era-analysis">
                      <h3>{eraTitle}</h3>
                      <p>{loreText}</p>
                    </div>
                    {/* Technical Briefing — expanded stat deep-dive */}
                    {techBriefingLoading && (
                      <div className="dh-tech-briefing dh-tech-loading">
                        <span className="material-symbols-outlined dh-tech-icon">science</span>
                        <span>Researching deeper lore...</span>
                      </div>
                    )}
                    {techBriefing && !techBriefingLoading && (
                      <div className="dh-tech-briefing">
                        <div className="dh-tech-header">
                          <span className="material-symbols-outlined dh-tech-icon">science</span>
                          <h4>{techBriefing.title}</h4>
                          <button className="dh-tech-close" onClick={() => setTechBriefing(null)} aria-label="Close briefing">
                            <span className="material-symbols-outlined">close</span>
                          </button>
                        </div>
                        <p className="dh-tech-content">{techBriefing.content}</p>
                      </div>
                    )}
                  </>
                )
              })()}

              {/* Chat messages */}
              <div className="dh-chat-messages">
                {messages.map((msg, idx) => {
                  if (msg.role === 'system') {
                    return (
                      <div key={idx} className="dh-system-msg">
                        {msg.text}
                      </div>
                    )
                  }

                  const cls = ['dh-message', msg.role]
                  if (msg.isError) cls.push('error')

                  return (
                    <div key={idx} className={cls.join(' ')} aria-live="polite">
                      {msg.role === 'dewey' && (
                        <div className="dh-msg-avatar">
                          <img src="/dewey-avatar.jpeg" alt="Dewey" />
                        </div>
                      )}
                      <div className="dh-msg-body">
                        <span dangerouslySetInnerHTML={{ __html: msg.text }}></span>
                        <div className="dh-message-time">{formatTime(msg.timestamp)}</div>
                      </div>
                    </div>
                  )
                })}

                {isLoading && (
                  <div className="dh-typing">
                    <div className="dh-msg-avatar">
                      <img src="/dewey-avatar.jpeg" alt="Dewey" />
                    </div>
                    <span>Dewey is thinking...</span>
                  </div>
                )}
              </div>

              {/* Handoff chips */}
              {shouldShowHandoff && (
                <div className="dh-handoff">
                  <div className="dh-handoff-title">Dewey suggests these helpers:</div>
                  <div className="dh-handoff-subtitle">When you open one, you can tell them:</div>
                  <div className="dh-handoff-quote">{handoffText}</div>
                  <div className="dh-handoff-chips" role="list">
                    {recommendedPanels.map(panel => (
                      <button
                        key={panel.id}
                        type="button"
                        className="dh-handoff-chip"
                        onClick={() => handleOpenPanel(panel)}
                      >
                        {panel.label}
                      </button>
                    ))}
                  </div>
                </div>
              )}

              {/* Bottom dock: avatar + input + pills */}
              <div className="dh-dock">
                <div className="dh-dock-inner">
                  {/* Dewey title block */}
                  <div className="dh-avatar-block">
                    <div style={{ textAlign: 'center' }}>
                      <p className="dh-archive-tag">Archive System Online</p>
                      <h2>Dewey: The Arcade Historian</h2>
                    </div>
                  </div>

                  {/* Input bar */}
                  <div className="dh-input-wrap">
                    <div className="dh-input-glow">
                      <div className="glass-pill dh-input-bar">
                        <div className="dh-input-left">
                          <button
                            className={`dh-eq-btn ${isRecording ? 'recording' : ''}`}
                            onClick={startVoice}
                            title={micButtonTitle}
                            aria-label={micButtonTitle}
                            aria-pressed={isRecording}
                            type="button"
                            disabled={isDeweyResponding || !speechSupported}
                          >
                            <span className="material-symbols-outlined dh-eq-icon">graphic_eq</span>
                          </button>
                          <input
                            ref={inputRef}
                            type="text"
                            value={input}
                            onChange={(e) => setInput(e.target.value)}
                            onKeyPress={handleKeyPress}
                            placeholder="Tell me about the first arcade hit."
                            autoComplete="off"
                            disabled={isDeweyResponding}
                          />
                        </div>
                        <div className="dh-input-right">
                          <div className="dh-status-pill">
                            <div className="dh-status-dot"></div>
                            <span className="dh-status-label">Active</span>
                          </div>
                          <button
                            className="dh-send-btn"
                            onClick={sendMessage}
                            title="Send Message"
                            disabled={isDeweyResponding || !input.trim()}
                          >
                            <span className="material-symbols-outlined" style={{ fontWeight: 700 }}>send</span>
                          </button>
                        </div>
                      </div>
                    </div>

                    {/* Quick-action pills */}
                    <div className="dh-pills">
                      <button className="dh-pill" onClick={getNewsHeadlines}>
                        <span className="material-symbols-outlined" style={{ fontSize: 14, color: 'var(--dh-primary)' }}>newspaper</span>
                        <span className="dh-pill-label">Gaming News</span>
                      </button>
                      <button className="dh-pill" onClick={getRecommendations}>
                        <span className="material-symbols-outlined" style={{ fontSize: 14, color: 'var(--dh-secondary)' }}>auto_awesome</span>
                        <span className="dh-pill-label">Recommended</span>
                      </button>
                      <button className="dh-pill" onClick={aboutArcade}>
                        <span className="material-symbols-outlined" style={{ fontSize: 14, color: 'var(--dh-primary)' }}>sports_esports</span>
                        <span className="dh-pill-label">G&G Arcade</span>
                      </button>
                      <button className="dh-pill" onClick={getGameTrivia}>
                        <span className="material-symbols-outlined" style={{ fontSize: 14, color: 'var(--dh-secondary)' }}>psychology</span>
                        <span className="dh-pill-label">Trivia</span>
                      </button>
                    </div>
                  </div>
                </div>
              </div>
            </div>
          </main>

          {/* Footer */}
          <footer className="dh-footer">
            <div className="dh-footer-inner">
              <div className="dh-footer-left">
                <div className="dh-footer-item">
                  <span className="dh-footer-dot-cyan"></span>
                  <span>Sub-Space Link Active</span>
                </div>
                <div className="dh-footer-item">
                  <span className="dh-footer-dot-lime"></span>
                  <span>TFLOPS: 12.4 Normal</span>
                </div>
              </div>
              <div className="dh-footer-right">
                <span>Protocol 9.04.1</span>
              </div>
            </div>
          </footer>
        </>
      )}
    </div>
  )
}







// @panel: LaunchBoxPanel
// @role: Game library management and launching interface
// @owner: LoRa
// @linked: backend/routers/launchbox.py
// @features: game-browsing, filtering, statistics, launching

import React, { useCallback, useEffect, useRef, useState, useMemo, memo } from 'react'
import { PanelShell } from '../_kit'
import { API_ENDPOINTS } from '../../constants/a_drive_paths'
import { speakAsLora, stopSpeaking } from '../../services/ttsClient'
import './launchbox.css'
import { useProfileContext } from '../../context/ProfileContext'
import { useBlinkyGameSelection } from '../../hooks/useBlinkyGameSelection'
import LaunchBoxErrorBoundary from './LaunchBoxErrorBoundary'
import useLaunchLock from './hooks/useLaunchLock'
import usePluginHealth from './hooks/usePluginHealth'
import useVoiceRecording from './hooks/useVoiceRecording'
import ShaderPreviewModal from './components/ShaderPreviewModal'
import LoraChatDrawer from './components/LoraChatDrawer'
import { getGatewayUrl } from '../../services/gateway'

// Inline useDebounce hook since it's not available in the hooks folder
function useDebounce(value, delay) {
  const [debouncedValue, setDebouncedValue] = useState(value)
  useEffect(() => {
    const timer = setTimeout(() => setDebouncedValue(value), delay)
    return () => clearTimeout(timer)
  }, [value, delay])
  return debouncedValue
}

const DEVICE_ID_STORAGE_KEY = 'launchbox:device-id'
const LOCAL_LAUNCHBOX_API = '/api/launchbox'
const PROFILE_STORAGE_KEY = 'launchbox:active-profile'
const RETROARCH_ALLOWED_STORAGE_KEY = 'launchbox:allow-retroarch'
// Ensure API calls hit the gateway when running under Vite (5173)
const GATEWAY = (typeof window !== 'undefined' && window.location && window.location.port === '5173')
  ? getGatewayUrl()
  : ''

const formatProfileLabel = (profile) => {
  if (!profile) return 'Guest'
  return profile.charAt(0).toUpperCase() + profile.slice(1)
}

const normalizeTitleForMatch = (str) => {
  return (str || '')
    .toString()
    .trim()
    .toLowerCase()
    .replace(/['’]/g, '')
    .replace(/[^a-z0-9]+/g, ' ')
    .replace(/\s+/g, ' ')
    .trim()
}

const getPlatformIcon = (platform) => {
  const name = (platform || '').toLowerCase()

  if (!name || name === 'all') return '🎮'
  if (name.includes('gun')) return '🔫'
  if (name.includes('laser') || name.includes('daphne') || name.includes('hypseus')) return '💿'
  if (name.includes('atari')) return '🛸'
  if (name.includes('sega') || name.includes('genesis') || name.includes('dreamcast') || name.includes('naomi') || name.includes('master system')) return '🌀'
  if (name.includes('nintendo') || name.includes('famicom') || name.includes('nes') || name.includes('snes') || name.includes('game boy') || name.includes('gba') || name.includes('gbc') || name.includes('n64') || name.includes('gamecube') || name.includes('wii') || name.includes('switch') || name.includes('ds')) return '🍄'
  if (name.includes('playstation') || /^ps\d/.test(name) || name.includes('psp') || name.includes('vita')) return '🎯'
  if (name.includes('xbox')) return '❎'
  if (name.includes('pc') || name.includes('windows') || name.includes('steam') || name.includes('teknoparrot')) return '🖥️'
  if (name.includes('arcade') || name.includes('mame') || name.includes('cps') || name.includes('model 2') || name.includes('model 3')) return '🕹️'

  return '🎮'
}

const generateDeviceId = () => {
  if (typeof crypto !== 'undefined' && typeof crypto.randomUUID === 'function') {
    return `launchbox-${crypto.randomUUID()}`
  }
  return `launchbox-${Math.random().toString(36).slice(2)}`
}

const resolveLaunchboxDeviceId = () => {
  try {
    if (typeof window === 'undefined' || !window.localStorage) {
      return generateDeviceId()
    }
    const existing = window.localStorage.getItem(DEVICE_ID_STORAGE_KEY)
    if (existing) return existing
    const created = generateDeviceId()
    window.localStorage.setItem(DEVICE_ID_STORAGE_KEY, created)
    return created
  } catch {
    return generateDeviceId()
  }
}

const arrayBufferToBase64 = (buffer) => {
  let binary = ''
  const bytes = new Uint8Array(buffer)
  for (let i = 0; i < bytes.byteLength; i += 1) {
    binary += String.fromCharCode(bytes[i])
  }
  if (typeof window !== 'undefined' && typeof window.btoa === 'function') {
    return window.btoa(binary)
  }
  if (typeof Buffer !== 'undefined') {
    return Buffer.from(binary, 'binary').toString('base64')
  }
  throw new Error('Base64 encoding not supported in this environment.')
}

const pickRecorderOptions = () => {
  if (typeof window === 'undefined' || typeof window.MediaRecorder === 'undefined') {
    return undefined
  }
  if (typeof window.MediaRecorder.isTypeSupported !== 'function') {
    return undefined
  }
  // Prefer WAV format for better Whisper API compatibility
  // WebM chunks don't concatenate into valid files for Whisper
  const preferred = ['audio/wav', 'audio/webm;codecs=opus', 'audio/webm', 'audio/ogg;codecs=opus']
  const supported = preferred.find(type => window.MediaRecorder.isTypeSupported(type))
  return supported ? { mimeType: supported } : undefined
}

/**
 * Step 1: Response Normalizer
 * This helper function makes the frontend tolerant to both the old API response (an array)
 * and the new paginated response (an object with a `games` property).
 */
const normalizeApiResponse = (data) => {
  // New API shape: { games: [], total: 0, ... }
  if (data && Array.isArray(data.games)) {
    return {
      games: data.games,
      total: data.total ?? data.games.length,
    }
  }
  // Legacy API shape: [...]
  if (Array.isArray(data)) {
    console.warn('[LaunchBoxPanel] Received legacy array response from /games API. Full client-side filtering is being used.')
    return {
      games: data,
      total: data.length,
    }
  }
  // Fallback for invalid or empty responses
  return { games: [], total: 0 }
}

// Memoized chat message component to prevent unnecessary re-renders
const ChatMessage = memo(({ message, role }) => {
  // Strip markdown formatting (bold, italic, lists) for clean display
  const cleanMessage = message
    .replace(/\*\*([^*]+)\*\*/g, '$1')  // Remove **bold**
    .replace(/\*([^*]+)\*/g, '$1')       // Remove *italic*
    .replace(/^[-•]\s+/gm, '')           // Remove bullet points
    .replace(/^\d+\.\s+/gm, '')          // Remove numbered lists

  return (
    <div className={`chat-message ${role}`}>
      <div className="message-bubble">
        {cleanMessage}
      </div>
    </div>
  )
})

ChatMessage.displayName = 'ChatMessage'

// Memoized game card component to prevent unnecessary re-renders
const GameCard = memo(({ game, onLaunch, onGameHover, formatRelativeTime, pluginAvailable, launchDisabled }) => {
  const isPinball = useMemo(() => (game.platform || '').toLowerCase().includes('pinball'), [game.platform])

  const handleLaunch = useCallback((e) => {
    if (e) {
      e.preventDefault()
      e.stopPropagation()
    }
    onLaunch(game)
  }, [game, onLaunch])

  // Trigger LED selection when hovering over the game card
  const handleMouseEnter = useCallback(() => {
    if (onGameHover) {
      onGameHover(game)
    }
  }, [game, onGameHover])

  // Memoize styles used in the component
  const hiddenStyle = useMemo(() => ({ display: 'none' }), [])

  const handleImageError = useCallback((e) => {
    // Fallback to placeholder if image not found
    e.target.style.display = 'none'
    e.target.nextSibling.style.display = 'flex'
  }, [])

  // Disable launch when cross-tab lock or in-flight
  const isDisabled = !!launchDisabled
  const launchTooltip = `Launch ${game.title}`

  return (
    <div className={`game-card ${isPinball ? 'pinball-card' : ''}`} onMouseEnter={handleMouseEnter}>
      {/* Game Box Art */}
      <div className="game-image-container">
        <img
          src={`${GATEWAY}/api/launchbox/image/${game.id}`}
          alt={game.title}
          className="game-image"
          onError={handleImageError}
        />
        <div className="game-image-placeholder" style={hiddenStyle}>
          <span className="placeholder-icon">🎮</span>
          <span className="placeholder-text">{game.title.substring(0, 1)}</span>
        </div>
      </div>

      <div className="game-info">
        <div className="game-title-row">
          <h3 className="game-title">{game.title}</h3>
          {game.genre && (
            <span className={`genre-badge genre-${game.genre.toLowerCase().replace(/ & /g, '-').replace(/ /g, '-')}`}>
              {game.genre}
            </span>
          )}
          <span className="game-year">{game.year}</span>
        </div>
        <div className="game-meta">
          <span className="meta-item">🎮 {game.platform}</span>
          <span className="meta-item">🕐 {formatRelativeTime(game.lastPlayed)}</span>
          <span className="meta-item">⏱️ {game.sessionTime}</span>
          <span className="meta-item">🔥 {game.playCount} plays</span>
        </div>
      </div>
      <button
        className={`game-play-btn ${isDisabled && !isPinball ? 'disabled' : ''} ${isPinball ? 'always-visible' : ''}`}
        onClick={handleLaunch}
        disabled={isDisabled && !isPinball}
        title={launchTooltip}
        aria-label={launchTooltip}
      >
        ▶
      </button>
    </div>
  )
})

GameCard.displayName = 'GameCard'

function LaunchBoxPanelContent() {
  // Chat sidebar state
  const [chatOpen, setChatOpen] = useState(false)
  const [messages, setMessages] = useState([
    { role: 'assistant', text: 'Hey! I\'m LoRa, your LaunchBox assistant. Ask me anything about your games!' }
  ])
  const addMessage = useCallback((text, role) => {
    setMessages(prev => [...prev, { role, text }])
  }, [])
  const [input, setInput] = useState('')

  // Panel state
  const [activeTab, setActiveTab] = useState('recent')
  const [deviceId] = useState(() => resolveLaunchboxDeviceId())
  const [subPanelExpanded, setSubPanelExpanded] = useState(true)
  const [loraState, setLoraState] = useState('idle') // idle, listening, processing, launching

  // API headers for all fetch calls
  const apiHeaders = useMemo(() => ({
    'x-panel': 'launchbox',
    'x-device-id': deviceId
  }), [deviceId])

  // Toast notification (needs to be before blinkySelection to avoid circular dependency)
  const [toastMsg, setToastMsg] = useState("")
  const showToast = useCallback((msg) => {
    setToastMsg(msg)
    window.clearTimeout(showToast._t)
    showToast._t = window.setTimeout(() => setToastMsg(""), 2000)
  }, [])

  // LED Blinky integration - lights up cabinet when hovering games
  const blinkySelection = useBlinkyGameSelection({ onToast: showToast })
  const { isLockActive, acquireLock, releaseLock } = useLaunchLock({ lockMs: 5000 })
  const { pluginAvailable, checkPluginHealth } = usePluginHealth({ gateway: GATEWAY })

  const [allowRetroArch, setAllowRetroArch] = useState(() => {
    try {
      if (typeof window === 'undefined' || !window.localStorage) return true
      const v = window.localStorage.getItem(RETROARCH_ALLOWED_STORAGE_KEY)
      if (v === null) return true
      return v === 'true'
    } catch {
      return true
    }
  })
  const [directRetroArchEnabled, setDirectRetroArchEnabled] = useState(null)

  // Data state (Old and New for safe refactoring)
  const [games, setGames] = useState([]) // NEW: Holds the current page of games
  const [totalGames, setTotalGames] = useState(0) // NEW: Total games from server
  const [gamesReloadToken, setGamesReloadToken] = useState(0) // NEW: Forces paginated refetch
  const [platforms, setPlatforms] = useState([])
  const [genres, setGenres] = useState([])
  const [stats, setStats] = useState(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState(null)
  const [perfMetrics, setPerfMetrics] = useState({})

  // Filter and pagination state
  const [platformFilter, setPlatformFilter] = useState('All')
  const [genreFilter, setGenreFilter] = useState('All')
  const [yearFilter, setYearFilter] = useState('All')
  const [sortBy, setSortBy] = useState('title')
  const [sortOrder, setSortOrder] = useState('asc')
  const [searchQuery, setSearchQuery] = useState('')
  const [hoveredGame, setHoveredGame] = useState(null)
  const debouncedSearchQuery = useDebounce(searchQuery, 300)
  const [currentPage, setCurrentPage] = useState(1)
  const GAMES_PER_PAGE = 50 // Updated to a more reasonable page size


  // Chat state
  const [isChatLoading, setIsChatLoading] = useState(false)

  // Shader modal state
  const [shaderPreview, setShaderPreview] = useState(null)
  const [shaderModal, setShaderModal] = useState({ open: false, applying: false, error: '', gameId: '', shaderName: '', emulator: '', diff: '', oldConfig: null, newConfig: null })
  const [pendingShaderApply, setPendingShaderApply] = useState(null)

  // Profile state (from context or local)
  const { profile: sharedProfile } = useProfileContext() || {}
  const [activeProfile, setActiveProfile] = useState('guest')
  const profileOptions = useMemo(() => {
    const options = [
      { value: 'guest', label: 'Guest' },
      { value: 'dad', label: 'Dad' },
      { value: 'mom', label: 'Mom' },
      { value: 'tim', label: 'Tim' },
      { value: 'sarah', label: 'Sarah' }
    ]
    const sharedId = sharedProfile?.userId
    const sharedName = sharedProfile?.displayName
    if (sharedId && sharedName && !options.some(opt => opt.value === sharedId)) {
      // Label for dropdown shows source, but displayName is used for AI greeting
      options.unshift({ value: sharedId, label: sharedName, displayName: sharedName, source: 'voice' })
    }
    return options
  }, [sharedProfile])
  const activeProfileDetails = useMemo(() => {
    return profileOptions.find(p => p.value === activeProfile)
  }, [activeProfile, profileOptions])
  const activeProfileLabel = useMemo(() => {
    if (activeProfileDetails?.label) return activeProfileDetails.label
    return activeProfile.charAt(0).toUpperCase() + activeProfile.slice(1)
  }, [activeProfile, activeProfileDetails])
  // Get the actual display name for AI (not the dropdown label which may have suffixes)
  const activeDisplayName = useMemo(() => {
    if (activeProfileDetails?.displayName) return activeProfileDetails.displayName
    return activeProfileLabel
  }, [activeProfileDetails, activeProfileLabel])
  const handleProfileChange = useCallback((e) => {
    profileTouchedRef.current = true
    setActiveProfile(e.target.value)
  }, [])
  const chatProfileId = activeProfile || 'guest'
  // Use clean display name for AI, not the label which may include "(Vicky)" suffix
  const chatProfileName = activeDisplayName || 'Guest'
  const scoreProfileId = sharedProfile?.userId || 'guest'
  const scoreProfileName = sharedProfile?.displayName || 'Guest'


  // Refs




  const chatMessagesRef = useRef(null)
  const searchInputRef = useRef(null)
  const sendMessageWithTextRef = useRef(null)
  const resolveAndLaunchRef = useRef(null)
  const handoffProcessedRef = useRef(null)
  const profileTouchedRef = useRef(false)

  useEffect(() => {
    if (!profileTouchedRef.current && sharedProfile?.userId) {
      setActiveProfile(sharedProfile.userId)
    }
  }, [sharedProfile])

  const handleVoiceCommandTranscript = useCallback((transcript) => {
    const sanitized = (transcript || '').trim()
    if (!sanitized) {
      addMessage("I didn't catch that. Try again.", 'assistant')
      return
    }
    setInput(sanitized)
    sendMessageWithTextRef.current?.(sanitized)
  }, [addMessage])

  const { isRecording, startVoiceRecording, stopVoiceRecording } = useVoiceRecording({
    addMessage,
    showToast,
    onTranscript: handleVoiceCommandTranscript,
    setLoraState
  })

  // Define supported platforms for direct launch in this panel.
  // Keep broad compatibility but reject empty/known unsupported launcher-only categories.
  const isSupportedPlatform = useCallback((platform) => {
    if (!platform || typeof platform !== 'string') return false
    const normalized = platform.trim().toLowerCase()
    if (!normalized) return false

    const unsupportedKeywords = ['flash']
    return !unsupportedKeywords.some(keyword => normalized.includes(keyword))
  }, [])

  const canLaunchHere = useCallback((game) => {
    if (!game || !game.id) return false
    return isSupportedPlatform(game.platform)
  }, [isSupportedPlatform])

  // Cache status (for stale indicator)
  const [cacheStatus, setCacheStatus] = useState(null)
  const STALE_THRESHOLD_SECS = 6 * 3600 // 6 hours

  const fetchCacheStatus = useCallback(async () => {
    try {
      const res = await fetch(GATEWAY + API_ENDPOINTS.CACHE_STATUS, { headers: { 'Cache-Control': 'no-cache' } })
      if (res.ok) {
        const s = await res.json()
        setCacheStatus(s)
      }
    } catch (_) {
      // ignore
    }
  }, [])


  // Check plugin health on mount (non-blocking)
  useEffect(() => {
    checkPluginHealth()
    fetchCacheStatus()

    // Fetch initial metadata
    const fetchMetadata = async () => {
      try {
        const [platformsRes, genresRes, statsRes] = await Promise.all([
          fetch(`${GATEWAY}${API_ENDPOINTS.PLATFORMS}`),
          fetch(`${GATEWAY}${API_ENDPOINTS.GENRES}`),
          fetch(`${GATEWAY}${API_ENDPOINTS.STATS}`)
        ]);
        if (!platformsRes.ok || !genresRes.ok || !statsRes.ok) {
          throw new Error('Failed to load metadata');
        }
        const platformsData = await platformsRes.json();
        const genresData = await genresRes.json();
        const statsData = await statsRes.json();
        setPlatforms(platformsData);
        setGenres(genresData);
        setStats(statsData);
      } catch (err) {
        // Non-critical, the panel can still function
        console.warn("Could not load metadata:", err);
      }
    };
    fetchMetadata();

    const fetchDirectLaunchStatus = async () => {
      try {
        const res = await fetch(`${GATEWAY}${LOCAL_LAUNCHBOX_API}/diagnostics/dry-run`, {
          headers: apiHeaders
        })
        if (!res.ok) return
        const data = await res.json().catch(() => ({}))
        const env = data?.allow_direct_env || {}
        const cfg = data?.allow_direct_config || {}
        const enabled = Boolean(env.AA_ALLOW_DIRECT_RETROARCH || cfg.allow_direct_retroarch)
        setDirectRetroArchEnabled(enabled)
      } catch {
        setDirectRetroArchEnabled(null)
      }
    }

    fetchDirectLaunchStatus()
  }, []); // Only run once on mount

  // NEW: Fetch paginated games from the new backend endpoint
  useEffect(() => {
    const controller = new AbortController();
    const fetchGamesPage = async () => {
      setLoading(true);
      setError(null);

      const allowedSortFields = new Set(['title', 'year', 'platform', 'play_count', 'last_played'])
      const serverSortBy = allowedSortFields.has(sortBy) ? sortBy : 'title'

      let yearMin
      let yearMax
      if (yearFilter !== 'All') {
        const decadeStart = parseInt(yearFilter.substring(0, 4), 10)
        if (Number.isFinite(decadeStart)) {
          yearMin = decadeStart
          yearMax = decadeStart + 9
        }
      }

      const params = new URLSearchParams({
        page: currentPage,
        limit: GAMES_PER_PAGE,
        sort_by: serverSortBy,
        sort_order: sortOrder,
      });

      if (platformFilter && platformFilter !== 'All') {
        params.set('platform', platformFilter);
      }
      if (genreFilter && genreFilter !== 'All') {
        params.set('genre', genreFilter);
      }
      if (typeof yearMin === 'number') {
        params.set('year_min', String(yearMin))
      }
      if (typeof yearMax === 'number') {
        params.set('year_max', String(yearMax))
      }
      if (debouncedSearchQuery) {
        params.set('search', debouncedSearchQuery);
      }

      try {
        const url = `${GATEWAY}${LOCAL_LAUNCHBOX_API}/games?${params.toString()}`;
        const response = await fetch(url, {
          headers: apiHeaders,
          signal: controller.signal,
        });

        if (!response.ok) {
          throw new Error(`API Error: ${response.status} ${response.statusText}`);
        }

        const data = await response.json();
        const normalized = normalizeApiResponse(data);

        setGames(normalized.games);
        setTotalGames(normalized.total);

      } catch (err) {
        if (err.name !== 'AbortError') {
          setError(err.message || 'Unable to load games');
        }
      } finally {
        setLoading(false);
      }
    };

    fetchGamesPage();

    return () => {
      controller.abort();
    };
  }, [
    currentPage,
    debouncedSearchQuery,
    platformFilter,
    genreFilter,
    yearFilter,
    sortBy,
    sortOrder,
    apiHeaders,
    gamesReloadToken,
  ]);


  // Refresh library (POST revalidate) + refetch games
  const refreshLibrary = useCallback(async () => {
    try {
      const res = await fetch(`${GATEWAY}${API_ENDPOINTS.CACHE_REVALIDATE}`, { method: 'POST' })
      const data = await res.json()
      const after = data && (data.after || {})
      const size = after && (after.size || 0)
      showToast(`Library refreshed (${size} items)`) // UX: display count
      // Trigger paginated refetch (avoid loading full library into the browser)
      setCurrentPage(1)
      setGamesReloadToken(prev => prev + 1)
      // Update status for stale badge
      fetchCacheStatus()
    } catch (e) {
      showToast('Refresh failed')
    }
  }, [fetchCacheStatus, showToast])
  // Default stats shown while loading
  const defaultStats = {
    totalGames: 0,
    totalGamesChange: 'Loading...',
    platforms: 0,
    platformsDetail: 'Loading...',
    mostPlayed: 'Loading...',
    mostPlayedSessions: '0 sessions',
    totalPlaytime: '0h',
    totalPlaytimeWeek: '0h this week'
  }

  const displayStats = stats || defaultStats

  // Refs for performance optimization
  const lastLaunchRef = useRef({ title: null, timestamp: 0 })

  // Launch game handler (must be before sendMessage to avoid hoisting error)
  const launchGame = useCallback(async (game) => {
    // Validation guards to prevent errors
    if (!game || !game.id) {
      addMessage('❌ No game selected to launch.', 'assistant')
      return
    }

    if (loading) {
      addMessage('⏳ Library is still loading. Try again in a moment.', 'assistant')
      return
    }

    // Respect panel scope: only allow supported platforms here
    if (!canLaunchHere(game)) {
      addMessage('ℹ️ Heads up: This title isn’t launchable from this panel. Try LaunchBox for this game.', 'assistant')
      showToast('Try LaunchBox for this title')
      return
    }

    // If plugin is offline, continue with backend fallbacks for supported platforms
    if (!pluginAvailable) {
      addMessage('⚠️ Plugin offline. Attempting fallback launch for supported platforms...', 'assistant')
    }

    // Debounce: prevent launching same game within 3 seconds
    const now = Date.now()
    if (lastLaunchRef.current.title === game.title &&
      (now - lastLaunchRef.current.timestamp) < 3000) {
      addMessage(`⏸️ Already launching ${game.title}, please wait...`, 'assistant')
      return
    }

    lastLaunchRef.current = { title: game.title, timestamp: now }

    // Cross-tab lock: acquire before starting
    acquireLock()
    setLoraState('launching')
    addMessage(`Launching ${game.title} for ${scoreProfileName}...`, 'assistant')

    // Fire LED preview + launch events for Blinky (non-blocking)
    ;(async () => {
      try {
        let ledGame = game
        const hasRomHint = Boolean(
          game?.rom ||
          game?.rom_path ||
          game?.romPath ||
          game?.application_path ||
          game?.applicationPath
        )

        // AI resolve payloads can be title/id-only; hydrate full game record for LED ROM mapping.
        if (!hasRomHint && game?.id) {
          try {
            const detailRes = await fetch(`${GATEWAY}${API_ENDPOINTS.GAMES}/${game.id}`, {
              headers: apiHeaders
            })
            if (detailRes.ok) {
              const detail = await detailRes.json().catch(() => null)
              if (detail && typeof detail === 'object') {
                ledGame = { ...detail, ...game }
              }
            }
          } catch (detailErr) {
            console.warn('[LaunchBox] Could not hydrate LED game payload:', detailErr)
          }
        }

        await blinkySelection.gameLaunch(ledGame, game.platform || 'MAME')
      } catch (ledErr) {
        console.warn('[LaunchBox] LED launch hook failed (non-blocking):', ledErr?.message || ledErr)
      }
    })()

    // === NON-BLOCKING VOICE ANNOUNCEMENT ===
    // Fire-and-forget: TTS must never block game launch
    // If voice engine hangs or fails, game still launches
    if (typeof speakAsLora === 'function') {
      try {
        // Do NOT await - fire and forget immediately
        Promise.resolve(speakAsLora(`Loading ${game.title}`)).catch(voiceErr => {
          console.warn('[LaunchBox] TTS announcement failed (non-blocking):', voiceErr?.message || voiceErr)
        })
      } catch (voiceSyncErr) {
        // Synchronous error in speakAsLora call itself - log and continue
        console.warn('[LaunchBox] TTS call failed (sync):', voiceSyncErr?.message || voiceSyncErr)
      }
    }

    try {
      const response = await fetch(`${GATEWAY}${API_ENDPOINTS.LAUNCH}/${game.id}`, {
        method: 'POST',
        headers: {
          ...apiHeaders,
          'Content-Type': 'application/json',
          'x-panel': 'launchbox',
          'x-corr-id': `${Date.now()}-${Math.random().toString(36).slice(2)}`,
          // Player/session tracking for ScoreKeeper Sam
          // Use Vicky's shared profile for score attribution
          'x-user-profile': scoreProfileId,
          'x-user-name': scoreProfileName,
          'x-session-owner': scoreProfileId
        }
      })

      const result = await response.json()

      if (result.success) {
        addMessage(`✅ ${game.title} launched via ${result.method_used}`, 'assistant')
        showToast(`Launched via: ${result.method_used}`)
      } else {
        // Backend returns 'message' field, not 'error' field - check message first
        const errorMsg = result.message || result.error || 'Unknown error occurred'
        addMessage(`❌ Failed to launch ${game.title}: ${errorMsg}`, 'assistant')
        showToast('Launch failed')
      }
    } catch (err) {
      console.error('Launch failed:', err)
      // Provide more detailed error information with proper fallbacks
      const errorDetail = err.message || err.toString() || 'Network error'
      addMessage(`❌ Launch error: ${errorDetail}`, 'assistant')
      showToast('Launch error')
    } finally {
      setLoraState('idle')
      releaseLock()  // Release cross-tab lock after launch completes/fails
    }
  }, [addMessage, loading, pluginAvailable, canLaunchHere, showToast, acquireLock, releaseLock, apiHeaders, blinkySelection, scoreProfileName, scoreProfileId])

  // --- Shader Preview Helpers ---
  const openShaderPreview = useCallback((preview) => {
    const gameId = preview?.gameId || preview?.game_id || ''
    const shaderName = preview?.shaderName || preview?.shader_name || ''
    const emulator = preview?.emulator || ''
    const oldConfig = preview?.old || null
    const newConfig = preview?.new || null
    setShaderPreview({
      diff: preview?.diff || '',
      oldText: JSON.stringify(oldConfig || { shader: 'none' }, null, 2),
      newText: JSON.stringify(newConfig || {}, null, 2),
      gameId,
      shaderName,
      emulator
    })
    setPendingShaderApply({ game_id: gameId, shader_name: shaderName, emulator })
    setShaderModal(prev => ({ ...prev, open: true, gameId, shaderName, emulator, diff: preview?.diff || '', oldConfig, newConfig }))
    setChatOpen(true)
  }, [])

  const closeShaderPreview = useCallback(() => {
    setShaderModal(prev => ({ ...prev, open: false, applying: false, error: '' }))
  }, [])

  const applyShaderChange = useCallback(async () => {
    const applyReq = pendingShaderApply || { game_id: shaderModal.gameId, shader_name: shaderModal.shaderName, emulator: shaderModal.emulator }
    const { game_id, shader_name, emulator } = applyReq
    if (!game_id || !shader_name || !emulator) return
    try {
      setShaderModal(prev => ({ ...prev, applying: true, error: '' }))
      const resp = await fetch('/api/launchbox/shaders/apply', {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
          'x-scope': 'config',
          'x-device-id': deviceId,
          'x-panel': 'launchbox'
        },
        body: JSON.stringify({ game_id, shader_name, emulator })
      })
      const result = await resp.json().catch(() => ({}))
      if (result?.success) {
        addMessage(` Shader applied successfully! Backup saved at ${result?.backup_path || 'none'}`, 'assistant')
        showToast('Shader applied')
        closeShaderPreview()
      } else {
        const msg = result?.error || 'Failed to apply shader'
        addMessage(` Failed to apply shader: ${msg}`, 'assistant')
        setShaderModal(prev => ({ ...prev, applying: false, error: msg }))
        showToast('Shader apply failed')
      }
    } catch (e) {
      setShaderModal(prev => ({ ...prev, applying: false, error: e?.message || String(e) }))
      showToast('Shader apply error')
    }
    finally {
      setShaderPreview(null)
      setPendingShaderApply(null)
    }
  }, [pendingShaderApply, shaderModal, deviceId, addMessage, showToast, closeShaderPreview])

  const removeShaderBinding = useCallback(async () => {
    const { gameId, emulator } = shaderModal
    if (!gameId) return
    try {
      setShaderModal(prev => ({ ...prev, applying: true, error: '' }))
      const qs = emulator ? `?emulator=${encodeURIComponent(emulator)}` : ''
      const resp = await fetch(`/api/launchbox/shaders/game/${encodeURIComponent(gameId)}${qs}`, {
        method: 'DELETE',
        headers: {
          'x-scope': 'config',
          'x-device-id': deviceId,
          'x-panel': 'launchbox'
        }
      })
      const result = await resp.json().catch(() => ({}))
      if (result?.success) {
        const count = Number(result?.removed_count || 1)
        addMessage(`Removed ${count} shader binding(s) for ${gameId}`, 'assistant')
        showToast('Shader removed')
        closeShaderPreview()
      } else {
        const msg = result?.error || 'Failed to remove shader'
        setShaderModal(prev => ({ ...prev, applying: false, error: msg }))
        showToast('Shader remove failed')
      }
    } catch (e) {
      setShaderModal(prev => ({ ...prev, applying: false, error: e?.message || String(e) }))
      showToast('Shader remove error')
    }
  }, [shaderModal, deviceId, addMessage, showToast, closeShaderPreview])

  const maybeHandleShaderToolCalls = useCallback((toolCalls, aiText = '') => {
    try {
      const arr = Array.isArray(toolCalls) ? toolCalls : []
      for (const tc of arr) {
        if (!tc || tc.name !== 'manage_shader') continue
        const action = tc.input?.action
        if (action === 'preview') {
          openShaderPreview({
            gameId: tc.input?.game_id,
            shaderName: tc.input?.shader_name,
            // Prefer emulator returned by the tool (may switch mame<->retroarch)
            emulator: (tc.result && tc.result.emulator) || tc.input?.emulator,
            diff: tc.result?.diff,
            old: tc.result?.old,
            new: tc.result?.new
          })
          break
        }
        if (action === 'apply') {
          const ok = Boolean(tc.result?.success)
          const backup = tc.result?.backup_path || 'none'
          if (ok) {
            addMessage(` Shader applied successfully! Backup saved at ${backup}`, 'assistant')
            showToast('Shader applied')
            setShaderPreview(null)
            setPendingShaderApply(null)
            closeShaderPreview()
          } else {
            const msg = tc.result?.error || 'unknown error'
            addMessage(` Failed to apply shader: ${msg}`, 'assistant')
            showToast('Shader apply failed')
          }
        }
        if (action === 'remove') {
          const count = Number(tc.result?.removed_count || 0)
          if (count > 0) showToast(`Removed ${count} shader binding(s)`)
        }
      }
      // Fallback detection if AI text mentions preview
      if (typeof aiText === 'string' && (aiText.includes('preview_ready') || aiText.toLowerCase().includes('shader preview'))) {
        // Best-effort: open empty modal to prompt user
        setShaderModal(prev => ({ ...prev, open: true }))
      }
    } catch (e) {
      console.warn('[LaunchBox UI] manage_shader handling error:', e)
    }
  }, [openShaderPreview, showToast])

  // Resolve game title via plugin, then launch
  const resolveAndLaunch = useCallback(async (title, filters = {}) => {
    const trimmedTitle = (title || '').trim()
    if (!trimmedTitle) {
      addMessage('Heads up: provide a game title to resolve.', 'assistant')
      return
    }

    setLoraState('processing')
    addMessage(`Searching for "${trimmedTitle}"...`, 'assistant')

    try {
      const response = await fetch(`${GATEWAY}${API_ENDPOINTS.RESOLVE}`, {
        method: 'POST',
        headers: {
          ...apiHeaders,
          'Content-Type': 'application/json'
        },
        body: JSON.stringify({
          title: trimmedTitle,
          platform: filters.platform || undefined,
          year: filters.year || undefined,
          limit: 5
        })
      })

      const payload = await response.json().catch(() => ({}))
      if (!response.ok) {
        throw new Error(payload?.message || 'Failed to resolve game')
      }

      const normalizeCandidates = (result) => {
        if (Array.isArray(result)) return result
        if (result?.status === 'resolved' && result.game) return [result.game]
        if (result?.status === 'multiple_matches' && Array.isArray(result.suggestions)) return result.suggestions
        return []
      }

      if (Array.isArray(payload)) {
        if (payload.length === 0) {
          addMessage(`Heads up: no games found matching "${trimmedTitle}"`, 'assistant')
          return
        }

        if (payload.length === 1) {
          const only = payload[0]
          const exact = normalizeTitleForMatch(trimmedTitle) === normalizeTitleForMatch(only?.title)
          if (exact) {
            addMessage(`Found: ${only.title}. Launching...`, 'assistant')
            await launchGame(only)
            return
          }
        }

        const preview = payload.slice(0, 4).map((g, i) => `${i + 1}) ${g.title} (${g.platform || 'Unknown'})`).join(', ')
        addMessage(`Heads up: I found multiple possible matches for "${trimmedTitle}". Please specify platform/year. Top matches: ${preview}`, 'assistant')
        return
      }

      if (payload.status === 'resolved' && payload.game) {
        const isExact = payload.source === 'cache_exact' ||
          normalizeTitleForMatch(trimmedTitle) === normalizeTitleForMatch(payload.game.title)

        const sourceLabel = payload.source === 'cache_fuzzy' ? 'Fuzzy match' : 'Found'
        const confidenceSuffix = payload.game.confidence ? ` (${Math.round(payload.game.confidence * 100)}% confidence)` : ''

        if (!isExact) {
          addMessage(`Heads up: ${sourceLabel}: ${payload.game.title}${confidenceSuffix}. Please confirm by adding platform/year so I do not launch the wrong game.`, 'assistant')
          return
        }

        addMessage(`${sourceLabel}: ${payload.game.title}${confidenceSuffix}. Launching...`, 'assistant')
        await launchGame(payload.game)
        return
      }

      if (payload.status === 'multiple_matches') {
        const suggestions = Array.isArray(payload.suggestions) ? payload.suggestions : []
        if (suggestions.length === 0) {
          addMessage('Heads up: multiple matches returned but none could be displayed.', 'assistant')
          return
        }

        const listPreview = suggestions.slice(0, 4).map((g, i) => `${i + 1}) ${g.title} (${g.platform || 'Unknown'})`).join(', ')
        addMessage(`Heads up: I found ${suggestions.length} matches for "${trimmedTitle}". Please specify platform/year so I do not launch the wrong one. Top matches: ${listPreview}`, 'assistant')
        return
      }

      if (payload.status === 'not_found') {
        addMessage(payload.message || `Heads up: no games found matching "${trimmedTitle}"`, 'assistant')
        return
      }

      const fallbackMatches = normalizeCandidates(payload)
      if (fallbackMatches.length) {
        if (fallbackMatches.length === 1) {
          const only = fallbackMatches[0]
          const exact = normalizeTitleForMatch(trimmedTitle) === normalizeTitleForMatch(only?.title)
          if (exact) {
            addMessage(`Found: ${only.title}. Launching...`, 'assistant')
            await launchGame(only)
            return
          }
        }

        const preview = fallbackMatches.slice(0, 4).map((g, i) => `${i + 1}) ${g.title} (${g.platform || 'Unknown'})`).join(', ')
        addMessage(`Heads up: I found multiple possible matches for "${trimmedTitle}". Please specify platform/year. Top matches: ${preview}`, 'assistant')
        return
      }

      addMessage(`Heads up: no games found matching "${trimmedTitle}"`, 'assistant')
    } catch (err) {
      console.error('Resolve failed:', err)
      const errorDetail = err?.message || 'Network error'
      addMessage(`Heads up: resolution error - ${errorDetail}`, 'assistant')
    } finally {
      setLoraState('idle')
    }
  }, [addMessage, launchGame, apiHeaders])

  // Assign to ref so voice callbacks can use it
  resolveAndLaunchRef.current = resolveAndLaunch

  // Voice recording toggle
  const toggleMic = useCallback(() => {
    if (isRecording) {
      stopVoiceRecording()
    } else {
      // CRITICAL: Stop any TTS audio immediately to prevent echo
      stopSpeaking()
      startVoiceRecording()
    }
  }, [isRecording, startVoiceRecording, stopVoiceRecording])

  // Memoized toggle handlers to prevent re-renders
  const toggleChat = useCallback(() => {
    setChatOpen(prev => !prev)
  }, [])

  const toggleSubPanel = useCallback(() => {
    setSubPanelExpanded(prev => !prev)
  }, [])

  const closeChat = useCallback(() => {
    setChatOpen(false)
  }, [])

  const closeSubPanel = useCallback(() => {
    setSubPanelExpanded(false)
  }, [])

  const setTabRecent = useCallback(() => {
    setActiveTab('recent')
  }, [])

  const setTabStats = useCallback(() => {
    setActiveTab('stats')
  }, [])

  // Pagination handlers - memoized to prevent recreation on each render
  const goToPreviousPage = useCallback(() => {
    setCurrentPage(prev => Math.max(1, prev - 1))
  }, [])

  const goToNextPage = useCallback((maxPages) => {
    setCurrentPage(prev => Math.min(maxPages, prev + 1))
  }, [])

  // Reload handler for error state
  const handleReload = useCallback(() => {
    window.location.reload()
  }, [])

  // Memoized retry plugin check handler
  const retryPluginCheck = useCallback(() => {
    checkPluginHealth(true) // Force check, bypass cache
  }, [checkPluginHealth])

  // Memoized filter and input handlers to prevent re-renders
  const handleSearchQueryChange = useCallback((e) => {
    setSearchQuery(e.target.value)
  }, [])

  const handlePlatformFilterChange = useCallback((e) => {
    setPlatformFilter(e.target.value)
  }, [])

  const handleGenreFilterChange = useCallback((e) => {
    setGenreFilter(e.target.value)
  }, [])

  const handleYearFilterChange = useCallback((e) => {
    setYearFilter(e.target.value)
  }, [])

  const handleSortByChange = useCallback((e) => {
    const nextSort = e.target.value
    setSortBy(nextSort)

    if (nextSort === 'year' || nextSort === 'play_count' || nextSort === 'last_played') {
      setSortOrder('desc')
    } else {
      setSortOrder('asc')
    }
  }, [])

  const handleInputChange = useCallback((e) => {
    setInput(e.target.value)
  }, [])

  // Get unique platforms, genres, and decades for filters - memoized to avoid recreating arrays
  const platformsForFilter = useMemo(() => ['All', ...(platforms || [])], [platforms])
  const genresForFilter = useMemo(() => ['All', ...(genres || [])], [genres])
  const decades = useMemo(() => ['All', '1970s', '1980s', '1990s', '2000s', '2010s', '2020s'], [])

  // Memoize voice bars array to avoid recreation on each render
  const voiceBars = useMemo(() => [...Array(8)], [])

  // Memoized styles to prevent recreation on each render
  const memoizedStyles = useMemo(() => ({
    hiddenDisplay: { display: 'none' },
    stopIcon: { fontSize: '20px' },
    micIcon: { width: '28px', height: '28px' },
    voiceBarDelays: Array.from({ length: 8 }, (_, i) => ({ animationDelay: `${i * 0.1}s` }))
  }), [])

  // Games visible on the current server page
  const visibleGames = useMemo(() => games || [], [games])

  const totalPages = Math.max(1, Math.ceil((totalGames || 0) / GAMES_PER_PAGE))

  // Reset to page 1 when filters change
  useEffect(() => {
    setCurrentPage(1)
  }, [platformFilter, genreFilter, yearFilter, sortBy, sortOrder, debouncedSearchQuery])

  // Ctrl+F keyboard shortcut to focus search
  useEffect(() => {
    const handleKeyDown = (e) => {
      if ((e.ctrlKey || e.metaKey) && e.key === 'f') {
        e.preventDefault()
        // Expand panel if collapsed
        if (!subPanelExpanded) {
          setSubPanelExpanded(true)
        }
        // Focus search after a tick to ensure panel is visible
        setTimeout(() => {
          searchInputRef.current?.focus()
        }, 50)
      }
    }
    window.addEventListener('keydown', handleKeyDown)
    return () => window.removeEventListener('keydown', handleKeyDown)
  }, [subPanelExpanded])

  // Random game selector
  const selectRandomGame = useCallback(async () => {
    const platformScope = platformFilter || 'All'

    try {
      const params = new URLSearchParams()
      if (platformScope !== 'All') {
        params.set('platform', platformScope)
      }

      const url = `${GATEWAY}${LOCAL_LAUNCHBOX_API}/random${params.toString() ? `?${params.toString()}` : ''}`
      const response = await fetch(url, { headers: apiHeaders })
      if (!response.ok) {
        throw new Error(`API Error: ${response.status} ${response.statusText}`)
      }

      const randomGame = await response.json()
      if (!randomGame || !randomGame.id) {
        throw new Error('No random game returned')
      }

      addMessage(`🎲 Random selection for ${scoreProfileName}: ${randomGame.title} (${randomGame.year || 'Unknown'})`, 'assistant')
      setLoraState('launching')
      setTimeout(() => {
        launchGame(randomGame)
      }, 1000)
      return
    } catch (err) {
      // Fallback: pick from currently loaded page
      const candidates = visibleGames.length > 0 ? visibleGames : games
      if (!candidates || candidates.length === 0) {
        addMessage('❌ No games available for random selection.', 'assistant')
        return
      }
      const fallback = candidates[Math.floor(Math.random() * candidates.length)]
      if (!fallback) {
        addMessage('❌ Failed to select a random game. Please try again.', 'assistant')
        return
      }
      addMessage(`🎲 Random selection for ${scoreProfileName}: ${fallback.title} (${fallback.year || 'Unknown'})`, 'assistant')
      setLoraState('launching')
      setTimeout(() => {
        launchGame(fallback)
      }, 1000)
    }
  }, [platformFilter, visibleGames, games, apiHeaders, addMessage, launchGame, scoreProfileName])

  // Launch LaunchBox app (fire-and-forget for instant UI response)
  const launchLaunchBoxApp = useCallback(() => {
    // Immediate UI feedback - don't wait for API
    addMessage('Launching LaunchBox...', 'assistant')

    // Fire-and-forget: launch in background, don't block UI
    fetch(`${GATEWAY}/api/launchbox/frontend/launchbox/launch`, {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
        'x-device-id': deviceId,
        'x-panel': 'launchbox'
      }
    }).then(response => {
      if (!response.ok) {
        response.json().catch(() => ({})).then(data => {
          addMessage(`Failed to launch LaunchBox: ${data.message || 'Unknown error'}`, 'assistant')
        })
      }
      // Success case: LaunchBox is launching, no need for confirmation message
      // (it takes over the screen anyway)
    }).catch(err => {
      addMessage(`Failed to launch LaunchBox: ${err.message}`, 'assistant')
    })
  }, [addMessage, deviceId])

  const sendChatMessage = useCallback(async (messageText, options = {}) => {
    const text = (messageText || '').trim()
    if (!text) return

    const speakResponse = Boolean(options.speakResponse)
    const source = options.source || 'LaunchBox'

    try { stopSpeaking() } catch { }

    addMessage(text, 'user')
    setLoraState('processing')
    setIsChatLoading(true)

    try {
      const profileId = chatProfileId
      const profileName = chatProfileName

      const response = await fetch(`${GATEWAY}/api/launchbox/chat`, {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
          'x-device-id': deviceId,
          'x-panel': 'launchbox',
          'x-user-profile': profileId,
          'x-user-name': profileName
        },
        body: JSON.stringify({
          message: text,
          profile: {
            id: profileId,
            name: profileName,
            source
          },
          context: {
            currentFilters: {
              genre: genreFilter,
              platform: platformFilter,
              decade: yearFilter,
              sortBy,
              search: searchQuery
            },
            availableGames: totalGames,
            totalGames,
            stats,
            directLaunch: {
              allowRetroArch,
              directRetroArchEnabled
            }
          }
        })
      })

      if (!response.ok) {
        throw new Error(`AI chat failed: ${response.status}`)
      }

      const result = await response.json()

      if (result.success && result.response) {
        addMessage(result.response, 'assistant')

        if (speakResponse) {
          speakAsLora(result.response).catch(err => {
            console.warn('[LaunchBox TTS] Failed to speak response:', err)
          })
        }

        if (result.game_launched) {
          setLoraState('launching')
          setTimeout(() => setLoraState('idle'), 2000)
        }

        maybeHandleShaderToolCalls(result.tool_calls_made, result.response)
      } else {
        const errorMsg = 'Sorry, I had trouble processing that request.'
        addMessage(errorMsg, 'assistant')
        if (speakResponse) {
          speakAsLora(errorMsg).catch(err => {
            console.warn('[LaunchBox TTS] Failed to speak error:', err)
          })
        }
      }
    } catch (error) {
      console.error('[LaunchBox AI] Error:', error)
      const errorMsg = `Sorry, I encountered an error: ${error.message}`
      addMessage(errorMsg, 'assistant')
      if (speakResponse) {
        speakAsLora(errorMsg).catch(err => {
          console.warn('[LaunchBox TTS] Failed to speak error:', err)
        })
      }
    } finally {
      setLoraState('idle')
      setIsChatLoading(false)
    }
  }, [
    addMessage,
    allowRetroArch,
    chatProfileId,
    chatProfileName,
    deviceId,
    directRetroArchEnabled,
    genreFilter,
    maybeHandleShaderToolCalls,
    platformFilter,
    searchQuery,
    sortBy,
    stats,
    totalGames,
    yearFilter
  ])

  // AI chat message handler
  const sendMessage = useCallback(async () => {
    const text = input.trim()
    if (!text) return

    setInput('')
    await sendChatMessage(text, {
      speakResponse: false,
      source: activeProfileDetails?.description || 'LaunchBox'
    })
  }, [input, sendChatMessage, activeProfileDetails])

  // Helper function to send message with custom text (for voice transcription)
  const sendMessageWithText = useCallback(async (text) => {
    const messageText = (text || '').trim()
    if (!messageText) return

    setInput('')
    await sendChatMessage(messageText, {
      speakResponse: true,
      source: 'LaunchBox'
    })
  }, [sendChatMessage])

  // Assign to ref so it can be called from voice callbacks
  useEffect(() => {
    sendMessageWithTextRef.current = sendMessageWithText
  }, [sendMessageWithText])

  // Stop any ongoing TTS when this panel unmounts
  useEffect(() => () => { try { stopSpeaking() } catch { } }, [])

  // Handoff effect (handles Dewey → LaunchBox context handoff)
  useEffect(() => {
    const urlParams = new URLSearchParams(window.location.search)
    const handoffContext = urlParams.get('context')
    const hasHandoff = Boolean((handoffContext || '').trim())
    const noHandoff = urlParams.has('nohandoff')
    const shouldHandoff = hasHandoff && !noHandoff

    if (handoffContext && handoffContext !== handoffProcessedRef.current) {
      const welcomeMsg = `Hi! Dewey told me: "${handoffContext}"\n\nI'm LoRa, your LaunchBox librarian. I can help you find games, launch titles, and manage your library. What would you like to play?`
      handoffProcessedRef.current = handoffContext

      addMessage(welcomeMsg, 'assistant')
      setChatOpen(true)
      speakAsLora(welcomeMsg).catch(err => {
        console.warn('[LaunchBox] URL handoff TTS failed:', err)
      })
    }

    // Check for JSON handoff from Dewey (only when arriving via Dewey URL context)
    if (shouldHandoff) (async () => {
      try {
        const response = await fetch('/api/local/dewey/handoff/launchbox', {
          method: 'GET',
          headers: {
            'Content-Type': 'application/json',
            'x-device-id': window?.AA_DEVICE_ID ?? 'cabinet-001',
            'x-panel': 'launchbox',
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
            const welcomeMsg = `Dewey briefed me: "${summaryText}". I'm LoRa, ready to help you find the perfect game!`

            addMessage(welcomeMsg, 'assistant')
            setChatOpen(true)
            speakAsLora(welcomeMsg).catch(err => {
              console.warn('[LaunchBox] JSON handoff TTS failed:', err)
            })
          }
        }
      } catch (err) {
        console.warn('[LaunchBox] Handoff fetch failed:', err)
      }
    })()
  }, [addMessage])

  // Memoized keypress handler for input fields (must be after sendMessage)
  const handleInputKeyPress = useCallback((e) => {
    if (e.key === 'Enter') {
      sendMessage()
    }
  }, [sendMessage])

  // Format relative time - memoized to avoid recalculating for every game
  const formatRelativeTime = useCallback((date) => {
    // Handle undefined or invalid dates
    if (!date) return 'Never played'

    // Convert to Date object if it's a string
    const dateObj = date instanceof Date ? date : new Date(date)

    // Check if date is valid
    if (isNaN(dateObj.getTime())) return 'Invalid date'

    const now = Date.now()
    const diff = now - dateObj.getTime()
    const hours = Math.floor(diff / (1000 * 60 * 60))
    const days = Math.floor(diff / (1000 * 60 * 60 * 24))

    if (hours < 1) return 'Just now'
    if (hours < 24) return `${hours}h ago`
    return `${days} day${days > 1 ? 's' : ''} ago`
  }, [])

  // Auto-scroll chat to bottom
  useEffect(() => {
    if (chatMessagesRef.current) {
      chatMessagesRef.current.scrollTop = chatMessagesRef.current.scrollHeight
    }
  }, [messages])

  // Status badge text - memoized to avoid recreating objects
  const statusText = useMemo(() => ({
    idle: 'Ready',
    listening: 'Listening...',
    processing: 'Thinking...',
    launching: 'Launching'
  }[loraState]), [loraState])

  const statusColor = useMemo(() => ({
    idle: 'status-ready',
    listening: 'status-listening',
    processing: 'status-processing',
    launching: 'status-launching'
  }[loraState]), [loraState])

  // Show loading state only on initial load (not when refetching for search/filter)
  if (loading && games.length === 0) {
    return (
      <PanelShell
        title="LaunchBox LoRa"
        subtitle="Loading game library..."
        icon={<img src="/lora-avatar.jpeg" alt="LoRa" className="panel-avatar" />}
        status="degraded"
      >
        <div className="loading-container">
          <p className="loading-title">Loading games from backend...</p>
          <p className="loading-subtitle">This may take a few seconds if parsing XML files...</p>
        </div>
      </PanelShell>
    )
  }

  // Show error state
  if (error) {
    // Determine if this is a network error (backend not running) vs data error
    const isBackendStarting = error.includes('backend is starting') || error.includes('Failed to fetch') || error.includes('NetworkError')
    const isLaunchBoxMissing = error.includes('LaunchBox') || error.includes('503') || error.includes('not configured')

    return (
      <PanelShell
        title="LaunchBox LoRa"
        subtitle={isBackendStarting ? "Connecting..." : "Connection Error"}
        icon={<img src="/lora-avatar.jpeg" alt="LoRa" className="panel-avatar" />}
        status="offline"
      >
        <div className="error-container">
          {isBackendStarting ? (
            <>
              <p className="error-message">⏳ Arcade Assistant is starting up...</p>
              <p className="error-detail">The backend is still loading. This usually takes 10-30 seconds on startup.</p>
              <p className="error-detail" style={{ marginTop: '8px', fontSize: '14px', opacity: 0.8 }}>
                If this persists, make sure the Arcade Assistant launcher is running.
              </p>
            </>
          ) : isLaunchBoxMissing ? (
            <>
              <p className="error-message">📂 LaunchBox Not Found</p>
              <p className="error-detail">{error}</p>
              <p className="error-detail" style={{ marginTop: '8px', fontSize: '14px', opacity: 0.8 }}>
                LoRa needs LaunchBox to browse your game library. Other panels will still work.
              </p>
            </>
          ) : (
            <>
              <p className="error-message">❌ Failed to load game library</p>
              <p className="error-detail">{error}</p>
            </>
          )}

          <button
            onClick={handleReload}
            className="error-retry-btn"
          >
            🔄 Retry
          </button>
        </div>
      </PanelShell>
    )
  }

  return (
    <PanelShell
      title="LaunchBox LoRa"
      subtitle="Game Library AI Assistant"
      icon={<img src="/lora-avatar.jpeg" alt="LoRa" className="panel-avatar" />}
      status="online"
      headerActions={
        <div className="lora-header-actions">
          {/* Status Badge */}
          <div className={`lora-status-badge ${statusColor}`}>
            <div className="status-dot" />
            <span>{statusText}</span>
          </div>

          <div
            className="lora-profile-select"
            style={{ display: 'flex', flexDirection: 'column', gap: '4px', alignItems: 'flex-start', minWidth: '170px' }}
          >
            <span style={{ fontSize: '11px', textTransform: 'uppercase', letterSpacing: '0.08em', color: '#93c5fd' }}>
              RetroArch
            </span>
            <label style={{ display: 'flex', gap: '8px', alignItems: 'center', fontSize: '13px', color: '#ffffff' }}>
              <input
                type="checkbox"
                checked={allowRetroArch}
                onChange={(e) => {
                  const next = Boolean(e.target.checked)
                  setAllowRetroArch(next)
                  try {
                    window.localStorage.setItem(RETROARCH_ALLOWED_STORAGE_KEY, String(next))
                  } catch { }
                }}
              />
              Allow fallback
            </label>
            <span style={{ fontSize: '11px', color: '#9ca3af' }}>
              {directRetroArchEnabled === true ? 'Direct launch enabled' : directRetroArchEnabled === false ? 'Direct launch disabled' : 'Direct launch unknown'}
            </span>
          </div>

          {/* Profile Selector */}
          <div
            className="lora-profile-select"
            style={{ display: 'flex', flexDirection: 'column', gap: '4px', alignItems: 'flex-start', minWidth: '140px' }}
          >
            <span style={{ fontSize: '11px', textTransform: 'uppercase', letterSpacing: '0.08em', color: '#93c5fd' }}>
              Chat Profile
            </span>
            <select
              value={activeProfile}
              onChange={handleProfileChange}
              className="input"
              style={{
                padding: '6px 10px',
                background: '#0a0a0a',
                border: '1px solid rgba(200, 255, 0, 0.3)',
                borderRadius: '6px',
                color: '#ffffff',
                fontSize: '13px',
                cursor: 'pointer'
              }}
              aria-label="Select chat profile for LaunchBox"
            >
              {profileOptions.map(option => (
                <option key={option.value} value={option.value}>
                  {option.label}
                </option>
              ))}
            </select>
            {activeProfileDetails?.description && (
              <span style={{ fontSize: '11px', color: '#9ca3af' }}>
                {activeProfileDetails.description}
              </span>
            )}
          </div>

          {/* Random Game Button */}
          <button
            onClick={selectRandomGame}
            className="lora-random-btn"
            aria-label="Select random game"
            title="Launch random game"
          >
            <span className="random-icon">🎲</span>
          </button>

          {/* LaunchBox Shortcut Button */}
          <button
            onClick={launchLaunchBoxApp}
            className="lora-launchbox-btn"
            aria-label="Launch LaunchBox frontend"
            title="Switch to LaunchBox"
          >
            <span className="launchbox-btn-placeholder" aria-hidden="true">LB</span>
          </button>

          {/* Chat Button */}
          <button
            onClick={toggleChat}
            className="lora-chat-btn"
            aria-label="Toggle chat with LoRa"
          >
            <span className="chat-icon">💬</span>
            {!chatOpen && <span className="chat-notification">!</span>}
          </button>

          {/* Mic Button */}
          <button
            onClick={toggleMic}
            className={`lora-mic-btn ${isRecording ? 'recording' : ''}`}
            aria-label={isRecording ? 'Stop recording' : 'Start voice input'}
          >
            <img
              src="/lora-microphone.png"
              alt="Microphone"
              className="mic-icon"
            />
          </button>
        </div>
      }
    >
      <ShaderPreviewModal
        isOpen={shaderModal.open}
        shaderModal={shaderModal}
        shaderPreview={shaderPreview}
        onCancel={() => {
          addMessage('Shader change cancelled.', 'assistant')
          setShaderPreview(null)
          setPendingShaderApply(null)
          closeShaderPreview()
        }}
        onApply={applyShaderChange}
      />
      {/* Animated Background Grid */}
      <div className="lora-bg-grid" />

      {/* Plugin offline banner intentionally omitted: Launches do not depend on plugin availability */}

      {/* Main Content Area — Sidebar + Main */}
      <div className="lora-content">
        {/* Platform Sidebar */}
        <nav className="lora-sidebar">
          <div className="sidebar-header">
            <span className="sidebar-title">Library</span>
          </div>
          <ul className="sidebar-nav">
            <li>
              <button
                className={`sidebar-item ${platformFilter === 'All' ? 'active' : ''}`}
                onClick={() => { setPlatformFilter('All'); setCurrentPage(1) }}
              >
                <span className="sidebar-icon" aria-hidden="true">{getPlatformIcon('All')}</span>
                <span className="sidebar-label">All Games</span>
                <span className="sidebar-count">{totalGames}</span>
              </button>
            </li>
            {platforms.map(p => (
              <li key={p}>
                <button
                  className={`sidebar-item ${platformFilter === p ? 'active' : ''}`}
                  onClick={() => { setPlatformFilter(p); setCurrentPage(1) }}
                >
                  <span className="sidebar-icon" aria-hidden="true">{getPlatformIcon(p)}</span>
                  <span className="sidebar-label">{p}</span>
                </button>
              </li>
            ))}
          </ul>
          <div className="sidebar-footer">
            <div className="sidebar-status">
              <span className={`sidebar-dot ${pluginAvailable ? 'online' : 'offline'}`} />
              <span>{pluginAvailable ? '1/1 Board Connected' : 'No Board'}</span>
            </div>
          </div>
        </nav>

        {/* Main Panel */}
        <div className="lora-main">
          {/* Hero Section — Dynamic Preview */}
          {games.length > 0 && (() => {
            const featured = hoveredGame || games[0];
            return (
              <div className={`lora-hero ${hoveredGame ? 'hero-previewing' : ''}`}
                onClick={() => launchGame(featured)}
                style={{ backgroundImage: `url(${GATEWAY}/api/launchbox/image/${featured.id})`, backgroundSize: 'contain', backgroundPosition: 'right center', backgroundRepeat: 'no-repeat' }}
              >
                <div className="hero-overlay" />
                <div className="hero-content">
                  <span className="hero-tag">{hoveredGame ? 'Preview' : 'Last Session Active'}</span>
                  <h2 className="hero-title">{featured.title}</h2>
                  <p className="hero-meta">{featured.platform} • {featured.year || 'Unknown Year'}</p>
                  <button className="hero-play-btn" onClick={(e) => { e.stopPropagation(); launchGame(featured) }}>
                    ▶ {hoveredGame ? 'Launch' : 'Resume'}
                  </button>
                </div>
              </div>
            );
          })()}

          {/* Sub-Panel (Recent Games / Stats) */}
          {subPanelExpanded && (
            <div className="lora-subpanel">
              {/* Tab Navigation */}
              <div className="lora-tabs">
                <button
                  onClick={setTabRecent}
                  className={`lora-tab ${activeTab === 'recent' ? 'active' : ''}`}
                >
                  <span className="tab-icon">🕐</span>
                  Recently Played
                </button>
                <button
                  onClick={setTabStats}
                  className={`lora-tab ${activeTab === 'stats' ? 'active' : ''}`}
                >
                  <span className="tab-icon">📊</span>
                  Quick Stats
                </button>
                <button
                  onClick={closeSubPanel}
                  className="lora-tab-close"
                  aria-label="Collapse panel"
                >
                  ×
                </button>
              </div>

              {/* Tab Content */}
              <div className="lora-tab-content">
                {activeTab === 'recent' && (
                  <>
                    {/* Filter and Sort Controls */}
                    <div className="filter-controls">
                      <div className="filter-group filter-search">
                        <label htmlFor="search-games">Search:</label>
                        <input
                          id="search-games"
                          ref={searchInputRef}
                          type="text"
                          value={searchQuery}
                          onChange={handleSearchQueryChange}
                          placeholder="Search by title..."
                          className="filter-input"
                          autoComplete="off"
                        />
                      </div>

                      <div className="filter-group">
                        <label htmlFor="platform-filter">Platform:</label>
                        <select
                          id="platform-filter"
                          value={platformFilter}
                          onChange={handlePlatformFilterChange}
                          className="filter-select"
                        >
                          {platformsForFilter.map(platform => (
                            <option key={platform} value={platform}>{platform}</option>
                          ))}
                        </select>
                      </div>

                      <div className="filter-group">
                        <label htmlFor="genre-filter">Genre:</label>
                        <select
                          id="genre-filter"
                          value={genreFilter}
                          onChange={handleGenreFilterChange}
                          className="filter-select"
                        >
                          {genresForFilter.map(genre => (
                            <option key={genre} value={genre}>{genre}</option>
                          ))}
                        </select>
                      </div>

                      <div className="filter-group">
                        <label htmlFor="year-filter">Decade:</label>
                        <select
                          id="year-filter"
                          value={yearFilter}
                          onChange={handleYearFilterChange}
                          className="filter-select"
                        >
                          {decades.map(decade => (
                            <option key={decade} value={decade}>{decade}</option>
                          ))}
                        </select>
                      </div>

                      <div className="filter-group">
                        <label htmlFor="sort-by">Sort by:</label>
                        <select
                          id="sort-by"
                          value={sortBy}
                          onChange={handleSortByChange}
                          className="filter-select"
                        >
                          <option value="title">Title (A-Z)</option>
                          <option value="year">Year (Newest)</option>
                          <option value="platform">Platform (A-Z)</option>
                          <option value="last_played">Last Played (Recent)</option>
                          <option value="play_count">Most Played</option>
                        </select>
                      </div>

                      <div className="filter-results">
                        Showing {totalGames} game{totalGames !== 1 ? 's' : ''} total • {visibleGames.length} on this page
                      </div>
                      <div className="filter-actions">
                        <button className="lb-refresh-btn" onClick={refreshLibrary} title="Revalidate library cache">
                          Refresh Library
                        </button>
                        {cacheStatus && cacheStatus.last_loaded_at && ((Date.now() / 1000 - cacheStatus.last_loaded_at) > STALE_THRESHOLD_SECS) && (
                          <span className="lb-stale-badge" title="Cache may be stale">stale?</span>
                        )}
                      </div>
                    </div>

                    {/* Games Grid */}
                    <div className="games-grid">
                      {visibleGames.map((game) => (
                        <div key={game.id} onClick={() => setHoveredGame(game)} className={`game-card-wrapper ${hoveredGame?.id === game.id ? 'selected' : ''}`}>
                          <GameCard
                            game={game}
                            onLaunch={launchGame}
                            onGameHover={(g) => blinkySelection.gameSelected(g, g.platform || 'MAME')}
                            formatRelativeTime={formatRelativeTime}
                            pluginAvailable={pluginAvailable}
                            launchDisabled={!canLaunchHere(game) || isLockActive}
                          />
                        </div>
                      ))}
                      {visibleGames.length === 0 && (
                        <div className="no-games-message">
                          No games match your filters. Try adjusting your selection.
                        </div>
                      )}
                    </div>

                    {/* Pagination Controls */}
                    {totalPages > 1 && (
                      <div className="pagination-controls">
                        <button
                          onClick={goToPreviousPage}
                          disabled={currentPage === 1}
                          className="pagination-btn"
                        >
                          ← Previous
                        </button>
                        <span className="pagination-info">
                          Page {currentPage} of {totalPages}
                        </span>
                        <button
                          onClick={() => goToNextPage(totalPages)}
                          disabled={currentPage === totalPages}
                          className="pagination-btn"
                        >
                          Next →
                        </button>
                      </div>
                    )}
                  </>
                )}

                {activeTab === 'stats' && (
                  <div className="stats-grid">
                    <div className="stat-card stat-total">
                      <div className="stat-label">Total Games</div>
                      <div className="stat-value">{displayStats.total_games || displayStats.totalGames}</div>
                      <div className="stat-change">{displayStats.is_mock_data ? 'Mock Data' : displayStats.a_drive_status}</div>
                    </div>
                    <div className="stat-card stat-platforms">
                      <div className="stat-label">Platforms</div>
                      <div className="stat-value">{displayStats.platforms_count || displayStats.platforms}</div>
                      <div className="stat-change">{displayStats.platforms_count || displayStats.platforms} platforms</div>
                    </div>
                    <div className="stat-card stat-most-played">
                      <div className="stat-label">Genres</div>
                      <div className="stat-value">{displayStats.genres_count || 0}</div>
                      <div className="stat-change">{displayStats.genres_count || 0} genres</div>
                    </div>
                    <div className="stat-card stat-playtime">
                      <div className="stat-label">XML Files Parsed</div>
                      <div className="stat-value">{displayStats.xml_files_parsed || 0}</div>
                      <div className="stat-change">{displayStats.is_mock_data ? 'Using mock data' : 'Real A: drive data'}</div>
                    </div>
                  </div>
                )}
              </div>
            </div>
          )}

          {/* Collapsed Toggle */}
          {!subPanelExpanded && (
            <button
              onClick={toggleSubPanel}
              className="lora-expand-btn"
            >
              Show Recent Games ▲
            </button>
          )}

          {/* Input Area */}
          <div className="lora-input-area">
            <div className="lora-inline-status-row" aria-live="polite">
              <div className={`lora-inline-status-pill ${statusColor}`}>
                <div className="status-dot" />
                <span>{statusText}</span>
              </div>
              {isLockActive && (
                <span className="lora-inline-status-warning">Launch lock active</span>
              )}
              {!isLockActive && isChatLoading && (
                <span className="lora-inline-status-hint">Preparing response...</span>
              )}
            </div>
            <div className="lora-input-row">
              <input
                type="text"
                value={input}
                onChange={handleInputChange}
                onKeyPress={handleInputKeyPress}
                placeholder="Ask LoRa about your games..."
                className="lora-input"
                disabled={isChatLoading}
              />
              <button
                onClick={sendMessage}
                className="lora-send-btn"
                disabled={isChatLoading || !input.trim()}
                aria-label="Send message"
              >
                ➤
              </button>
            </div>
          </div>
        </div>{/* end lora-main */}
      </div>

      <LoraChatDrawer
        open={chatOpen}
        onClose={closeChat}
        isRecording={isRecording}
        isChatLoading={isChatLoading}
        messages={messages}
        input={input}
        onInputChange={handleInputChange}
        onInputKeyPress={handleInputKeyPress}
        onToggleMic={toggleMic}
        onSend={sendMessage}
        voiceBars={voiceBars}
        memoizedStyles={memoizedStyles}
        chatMessagesRef={chatMessagesRef}
        ChatMessageComponent={ChatMessage}
      />

      {toastMsg && (
        <div style={{ position: 'fixed', right: 16, bottom: 16, background: 'rgba(20,20,20,0.9)', color: '#c8ff00', padding: '8px 12px', borderRadius: 6, border: '1px solid rgba(200,255,0,0.4)' }}>
          {toastMsg}
        </div>
      )}
    </PanelShell>
  )
}

export default function LaunchBoxPanel() {
  return (
    <LaunchBoxErrorBoundary>
      <LaunchBoxPanelContent />
    </LaunchBoxErrorBoundary>
  )
}







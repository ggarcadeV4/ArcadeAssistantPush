// @panel: LaunchBoxPanel
// @role: Game library management and launching interface
// @owner: LoRa
// @linked: backend/routers/launchbox.py
// @features: game-browsing, filtering, statistics, launching

import React, { useCallback, useEffect, useRef, useState, useMemo, memo } from 'react'
import { PanelShell, DiffPreview } from '../_kit'
import { API_ENDPOINTS } from '../../constants/a_drive_paths'
import { speakAsLora, stopSpeaking } from '../../services/ttsClient'
import './launchbox.css'
import { useProfileContext } from '../../context/ProfileContext'
import { useBlinkyGameSelection } from '../../hooks/useBlinkyGameSelection'
import useVoiceRecording from './hooks/useVoiceRecording'
import useLaunchLock from './hooks/useLaunchLock'
import usePluginHealth from './hooks/usePluginHealth'
import useShaderPreview from './hooks/useShaderPreview'

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
  ? 'http://localhost:8787'
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
    .replace(/[\u2018\u2019]/g, '')
    .replace(/[^a-z0-9]+/g, ' ')
    .replace(/\s+/g, ' ')
    .trim()
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
    .replace(/^[-\u2022]\s+/gm, '')           // Remove bullet points
    .replace(/^\d+\.\s+/gm, '')          // Remove numbered lists

  return (
    <div className={`chat-message ${role}`}>
      <div className="message-bubble">
        {cleanMessage}
      </div>
    </div>
  )
})

// Memoized game card component to prevent unnecessary re-renders
const GameCard = memo(({ game, onLaunch, onGameHover, formatRelativeTime, pluginAvailable, launchDisabled }) => {
  const handleLaunch = useCallback(() => {
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
    <div className="game-card" onMouseEnter={handleMouseEnter}>
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
        className={`game-play-btn ${isDisabled ? 'disabled' : ''}`}
        onClick={handleLaunch}
        disabled={isDisabled}
        title={launchTooltip}
        aria-label={launchTooltip}
      >
        ▶
      </button>
    </div>
  )
})

export default function LaunchBoxPanel() {
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
  // Cross-tab launch lock
  const { lockUntil, isLockActive, acquireLock, releaseLock } = useLaunchLock({
    storageKey: 'launchbox:lock',
    lockMs: 5000,
  })

  // Plugin health
  const {
    checkingPlugin,
    pluginStatus,
    pluginAvailable,
    checkPluginHealth,
  } = usePluginHealth({ gateway: GATEWAY, cacheMs: 30000 })

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
  const [sortBy, setSortBy] = useState('lastPlayed')
  const [sortOrder, setSortOrder] = useState('asc')
  const [searchQuery, setSearchQuery] = useState('')
  const debouncedSearchQuery = useDebounce(searchQuery, 300)
  const [currentPage, setCurrentPage] = useState(1)
  const GAMES_PER_PAGE = 50 // Updated to a more reasonable page size


  // Chat state
  const [isChatLoading, setIsChatLoading] = useState(false)

  // Shader preview (extracted to hook — Phase 1a)
  const {
    shaderModal,
    shaderPreview,
    pendingShaderApply,
    maybeHandleShaderToolCalls,
    applyShaderChange,
    closeShaderPreview,
    openShaderPreview,
    removeShaderBinding,
    cancelShaderPreview,
  } = useShaderPreview({ addMessage, showToast, setChatOpen, deviceId })

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

  // Voice recording (replaces inline MediaRecorder + Web Speech logic)
  const {
    isRecording,
    isTranscribing,
    startVoiceRecording,
    stopVoiceRecording,
  } = useVoiceRecording({
    addMessage,
    showToast,
    setLoraState,
    onTranscript: (text) => {
      setInput(text)
      sendMessageWithTextRef.current?.(text)
    },
  })

  // Cache status (for stale indicator)
  const [cacheStatus, setCacheStatus] = useState(null)
  const STALE_THRESHOLD_SECS = 6 * 3600 // 6 hours

  const fetchCacheStatus = useCallback(async () => {
    try {
      const res = await fetch(`${GATEWAY}${API_ENDPOINTS.CACHE_STATUS}`, { headers: { 'Cache-Control': 'no-cache' } })
      if (res.ok) {
        const s = await res.json()
        setCacheStatus(s)
      }
    } catch (_) {
      // ignore
    }
  }, [])



  // Define supported platforms for direct launch in this panel
  const isSupportedPlatform = useCallback((platform) => {
    if (!platform) return false
    // Allow all platforms - backend will handle launch method selection
    // This includes: MAME (Arcade), RetroArch (NES, SNES, Genesis, etc.), PCSX2 (PS2), and more
    return true
  }, [])

  const canLaunchHere = useCallback((game) => {
    return !!game && isSupportedPlatform(game.platform)
  }, [isSupportedPlatform])


  useEffect(() => {
    checkPluginHealth()
  }, [checkPluginHealth])

  // Fetch cache status and initial metadata on mount
  useEffect(() => {
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

      const serverSortBy = (sortBy === 'title' || sortBy === 'year') ? sortBy : 'title'

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

  // Mock recent games for display while data loads (TODO: Remove when using real data)
  const mockGames = [
    {
      id: '1e48ac15-55e2-47f7-a33e-486451a16def',
      title: 'Mortal Kombat II',
      platform: 'Arcade',
      year: 1993,
      genre: 'Fighting',
      lastPlayed: new Date(Date.now() - 2 * 60 * 60 * 1000),
      sessionTime: '45 min',
      playCount: 28
    },
    {
      id: '2f59bc26-66f3-58g8-b44f-597562b27efg',
      title: 'Street Fighter II',
      platform: 'Arcade',
      year: 1991,
      genre: 'Fighting',
      lastPlayed: new Date(Date.now() - 24 * 60 * 60 * 1000),
      sessionTime: '32 min',
      playCount: 47
    },
    {
      id: '3g60cd37-77g4-69h9-c55g-608673c38fhi',
      title: 'Metal Slug',
      platform: 'Arcade',
      year: 1996,
      genre: 'Run & Gun',
      lastPlayed: new Date(Date.now() - 3 * 24 * 60 * 60 * 1000),
      sessionTime: '28 min',
      playCount: 32
    },
    {
      id: '4h71de48-88h5-70i0-d66h-719784d49gij',
      title: 'Pac-Man',
      platform: 'Arcade',
      year: 1980,
      genre: 'Maze',
      lastPlayed: new Date(Date.now() - 5 * 24 * 60 * 60 * 1000),
      sessionTime: '22 min',
      playCount: 89
    },
    {
      id: '5i82ef59-99i6-81j1-e77i-820895e50hjk',
      title: 'Galaga',
      platform: 'Arcade',
      year: 1981,
      genre: 'Shooter',
      lastPlayed: new Date(Date.now() - 7 * 24 * 60 * 60 * 1000),
      sessionTime: '18 min',
      playCount: 65
    }
  ]

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
      addMessage('\u274C No game selected to launch.', 'assistant')
      return
    }

    if (loading) {
      addMessage('\u23F3 Library is still loading. Try again in a moment.', 'assistant')
      return
    }

    // Respect panel scope: only allow supported platforms here
    if (!canLaunchHere(game)) {
      addMessage('\u2139\uFE0F Heads up: This title isn\u2019t launchable from this panel. Try LaunchBox for this game.', 'assistant')
      showToast('Try LaunchBox for this title')
      return
    }

    // If plugin is offline, continue with backend fallbacks for supported platforms
    if (!pluginAvailable) {
      addMessage('\u26A0\uFE0F Plugin offline. Attempting fallback launch for supported platforms...', 'assistant')
    }

    // Debounce: prevent launching same game within 3 seconds
    const now = Date.now()
    if (lastLaunchRef.current.title === game.title &&
      (now - lastLaunchRef.current.timestamp) < 3000) {
      addMessage(`\u23F8\uFE0F Already launching ${game.title}, please wait...`, 'assistant')
      return
    }

    lastLaunchRef.current = { title: game.title, timestamp: now }

    // Cross-tab lock: acquire before starting
    acquireLock()
    setLoraState('launching')
    addMessage(`Launching ${game.title} for ${scoreProfileName}...`, 'assistant')

    // Fire LED lighting immediately (no debounce)
    blinkySelection.gameLaunch(game.title, game.platform || 'MAME')

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
        addMessage(`\u2705 ${game.title} launched via ${result.method_used}`, 'assistant')
        showToast(`Launched via: ${result.method_used}`)
      } else {
        // Backend returns 'message' field, not 'error' field - check message first
        const errorMsg = result.message || result.error || 'Unknown error occurred'
        addMessage(`\u274C Failed to launch ${game.title}: ${errorMsg}`, 'assistant')
        showToast('Launch failed')
      }
    } catch (err) {
      console.error('Launch failed:', err)
      // Provide more detailed error information with proper fallbacks
      const errorDetail = err.message || err.toString() || 'Network error'
      addMessage(`\u274C Launch error: ${errorDetail}`, 'assistant')
      showToast('Launch error')
    } finally {
      setLoraState('idle')
      releaseLock()  // Release cross-tab lock after launch completes/fails
    }
  }, [addMessage, loading, pluginAvailable, canLaunchHere, showToast, acquireLock, releaseLock, apiHeaders, blinkySelection, scoreProfileName, scoreProfileId])

  // --- Shader Preview Helpers (extracted to useShaderPreview — Phase 1a) ---

  // Resolve game title via plugin, then launch
  const resolveAndLaunch = useCallback(async (title, filters = {}) => {

    const trimmedTitle = (title || '').trim()

    if (!trimmedTitle) {

      addMessage('Heads up: provide a game title to resolve.', 'assistant')

      return

    }

    setLoraState('processing')

    addMessage(`dY"? Searching for "${trimmedTitle}"...`, 'assistant')



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
            addMessage(`dYZr Found: ${only.title}. Launching...`, 'assistant')
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
          addMessage(`Heads up: ${sourceLabel}: ${payload.game.title}${confidenceSuffix}. Please confirm by adding platform/year so I don't launch the wrong game.`, 'assistant')
          return
        }

        addMessage(`dYZr ${sourceLabel}: ${payload.game.title}${confidenceSuffix}. Launching...`, 'assistant')

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

        addMessage(`Heads up: I found ${suggestions.length} matches for "${trimmedTitle}". Please specify platform/year so I don't launch the wrong one. Top matches: ${listPreview}`, 'assistant')

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
            addMessage(`dYZr Found: ${only.title}. Launching...`, 'assistant')
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
    setSortBy(e.target.value)
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

      addMessage(`\uD83C\uDFB2 Random selection for ${scoreProfileName}: ${randomGame.title} (${randomGame.year || 'Unknown'})`, 'assistant')
      setLoraState('launching')
      setTimeout(() => {
        launchGame(randomGame)
      }, 1000)
      return
    } catch (err) {
      // Fallback: pick from currently loaded page
      const candidates = visibleGames.length > 0 ? visibleGames : games
      if (!candidates || candidates.length === 0) {
        addMessage('\u274C No games available for random selection.', 'assistant')
        return
      }
      const fallback = candidates[Math.floor(Math.random() * candidates.length)]
      if (!fallback) {
        addMessage('\u274C Failed to select a random game. Please try again.', 'assistant')
        return
      }
      addMessage(`\uD83C\uDFB2 Random selection for ${scoreProfileName}: ${fallback.title} (${fallback.year || 'Unknown'})`, 'assistant')
      setLoraState('launching')
      setTimeout(() => {
        launchGame(fallback)
      }, 1000)
    }
  }, [platformFilter, visibleGames, games, apiHeaders, addMessage, launchGame, scoreProfileName])

  // Launch Pegasus fullscreen frontend (fire-and-forget for instant UI response)
  const launchPegasus = useCallback(() => {
    // Immediate UI feedback - don't wait for API
    addMessage('\uD83C\uDFAE Launching Pegasus...', 'assistant')

    // Fire-and-forget: launch in background, don't block UI
    fetch(`${GATEWAY}/api/launchbox/pegasus/launch`, {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
        'x-device-id': deviceId,
        'x-panel': 'launchbox'
      }
    }).then(response => {
      if (!response.ok) {
        response.json().catch(() => ({})).then(data => {
          addMessage(`\u274C Failed to launch Pegasus: ${data.message || 'Unknown error'}`, 'assistant')
        })
      }
      // Success case: Pegasus is launching, no need for confirmation message
      // (it takes over the screen anyway)
    }).catch(err => {
      addMessage(`\u274C Failed to launch Pegasus: ${err.message}`, 'assistant')
    })
  }, [addMessage, deviceId])

  // AI chat message handler
  const sendMessage = useCallback(async () => {
    const text = input.trim()
    if (!text) return

    // Cancel any ongoing TTS to prevent overlap
    try { stopSpeaking() } catch { }

    addMessage(text, 'user')
    setInput('')
    setLoraState('processing')
    setIsChatLoading(true)

    try {
      // Chat profile is separate from score attribution (defaults to Vicky)
      const profileId = chatProfileId
      const profileName = chatProfileName

      // Call dedicated LaunchBox chat endpoint
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
            source: activeProfileDetails?.description || 'LaunchBox'
          },
          context: {
            currentFilters: {
              genre: genreFilter,
              platform: platformFilter,
              decade: yearFilter,
              sortBy: sortBy,
              search: searchQuery
            },
            availableGames: totalGames,
            totalGames: totalGames,
            stats: stats,
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

        // If a game was launched, update UI state
        if (result.game_launched) {
          setLoraState('launching')
          setTimeout(() => setLoraState('idle'), 2000)
        }

        // Handle shader preview/tool results
        maybeHandleShaderToolCalls(result.tool_calls_made, result.response)
      } else {
        addMessage('Sorry, I had trouble processing that request.', 'assistant')
      }
    } catch (error) {
      console.error('[LaunchBox AI] Error:', error)
      addMessage(`Sorry, I encountered an error: ${error.message}`, 'assistant')
    } finally {
      setLoraState('idle')
      setIsChatLoading(false)
    }
  }, [input, addMessage, genreFilter, platformFilter, yearFilter, sortBy, searchQuery, totalGames, stats, allowRetroArch, directRetroArchEnabled, chatProfileId, chatProfileName, activeProfileDetails, deviceId])

  // Helper function to send message with custom text (for voice transcription)
  const sendMessageWithText = useCallback(async (text) => {
    if (!text || !text.trim()) return

    // Cancel any ongoing TTS to prevent overlap
    try { stopSpeaking() } catch { }

    const messageText = text.trim()
    addMessage(messageText, 'user')
    setLoraState('processing')
    setIsChatLoading(true)

    try {
      // Chat profile is separate from score attribution (defaults to Vicky)
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
          message: messageText,
          profile: {
            id: profileId,
            name: profileName,
            source: 'LaunchBox'
          },
          context: {
            currentFilters: {
              genre: genreFilter,
              platform: platformFilter,
              decade: yearFilter,
              sortBy: sortBy,
              search: searchQuery
            },
            availableGames: totalGames,
            totalGames: totalGames,
            stats: stats,
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

        // Speak the response since user used voice input
        speakAsLora(result.response).catch(err => {
          console.warn('[LaunchBox TTS] Failed to speak response:', err)
        })

        if (result.game_launched) {
          setLoraState('launching')
          setTimeout(() => setLoraState('idle'), 2000)
        }

        // Handle shader preview/tool results for voice path
        maybeHandleShaderToolCalls(result.tool_calls_made, result.response)
      } else {
        const errorMsg = 'Sorry, I had trouble processing that request.'
        addMessage(errorMsg, 'assistant')
        speakAsLora(errorMsg).catch(err => {
          console.warn('[LaunchBox TTS] Failed to speak error:', err)
        })
      }
    } catch (error) {
      console.error('[LaunchBox AI] Error:', error)
      const errorMsg = `Sorry, I encountered an error: ${error.message}`
      addMessage(errorMsg, 'assistant')
      speakAsLora(errorMsg).catch(err => {
        console.warn('[LaunchBox TTS] Failed to speak error:', err)
      })
    } finally {
      setLoraState('idle')
      setIsChatLoading(false)
      setInput('') // Clear input after sending
    }
  }, [addMessage, genreFilter, platformFilter, yearFilter, sortBy, searchQuery, totalGames, stats, allowRetroArch, directRetroArchEnabled, chatProfileId, chatProfileName, deviceId])

  // Assign to ref so it can be called from voice callbacks
  useEffect(() => {
    sendMessageWithTextRef.current = sendMessageWithText
  }, [sendMessageWithText])

  // Stop any ongoing TTS when this panel unmounts
  useEffect(() => () => { try { stopSpeaking() } catch { } }, [])

  // Handoff effect (handles Dewey -> LaunchBox context handoff)
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

  // Show loading state
  if (loading) {
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
              <p className="error-message">\u23F3 Arcade Assistant is starting up...</p>
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
            <span style={{ fontSize: '11px', textTransform: 'uppercase', letterSpacing: '0.08em', color: 'var(--nm-primary)' }}>
              RetroArch
            </span>
            <label style={{ display: 'flex', gap: '8px', alignItems: 'center', fontSize: '13px', color: 'var(--nm-on-surface)' }}>
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
            <span style={{ fontSize: '11px', color: 'var(--nm-on-surface-variant)' }}>
              {directRetroArchEnabled === true ? 'Direct launch enabled' : directRetroArchEnabled === false ? 'Direct launch disabled' : 'Direct launch unknown'}
            </span>
          </div>

          {/* Profile Selector */}
          <div
            className="lora-profile-select"
            style={{ display: 'flex', flexDirection: 'column', gap: '4px', alignItems: 'flex-start', minWidth: '140px' }}
          >
            <span style={{ fontSize: '11px', textTransform: 'uppercase', letterSpacing: '0.08em', color: 'var(--nm-primary)' }}>
              Chat Profile
            </span>
            <select
              value={activeProfile}
              onChange={handleProfileChange}
              className="input"
              style={{
                padding: '6px 10px',
                background: 'var(--nm-surface-container-lowest)',
                border: '1px solid rgba(204, 151, 255, 0.3)',
                borderRadius: '6px',
                color: 'var(--nm-on-surface)',
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
              <span style={{ fontSize: '11px', color: 'var(--nm-on-surface-variant)' }}>
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

          {/* Pegasus Launch Button */}
          <button
            onClick={launchPegasus}
            className="lora-pegasus-btn"
            aria-label="Launch Pegasus fullscreen frontend"
            title="Switch to Pegasus (fullscreen)"
          >
            <img
              src="/pegasus-button.png"
              alt="Launch Pegasus"
              className="pegasus-btn-image"
            />
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
      {/* Shader Preview Modal */}
      {shaderModal.open && (
        <div role="dialog" aria-modal="true" aria-label="Shader preview" className="shader-preview-overlay">
          <div className="shader-preview-card">
            <h3 className="shader-preview-title">Shader Configuration for {shaderModal.gameId}</h3>
            <div className="shader-preview-details">
              <div className="shader-detail-item">
                <span className="shader-detail-label">Shader:</span>
                <span className="shader-detail-value">{shaderModal.shaderName || 'n/a'}</span>
              </div>
              <div className="shader-detail-item">
                <span className="shader-detail-label">Emulator:</span>
                <span className="shader-detail-value">{shaderModal.emulator || 'n/a'}</span>
              </div>
              {shaderModal.diff && (
                <div className="shader-detail-item">
                  <span className="shader-detail-label">Change:</span>
                  <span className="shader-detail-value">{shaderModal.diff}</span>
                </div>
              )}
            </div>
            {shaderModal.error && (
              <div style={{ color: 'var(--nm-error)', marginBottom: 8 }}>Error: {shaderModal.error}</div>
            )}
            <div style={{ marginTop: 6 }}>
              <DiffPreview
                oldText={shaderPreview?.oldText || JSON.stringify(shaderModal.oldConfig || { shader: 'none' }, null, 2)}
                newText={shaderPreview?.newText || JSON.stringify(shaderModal.newConfig || {}, null, 2)}
              />
            </div>
            <div className="shader-preview-actions">
              <button
                onClick={cancelShaderPreview}
                disabled={shaderModal.applying}
                className="shader-btn shader-btn-cancel"
              >
                Cancel
              </button>
              <button onClick={applyShaderChange} disabled={shaderModal.applying} className="shader-btn shader-btn-apply">
                {shaderModal.applying ? 'Applying\u2026' : 'Apply Shader'}
              </button>
            </div>
          </div>
        </div>
      )}
      {/* Animated Background Grid */}
      <div className="lora-bg-grid" />

      {/* Plugin offline banner intentionally omitted: Launches do not depend on plugin availability */}

      {/* Main Content Area */}
      <div className="lora-content">
        {/* Import UI reverted */}
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
                      </select>
                    </div>

                    <div className="filter-results">
                      Showing {totalGames} game{totalGames !== 1 ? 's' : ''} total \u2022 {visibleGames.length} on this page
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

                  {/* Games List */}
                  <div className="recent-games-list">
                    {visibleGames.map((game) => (
                      <GameCard
                        key={game.id}
                        game={game}
                        onLaunch={launchGame}
                        onGameHover={(g) => blinkySelection.gameSelected(g.title, g.platform || 'MAME')}
                        formatRelativeTime={formatRelativeTime}
                        pluginAvailable={pluginAvailable}
                        launchDisabled={!canLaunchHere(game) || isLockActive}
                      />
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
                        \u2190 Previous
                      </button>
                      <span className="pagination-info">
                        Page {currentPage} of {totalPages}
                      </span>
                      <button
                        onClick={() => goToNextPage(totalPages)}
                        disabled={currentPage === totalPages}
                        className="pagination-btn"
                      >
                        Next \u2192
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
            Show Recent Games \u25B2
          </button>
        )}

        {/* Input Area */}
        <div className="lora-input-area">
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
            \u27A4
          </button>
        </div>
      </div>

      {/* Sliding Chat Panel */}
      {chatOpen && (
        <>
          <div className="panel-chat-overlay" onClick={closeChat} />
          <div className="panel-chat-sidebar" role="dialog" aria-label="Chat with LoRa">
            {/* Chat Header */}
            <div className="chat-header">
              <img src="/lora-avatar.jpeg" alt="LoRa" className="chat-avatar" />
              <div className="chat-header-info">
                <h3>Chat with LoRa</h3>
                {isRecording && (
                  <div className="voice-active-indicator">
                    <span className="voice-wave-icon">〰️</span>
                    Voice Active
                  </div>
                )}
              </div>
              <button
                onClick={closeChat}
                className="chat-close-btn"
                aria-label="Close chat"
              >
                ×
              </button>
            </div>

            {/* Chat Messages */}
            <div className="chat-messages" ref={chatMessagesRef}>
              {messages.map((msg, idx) => (
                <ChatMessage
                  key={idx}
                  message={msg.text}
                  role={msg.role}
                />
              ))}
              {isChatLoading && (
                <div className="chat-message assistant">
                  <div className="message-bubble">
                    <span className="typing-indicator">\u25CF\u25CF\u25CF</span>
                  </div>
                </div>
              )}
            </div>

            {/* Voice Visualization (when mic active) */}
            {isRecording && (
              <div className="voice-visualization">
                <div className="voice-bars">
                  {voiceBars.map((_, i) => (
                    <div key={i} className="voice-bar" style={memoizedStyles.voiceBarDelays[i]} />
                  ))}
                </div>
                <p className="voice-status">Listening...</p>
              </div>
            )}

            {/* Chat Input Area */}
            <div className="chat-input-container">
              <div className="chat-input-row">
                <input
                  type="text"
                  className="chat-input-field"
                  value={input}
                  onChange={handleInputChange}
                  onKeyPress={handleInputKeyPress}
                  placeholder={isRecording ? "Listening..." : "Type your message or use voice input..."}
                  aria-label="Chat with LoRa"
                  disabled={isChatLoading}
                />
                <button
                  className={`chat-voice-btn ${isRecording ? 'recording' : ''}`}
                  onClick={toggleMic}
                  title={isRecording ? 'Stop voice input' : 'Start voice input'}
                  aria-label={isRecording ? 'Stop voice input' : 'Start voice input'}
                >
                  {isRecording ? (
                    <span style={memoizedStyles.stopIcon}>\u23F9\uFE0F</span>
                  ) : (
                    <img src="/lora-mic.png" alt="Microphone" style={memoizedStyles.micIcon} />
                  )}
                </button>
                <button
                  className="chat-send-btn-sidebar"
                  onClick={sendMessage}
                  disabled={isChatLoading || !input.trim()}
                  aria-label="Send message"
                >
                  \u27A4
                </button>
              </div>
            </div>
          </div>
        </>
      )}

      {toastMsg && (
        <div style={{ position: 'fixed', right: 16, bottom: 16, background: 'rgba(25,25,28,0.95)', color: 'var(--nm-secondary)', padding: '8px 12px', borderRadius: 6, border: '1px solid rgba(58,223,250,0.3)', backdropFilter: 'blur(12px)' }}>
          {toastMsg}
        </div>
      )}
    </PanelShell>
  )
}

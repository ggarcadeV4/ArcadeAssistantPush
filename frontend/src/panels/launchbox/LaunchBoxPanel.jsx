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
const LORA_EXCLUDE_SPECIALIZED_PARAM = 'exclude_lora_specialized=1'
const PROFILE_STORAGE_KEY = 'launchbox:active-profile'
const RETROARCH_ALLOWED_STORAGE_KEY = 'launchbox:allow-retroarch'
// Ensure API calls hit the gateway when running under Vite (5173)
const GATEWAY = (typeof window !== 'undefined' && window.location && window.location.port === '5173')
  ? 'http://localhost:8787'
  : ''

function isLoRaExcludedPlatform(platformName) {
  const normalized = (platformName || '').trim().toLowerCase()
  if (!normalized) return false
  return normalized === 'american laser games'
    || normalized === 'daphne'
    || normalized === 'teknoparrot arcade'
    || normalized === 'taito type x'
    || normalized.includes('gun games')
}

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

const buildGameImageUrl = (game, variant = 'card') => {
  const keySource = [
    game?.box_front_path || '',
    game?.screenshot_path || '',
    game?.clear_logo_path || '',
  ].join('|')

  const cacheKey = encodeURIComponent(keySource || `${game?.id || 'unknown'}:${variant}:none`)
  return `${GATEWAY}/api/launchbox/image/${game.id}?variant=${encodeURIComponent(variant)}&cache_key=${cacheKey}`
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
          src={buildGameImageUrl(game, 'card')}
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
  const [selectedGameIndex, setSelectedGameIndex] = useState(0) // Hero carousel selection
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
  const [hasLoadedOnce, setHasLoadedOnce] = useState(false)

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
  const sidebarRef = useRef(null)

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
    if (isLoRaExcludedPlatform(platform)) return false
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
          fetch(`${GATEWAY}${API_ENDPOINTS.PLATFORMS}?${LORA_EXCLUDE_SPECIALIZED_PARAM}`),
          fetch(`${GATEWAY}${API_ENDPOINTS.GENRES}?${LORA_EXCLUDE_SPECIALIZED_PARAM}`),
          fetch(`${GATEWAY}${API_ENDPOINTS.STATS}?${LORA_EXCLUDE_SPECIALIZED_PARAM}`)
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
        exclude_lora_specialized: '1',
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
        setHasLoadedOnce(true)

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
        const methodUsed = String(result.method_used || '')
        if (methodUsed.includes('unconfirmed')) {
          addMessage(`\u2139\uFE0F ${game.title} launch started, but process confirmation timed out. If the game opened, you can ignore this notice.`, 'assistant')
          showToast('Launch started')
        } else {
          addMessage(`\u2705 ${game.title} launched via ${result.method_used}`, 'assistant')
          showToast(`Launched via: ${result.method_used}`)
        }
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
    addMessage(`\uD83D\uDD0D Searching for "${trimmedTitle}"...`, 'assistant')

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
            addMessage(`\uD83C\uDFAF Found: ${only.title}. Launching...`, 'assistant')
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
        addMessage(`\uD83C\uDFAF ${sourceLabel}: ${payload.game.title}${confidenceSuffix}. Launching...`, 'assistant')
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
            addMessage(`\uD83C\uDFAF Found: ${only.title}. Launching...`, 'assistant')
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
    const nextSortBy = e.target.value
    setSortBy(nextSortBy)
    setSortOrder(nextSortBy === 'year' ? 'desc' : 'asc')
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

  useEffect(() => {
    if (isLoRaExcludedPlatform(platformFilter)) {
      setPlatformFilter('All')
    }
  }, [platformFilter])

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
      params.set('exclude_lora_specialized', '1')
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

  // Launch native LaunchBox/Big Box frontend (fire-and-forget for instant UI response)
  const launchPegasus = useCallback(() => {
    // Immediate UI feedback - don't wait for API
    addMessage('\uD83C\uDFAE Launching Big Box...', 'assistant')

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
          addMessage(`\u274C Failed to launch Big Box: ${data.message || 'Unknown error'}`, 'assistant')
        })
      }
      // Success case: Big Box is launching, no need for confirmation message
      // (it takes over the screen anyway)
    }).catch(err => {
      addMessage(`\u274C Failed to launch Big Box: ${err.message}`, 'assistant')
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

  // Selected game for hero display
  const selectedGame = useMemo(() => {
    if (!games || games.length === 0) return null
    return games[selectedGameIndex % games.length] || games[0]
  }, [games, selectedGameIndex])

  const cacheLastUpdated = cacheStatus?.last_updated || cacheStatus?.generated_at || cacheStatus?.updated_at || null
  const cacheIsStale = useMemo(() => {
    if (!cacheLastUpdated) return false
    const lastUpdatedTs = new Date(cacheLastUpdated).getTime()
    if (!Number.isFinite(lastUpdatedTs)) return false
    return ((Date.now() - lastUpdatedTs) / 1000) > STALE_THRESHOLD_SECS
  }, [cacheLastUpdated])

  const directLaunchText = useMemo(() => {
    if (directRetroArchEnabled === null) return 'Direct Launch Unknown'
    return directRetroArchEnabled ? 'Direct Launch Enabled' : 'Direct Launch Disabled'
  }, [directRetroArchEnabled])

  const libraryCards = useMemo(() => visibleGames, [visibleGames])
  const currentRangeStart = totalGames === 0 ? 0 : ((currentPage - 1) * GAMES_PER_PAGE) + 1
  const currentRangeEnd = totalGames === 0 ? 0 : Math.min(totalGames, currentPage * GAMES_PER_PAGE)
  const subpanelModeLabel = activeTab === 'stats' ? 'Quick Stats' : 'Recent'
  const shellStatus = pluginAvailable ? 'online' : 'degraded'
  const heroTag = selectedGame?.genre || selectedGame?.platform || 'Featured Game'
  const heroMeta = [
    selectedGame?.platform,
    selectedGame?.year,
    selectedGame?.genre,
  ].filter(Boolean).join(' • ')

  const shellHeaderActions = (
    <div className="lora-shell-actions" aria-hidden="true">
      <span className={`lora-shell-pill ${statusColor}`}>{statusText}</span>
      <span className={`lora-shell-pill ${cacheIsStale ? 'is-stale' : 'is-fresh'}`}>
        {cacheIsStale ? 'Cache Stale' : 'Cache Fresh'}
      </span>
    </div>
  )

  const renderPanelFrame = (content) => (
    <PanelShell
      title="LaunchBox LoRa"
      subtitle="Cinematic library and launch surface"
      status={shellStatus}
      headerActions={shellHeaderActions}
      className="lora-panel-shell"
      bodyClassName="lora-panel-shell-body"
    >
      {content}
    </PanelShell>
  )

  const showBlockingLoad = loading && !hasLoadedOnce

  // Show loading state
  if (showBlockingLoad) {
    return renderPanelFrame(
      <div className="lora-cinematic">
        <div className="lora-loading-state">
          <div className="lora-loading-spinner" />
          <p className="lora-error-title">Loading game library...</p>
          <p className="lora-error-msg">This may take a few seconds if parsing XML files...</p>
        </div>
      </div>
    )
  }

  // Show error state
  if (error) {
    return renderPanelFrame(
      <div className="lora-cinematic">
        <div className="lora-error-state">
          {error.includes('ECONNREFUSED') || error.includes('Failed to fetch') ? (
            <>
              <p className="lora-error-title">{'\u23F3'} Arcade Assistant is starting up...</p>
              <p className="lora-error-msg">The backend is still loading. This usually takes 10-30 seconds on startup.</p>
            </>
          ) : error.includes('LaunchBox path not found') ? (
            <>
              <p className="lora-error-title">{'\uD83D\uDCC2'} LaunchBox Not Found</p>
              <p className="lora-error-msg">{error}</p>
            </>
          ) : (
            <>
              <p className="lora-error-title">{'\u274C'} Failed to load game library</p>
              <p className="lora-error-msg">{error}</p>
            </>
          )}
          <button className="lora-retry-btn" onClick={handleReload}>
            Retry
          </button>
        </div>
      </div>
    )
  }

  return renderPanelFrame(
    <div className={`lora-cinematic ${chatOpen ? 'chat-open' : ''}`}>
      {/* Cinematic Background */}
      <div className="lora-bg-cinematic">
        <img src="/lora-hero.png" alt="" />
        <div className="lora-bg-scrim-bottom" />
        <div className="lora-bg-scrim-left" />
      </div>

      {/* Main Canvas */}
      <div className="lora-canvas">
        {/* Header Bar */}
        <div className="lora-header-bar">
          <div className="lora-brand">
            <div>
              <span className="lora-brand-title">LaunchBox LoRa</span>
              <div className="lora-top-nav">
                <button type="button" className="lora-top-link active">Library</button>
              </div>
            </div>
          </div>
          <div className="lora-header-controls">
            <label className="lora-search-bar">
              <span className="lora-search-icon">⌕</span>
              <input
                ref={searchInputRef}
                type="text"
                value={searchQuery}
                onChange={handleSearchQueryChange}
                placeholder="SEARCH DATABASE"
                aria-label="Search LaunchBox library"
              />
            </label>
            <div className={`lora-status-pill ${statusColor}`}>
              <span className={`lora-status-dot ${loraState === 'idle' ? 'ready' : loraState}`} />
              {statusText}
            </div>
            <button
              className="lora-header-btn"
              onClick={refreshLibrary}
              title="Refresh library"
              aria-label="Refresh library"
            >
              {'\u21BB'}
            </button>
            <button
              className="lora-header-btn"
              onClick={selectRandomGame}
              title="Random Game"
              aria-label="Random game"
            >
              {'\uD83C\uDFB2'}
            </button>
            <button
              className="lora-header-btn"
              onClick={launchPegasus}
              title="Launch Big Box"
              aria-label="Launch Big Box"
            >
              <span className="lora-header-btn-glyph">LB</span>
            </button>
            <button
              className={`lora-header-btn ${chatOpen ? 'active' : ''}`}
              onClick={toggleChat}
              title="Chat with LoRa"
              aria-label="Toggle chat"
            >
              {'\uD83D\uDCAC'}
              {!chatOpen && <span className="lora-chat-badge">!</span>}
            </button>
            <div className="lora-brand-logo-wrap">
              <img src="/lora-avatar.jpeg" alt={chatProfileName} className="lora-brand-logo" />
            </div>
          </div>
        </div>

        {/* Content Body: Sidebar + Main */}
        <div className="lora-content-body">
          <div className="lora-icon-rail">
            <button type="button" className="lora-rail-btn" aria-label="Home">⌂</button>
            <button type="button" className="lora-rail-btn active" aria-label="Library">{'\uD83C\uDFAE'}</button>
            <button type="button" className={`lora-rail-btn ${chatOpen ? 'active' : ''}`} onClick={toggleChat} aria-label="Chat with LoRa">{'\uD83D\uDCAC'}</button>
            <div className="lora-rail-spacer" />
            <button type="button" className="lora-rail-btn power" onClick={launchPegasus} aria-label="Launch Big Box">LB</button>
          </div>
          {/* Category Sidebar */}
          <div className="lora-sidebar" ref={sidebarRef} tabIndex={-1}>
            <div className="lora-sidebar-title">Platforms</div>
            <button
              className={`lora-sidebar-item ${(genreFilter === 'All' && platformFilter === 'All') ? 'active' : ''}`}
              onClick={() => { setPlatformFilter('All'); setGenreFilter('All') }}
            >
              <span className="sidebar-icon">{'\uD83C\uDFAE'}</span>
              All Games
              <span className="sidebar-count">{totalGames}</span>
            </button>
            {(platforms || []).map(plat => (
              <button
                key={plat}
                className={`lora-sidebar-item ${platformFilter === plat ? 'active' : ''}`}
                onClick={() => setPlatformFilter(plat)}
              >
                <span className="sidebar-icon">{'\uD83D\uDCBF'}</span>
                {plat}
              </button>
            ))}
          </div>

          {/* Main Content Area */}
          <div className="lora-main">
            {/* Hero Section */}
            {selectedGame && (
              <div className="lora-hero">
                <div className="lora-hero-tag">
                  {selectedGame.genre || selectedGame.platform || 'Game'}
                </div>
                <h2 className="lora-hero-title">
                  {selectedGame.title.length > 20
                    ? <>{selectedGame.title.substring(0, Math.ceil(selectedGame.title.length / 2))} <span className="accent">{selectedGame.title.substring(Math.ceil(selectedGame.title.length / 2))}</span></>
                    : <>{selectedGame.title}</>
                  }
                </h2>
                <p className="lora-hero-meta">{heroMeta || 'Featured game ready to launch'}</p>
                <div className="lora-hero-actions">
                  <button
                    className="lora-btn-launch"
                    onClick={() => launchGame(selectedGame)}
                    disabled={!canLaunchHere(selectedGame) || isLockActive}
                    aria-label={`Launch ${selectedGame.title}`}
                  >
                    {'\u25B6'} Launch Game
                  </button>
                  <button
                    className="lora-btn-details"
                    onClick={() => {
                      addMessage(`Tell me about ${selectedGame.title}`, 'user')
                      setChatOpen(true)
                      sendMessageWithText(`Tell me about ${selectedGame.title} on ${selectedGame.platform}`)
                    }}
                  >
                    Game Details
                  </button>
                </div>
              </div>
            )}

            {/* Box Art Grid */}
            <div className="lora-carousel-section">
              <div className="lora-carousel-topline">
                <div>
                  <p className="lora-carousel-label">Library Games</p>
                  <p className="lora-carousel-meta">Showing {currentRangeStart}-{currentRangeEnd} of {totalGames} games</p>
                </div>
                <div className="lora-filter-controls">
                  <select value={platformFilter} onChange={handlePlatformFilterChange} aria-label="Filter by platform">
                    {platformsForFilter.map((platform) => (
                      <option key={platform} value={platform}>{platform}</option>
                    ))}
                  </select>
                  <select value={genreFilter} onChange={handleGenreFilterChange} aria-label="Filter by genre">
                    {genresForFilter.map((genre) => (
                      <option key={genre} value={genre}>{genre}</option>
                    ))}
                  </select>
                  <select value={yearFilter} onChange={handleYearFilterChange} aria-label="Filter by decade">
                    {decades.map((decade) => (
                      <option key={decade} value={decade}>{decade}</option>
                    ))}
                  </select>
                  <select value={sortBy} onChange={handleSortByChange} aria-label="Sort games">
                    <option value="title">Title A-Z</option>
                    <option value="year">Year Newest</option>
                    <option value="lastPlayed">Recently Played</option>
                  </select>
                </div>
              </div>
              <div className="lora-carousel">
                {libraryCards.map((game, idx) => (
                  <button
                    type="button"
                    key={game.id}
                    className={`lora-carousel-card ${idx === selectedGameIndex ? 'selected' : ''}`}
                    onClick={() => {
                      setSelectedGameIndex(idx)
                      blinkySelection.gameSelected(game.title, game.platform || 'MAME')
                    }}
                    onDoubleClick={() => {
                      setSelectedGameIndex(idx)
                      blinkySelection.gameSelected(game.title, game.platform || 'MAME')
                      launchGame(game)
                    }}
                    onMouseEnter={() => blinkySelection.gameSelected(game.title, game.platform || 'MAME')}
                    title={`Select ${game.title}. Double-click to launch.`}
                  >
                    <img
                      src={buildGameImageUrl(game, 'card')}
                      alt={game.title}
                      onError={(e) => { e.target.style.display = 'none' }}
                    />
                    <div className="card-fallback" aria-hidden="true">
                      <span className="card-fallback-initial">{game.title?.charAt(0) || '?'}</span>
                      <span className="card-fallback-label">No artwork</span>
                    </div>
                    <div className="card-overlay" />
                    <div className="card-title">
                      <strong>{game.title}</strong>
                      <span>{[game.platform, game.year].filter(Boolean).join(' • ')}</span>
                    </div>
                  </button>
                ))}
                {libraryCards.length === 0 && (
                  <div className="lora-carousel-placeholder">
                    <span className="card-icon">{'\uD83C\uDFAE'}</span>
                    No games match your filters
                  </div>
                )}
              </div>
              {totalPages > 1 && (
                <div className="lora-pagination">
                  <button type="button" onClick={goToPreviousPage} disabled={currentPage === 1}>Previous</button>
                  <span>Page {currentPage} of {totalPages}</span>
                  <button type="button" onClick={() => goToNextPage(totalPages)} disabled={currentPage === totalPages}>Next</button>
                </div>
              )}
            </div>

            {/* Stats Strip */}
            <div className={`lora-stats-strip ${subPanelExpanded ? '' : 'collapsed'}`}>
              <div className="lora-subpanel-header">
                <div className="lora-subpanel-tabs">
                  <button type="button" className={activeTab === 'recent' ? 'active' : ''} onClick={setTabRecent}>Recent</button>
                  <button type="button" className={activeTab === 'stats' ? 'active' : ''} onClick={setTabStats}>Quick Stats</button>
                </div>
                <button type="button" className="lora-subpanel-toggle" onClick={toggleSubPanel}>
                  {subPanelExpanded ? 'Collapse' : `Open ${subpanelModeLabel}`}
                </button>
              </div>

              {subPanelExpanded && activeTab === 'stats' && (
                <>
                  <div className="lora-stat-card">
                    <div className="lora-stat-header">
                      <span className="lora-stat-icon">{'\uD83C\uDFAE'}</span>
                      <span className="lora-stat-label">Total Games</span>
                    </div>
                    <div className="lora-stat-value">
                      {displayStats.total_games || displayStats.totalGames || totalGames}
                      <span className="lora-stat-suffix">GAMES</span>
                    </div>
                  </div>
                  <div className="lora-stat-card">
                    <div className="lora-stat-header">
                      <span className="lora-stat-icon">{'\uD83D\uDD79\uFE0F'}</span>
                      <span className="lora-stat-label">Platforms</span>
                    </div>
                    <div className="lora-stat-value">
                      {displayStats.platforms_count || displayStats.platforms || 0}
                      <span className="lora-stat-suffix">SYSTEMS</span>
                    </div>
                  </div>
                  <div className="lora-stat-card">
                    <div className="lora-stat-header">
                      <span className="lora-stat-icon">{'\uD83C\uDFAF'}</span>
                      <span className="lora-stat-label">Genres</span>
                    </div>
                    <div className="lora-stat-value">
                      {displayStats.genres_count || 0}
                      <span className="lora-stat-suffix">TYPES</span>
                    </div>
                  </div>
                </>
              )}

              {subPanelExpanded && activeTab === 'recent' && (
                <>
                  <div className="lora-stat-card recent-card">
                    <div className="lora-stat-header">
                      <span className="lora-stat-icon">{'\u2726'}</span>
                      <span className="lora-stat-label">Selected Game</span>
                    </div>
                    <div className="lora-recent-value">{selectedGame?.title || 'No selection'}</div>
                    <p className="lora-recent-text">{selectedGame ? `${heroMeta} • ${formatRelativeTime(selectedGame.lastPlayed)}` : 'Choose a game from the library shelf to focus it here.'}</p>
                  </div>
                  <div className="lora-stat-card recent-card">
                    <div className="lora-stat-header">
                      <span className="lora-stat-icon">{'\u21BB'}</span>
                      <span className="lora-stat-label">Library State</span>
                    </div>
                    <div className="lora-recent-value">{cacheIsStale ? 'Refresh Recommended' : 'Synced'}</div>
                    <p className="lora-recent-text">{cacheLastUpdated ? `Last updated ${formatRelativeTime(cacheLastUpdated)}` : 'No cache timestamp available.'}</p>
                  </div>
                  <div className="lora-stat-card recent-card">
                    <div className="lora-stat-header">
                      <span className="lora-stat-icon">{'\u2699'}</span>
                      <span className="lora-stat-label">Launch Status</span>
                    </div>
                    <div className="lora-recent-value">{pluginAvailable ? 'Plugin Online' : 'Plugin Offline'}</div>
                    <p className="lora-recent-text">{directLaunchText}</p>
                  </div>
                </>
              )}

              {subPanelExpanded && (
                <div className="lora-subpanel-footer">
                  <label className="lora-toggle-row">
                    <input
                      type="checkbox"
                      checked={allowRetroArch}
                      onChange={(e) => {
                        const next = e.target.checked
                        setAllowRetroArch(next)
                        try {
                          window.localStorage.setItem(RETROARCH_ALLOWED_STORAGE_KEY, String(next))
                        } catch {
                          // ignore persistence failures
                        }
                      }}
                    />
                    <span>Allow RetroArch fallback</span>
                  </label>
                  <span className={`lora-status-chip ${cacheIsStale ? 'is-stale' : 'is-fresh'}`}>{cacheIsStale ? 'Cache Stale' : 'Cache Fresh'}</span>
                  <span className="lora-status-chip">{directLaunchText}</span>
                </div>
              )}
            </div>
          </div>
        </div>
      </div>

      {chatOpen && <button type="button" className="lora-chat-scrim" onClick={closeChat} aria-label="Close chat overlay" />}

      {/* LoRa Chat Panel (Fixed Right) */}
      <div className={`lora-chat-panel ${chatOpen ? '' : 'hidden'}`} role="dialog" aria-label="Chat with LoRa">
        <div className="lora-chat-header">
          <div className="lora-chat-title">
            <div className="pulse-dot" />
            <span>LoRa AI</span>
          </div>
          <button className="lora-chat-close" onClick={closeChat} aria-label="Close chat">{'\u00D7'}</button>
        </div>
        <div className="lora-chat-profile">
          <label htmlFor="launchbox-lora-profile">Profile</label>
          <select id="launchbox-lora-profile" value={activeProfile} onChange={handleProfileChange}>
            {profileOptions.map((option) => (
              <option key={option.value} value={option.value}>{option.label}</option>
            ))}
          </select>
        </div>
        <div className="lora-chat-messages" ref={chatMessagesRef}>
          {messages.map((msg, idx) => (
            <div key={idx} className={`lora-chat-msg ${msg.role}`}>
              <div className="bubble">{msg.text}</div>
              <span className="msg-meta">
                {msg.role === 'assistant' ? 'LoRa' : chatProfileName}
              </span>
            </div>
          ))}
          {isChatLoading && (
            <div className="lora-chat-msg assistant lora-chat-typing">
              <div className="bubble">
                <div className="typing-dots">
                  <span /><span /><span />
                </div>
              </div>
            </div>
          )}
        </div>
        {isRecording && (
          <div className="lora-voice-viz">
            <div className="lora-voice-bars">
              {voiceBars.map((_, i) => (
                <div key={i} className="lora-voice-bar" style={memoizedStyles.voiceBarDelays[i]} />
              ))}
            </div>
            <p className="lora-voice-status">Listening...</p>
          </div>
        )}
        <div className="lora-chat-input-area">
          <button
            className={`lora-chat-mic-btn ${isRecording ? 'recording' : ''}`}
            onClick={toggleMic}
            title={isRecording ? 'Stop voice input' : 'Start voice input'}
            aria-label={isRecording ? 'Stop voice input' : 'Start voice input'}
          >
            {isRecording ? (
              <span style={{ fontSize: '18px' }}>{'\u23F9\uFE0F'}</span>
            ) : (
              <img src="/lora-mic.png" alt="Microphone" style={{ width: '22px', height: '22px' }} />
            )}
          </button>
          <input
            type="text"
            className="lora-chat-input"
            value={input}
            onChange={handleInputChange}
            onKeyPress={handleInputKeyPress}
            placeholder="Ask LoRa anything..."
            aria-label="Chat with LoRa"
            disabled={isChatLoading}
          />
          <button
            className="lora-chat-send"
            onClick={sendMessage}
            disabled={isChatLoading || !input.trim()}
            aria-label="Send message"
          >
            {'\u27A4'}
          </button>
        </div>
      </div>

      {/* Shader Preview Modal */}
      {shaderModal.open && (
        <div role="dialog" aria-modal="true" aria-label="Shader preview" className="shader-preview-overlay">
          <div className="shader-preview-card">
            <h3 className="shader-preview-title">Shader Configuration for {shaderModal.gameId}</h3>
            <div className="shader-preview-details">
              <div className="shader-detail-item">
                <span className="shader-detail-label">Preset:</span>
                {shaderModal.newConfig?.shader || 'None'}
              </div>
              {shaderModal.newConfig?.params && Object.entries(shaderModal.newConfig.params).map(([k, v]) => (
                <div key={k} className="shader-detail-item">
                  <span className="shader-detail-label">{k}:</span>
                  {String(v)}
                </div>
              ))}
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
                className="shader-btn-apply"
                onClick={applyShaderChange}
                disabled={pendingShaderApply}
              >
                {pendingShaderApply ? 'Applying...' : 'Apply'}
              </button>
              <button className="shader-btn-cancel" onClick={cancelShaderPreview}>
                Cancel
              </button>
              {shaderModal.oldConfig && shaderModal.oldConfig.shader !== 'none' && (
                <button className="shader-btn-remove" onClick={removeShaderBinding}>
                  Remove Shader
                </button>
              )}
            </div>
          </div>
        </div>
      )}

      {/* Floating Bottom Input */}
      {!chatOpen && (
        <div className="lora-floating-input">
          <div className="lora-floating-input-inner">
            <div className="lora-floating-sparkle">{'\u2728'}</div>
            <input
              type="text"
              className="lora-floating-field"
              value={input}
              onChange={handleInputChange}
              onKeyPress={handleInputKeyPress}
              placeholder="ASK LORA ANYTHING..."
              disabled={isChatLoading}
            />
            <button
              className="lora-floating-send"
              onClick={() => {
                setChatOpen(true)
                sendMessage()
              }}
              disabled={isChatLoading || !input.trim()}
              aria-label="Send message"
            >
              {'\u27A4'}
            </button>
          </div>
        </div>
      )}

      {/* Toast */}
      {toastMsg && (
        <div className="lora-toast">{toastMsg}</div>
      )}
    </div>
  )
}

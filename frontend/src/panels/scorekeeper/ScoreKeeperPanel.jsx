import React, { useState, useEffect, useCallback, useRef, useMemo } from 'react'
import { useAIAction } from '../_kit'
import { getLeaderboard, getByGame, applyTournamentCreate, previewScoreSubmit, applyScoreSubmit, previewTournamentReport, applyTournamentReport, getTournament, listTournaments, submitScoreViaPlugin, resolveGameByTitle, undoScorekeeper, restoreScorekeeper } from '../../services/scorekeeperClient'
import { useLocation } from 'react-router-dom'
import { getConsent, getProfile } from '../../services/profileClient'
import { useProfileContext } from '../../context/ProfileContext'
import { subscribeToScores } from '../../services/supabaseClient'
import { speakAsSam, stopSpeaking, isSpeaking } from '../../services/ttsClient'
import './scorekeeper.css'

// Constants
const PLAYER_COUNTS = [4, 8, 16, 32]

const ROUND_KEY_MAP = {
  4: ['semifinals', 'finals'],
  8: ['quarterfinals', 'semifinals', 'finals'],
  16: ['round1', 'quarterfinals', 'semifinals', 'finals'],
  32: ['round1', 'round2', 'quarterfinals', 'semifinals', 'finals']
}

function formatScoreValue(value, fallback = '�') {
  if (value === '' || value === null || value === undefined) return fallback
  const n = typeof value === 'number' ? value : Number(value)
  return Number.isFinite(n) ? n.toLocaleString() : fallback
}

function roundKeyFor(playerCount, roundNumber) {
  const keys = ROUND_KEY_MAP[playerCount]
  if (!keys) return `round${roundNumber}`
  return keys[roundNumber - 1] || `round${roundNumber}`
}

function createPlayerObject(name, fallbackId) {
  if (!name || name === 'TBD') {
    return { id: `${fallbackId}-tbd`, name: 'TBD' }
  }
  return { id: `${fallbackId}-${encodeURIComponent(name)}`, name }
}

function inferPlayerCount(data) {
  if (data?.player_count && PLAYER_COUNTS.includes(data.player_count)) {
    return data.player_count
  }
  const matches = Array.isArray(data?.matches) ? data.matches.length : 0
  if (matches > 0) {
    const candidate = matches + 1
    if (PLAYER_COUNTS.includes(candidate)) return candidate
    const pow = Math.pow(2, Math.ceil(Math.log2(candidate)))
    if (PLAYER_COUNTS.includes(pow)) return pow
  }
  return 8
}

function deriveCurrentRound(matches, playerCount) {
  const keys = ROUND_KEY_MAP[playerCount] || []
  if (!Array.isArray(matches) || matches.length === 0) {
    return keys[0] || 'round1'
  }

  const roundProgress = new Map()
  matches.forEach((match) => {
    const key = roundKeyFor(playerCount, match.round || 1)
    if (!roundProgress.has(key)) {
      roundProgress.set(key, { total: 0, completed: 0 })
    }
    const info = roundProgress.get(key)
    info.total += 1
    if (match.status === 'completed' || (match.winner && match.winner !== 'TBD')) {
      info.completed += 1
    }
  })

  for (const key of keys) {
    const info = roundProgress.get(key)
    if (!info) return key
    if (info.completed < info.total) return key
  }

  return keys[keys.length - 1] || 'finals'
}

function extractPlayersFromMatches(matches, playerCount) {
  const firstRound = Array.isArray(matches)
    ? matches.filter(match => (match.round || 1) === 1).sort((a, b) => (a.match_index ?? 0) - (b.match_index ?? 0))
    : []
  const names = []

  firstRound.forEach(match => {
    const p1 = match.player1 && match.player1 !== 'TBD' ? match.player1 : `Player ${names.length + 1}`
    const p2 = match.player2 && match.player2 !== 'TBD' ? match.player2 : `Player ${names.length + 2}`
    names.push(p1)
    names.push(p2)
  })

  while (names.length < playerCount) {
    names.push(`Player ${names.length + 1}`)
  }

  return names.slice(0, playerCount)
}

function buildBracketFromMatches(matches, playerCount) {
  if (!Array.isArray(matches) || matches.length === 0) return null

  const grouped = {}
  matches.forEach(match => {
    const key = roundKeyFor(playerCount, match.round || 1)
    if (!grouped[key]) grouped[key] = []
    grouped[key].push(match)
  })

  Object.keys(grouped).forEach(key => {
    grouped[key].sort((a, b) => (a.match_index ?? 0) - (b.match_index ?? 0))
  })

  const bracket = {}
  Object.entries(grouped).forEach(([key, list]) => {
    bracket[key] = list.map(match => {
      const baseId = `${key}-${match.match_index ?? 0}`
      const player1 = createPlayerObject(match.player1, `${baseId}-p1`)
      const player2 = createPlayerObject(match.player2, `${baseId}-p2`)
      let winner = null
      if (match.winner) {
        if (player1.name === match.winner) {
          winner = player1
        } else if (player2.name === match.winner) {
          winner = player2
        } else {
          winner = createPlayerObject(match.winner, `${baseId}-winner`)
        }
      }
      return {
        id: `${baseId}`,
        matchIndex: match.match_index ?? 0,
        player1,
        player2,
        winner,
        status: match.status || (winner ? 'completed' : 'pending')
      }
    })
  })

  return bracket
}

function buildLocalBracket(playerCount, names) {
  const players = names.slice(0, playerCount).map((name, index) => ({
    id: index + 1,
    name: name || `Player ${index + 1}`,
    active: true
  }))

  let bracket = {}

  if (playerCount === 4) {
    bracket = {
      semifinals: [
        { id: 's1', player1: players[0], player2: players[1], winner: null },
        { id: 's2', player1: players[2], player2: players[3], winner: null }
      ],
      finals: [
        { id: 'f1', player1: { name: 'TBD' }, player2: { name: 'TBD' }, winner: null }
      ]
    }
  } else if (playerCount === 8) {
    bracket = {
      quarterfinals: [
        { id: 'q1', player1: players[0], player2: players[1], winner: null },
        { id: 'q2', player1: players[2], player2: players[3], winner: null },
        { id: 'q3', player1: players[4], player2: players[5], winner: null },
        { id: 'q4', player1: players[6], player2: players[7], winner: null }
      ],
      semifinals: [
        { id: 's1', player1: { name: 'TBD' }, player2: { name: 'TBD' }, winner: null },
        { id: 's2', player1: { name: 'TBD' }, player2: { name: 'TBD' }, winner: null }
      ],
      finals: [
        { id: 'f1', player1: { name: 'TBD' }, player2: { name: 'TBD' }, winner: null }
      ]
    }
  } else if (playerCount === 16) {
    const round1 = []
    for (let i = 0; i < 16; i += 2) {
      round1.push({
        id: `r1-${Math.floor(i / 2)}`,
        player1: players[i],
        player2: players[i + 1],
        winner: null
      })
    }

    bracket = {
      round1: round1,
      quarterfinals: Array.from({ length: 4 }, (_, i) => ({
        id: `q${i + 1}`,
        player1: { name: 'TBD' },
        player2: { name: 'TBD' },
        winner: null
      })),
      semifinals: [
        { id: 's1', player1: { name: 'TBD' }, player2: { name: 'TBD' }, winner: null },
        { id: 's2', player1: { name: 'TBD' }, player2: { name: 'TBD' }, winner: null }
      ],
      finals: [
        { id: 'f1', player1: { name: 'TBD' }, player2: { name: 'TBD' }, winner: null }
      ]
    }
  } else if (playerCount === 32) {
    const round1 = []
    for (let i = 0; i < 32; i += 2) {
      round1.push({
        id: `r1-${Math.floor(i / 2)}`,
        player1: players[i],
        player2: players[i + 1],
        winner: null
      })
    }

    bracket = {
      round1: round1,
      round2: Array.from({ length: 8 }, (_, i) => ({
        id: `r2-${i}`,
        player1: { name: 'TBD' },
        player2: { name: 'TBD' },
        winner: null
      })),
      quarterfinals: Array.from({ length: 4 }, (_, i) => ({
        id: `q${i + 1}`,
        player1: { name: 'TBD' },
        player2: { name: 'TBD' },
        winner: null
      })),
      semifinals: [
        { id: 's1', player1: { name: 'TBD' }, player2: { name: 'TBD' }, winner: null },
        { id: 's2', player1: { name: 'TBD' }, player2: { name: 'TBD' }, winner: null }
      ],
      finals: [
        { id: 'f1', player1: { name: 'TBD' }, player2: { name: 'TBD' }, winner: null }
      ]
    }
  }

  return bracket
}

// Memoized BracketMatch component
const BracketMatch = React.memo(({ match, roundType, onPlayerClick }) => (
  <div className="bracket-match">
    <div
      className={`player ${match.winner?.id === match.player1.id ? 'winner' : ''}`}
      onClick={() => match.player1.id && onPlayerClick(match.id, match.player1.id, roundType)}
    >
      {match.player1.name}
    </div>
    <div
      className={`player ${match.winner?.id === match.player2.id ? 'winner' : ''}`}
      onClick={() => match.player2.id && onPlayerClick(match.id, match.player2.id, roundType)}
    >
      {match.player2.name}
    </div>
  </div>
))

export default function ScoreKeeperPanel() {
  const location = useLocation()
  const searchParams = new URLSearchParams(location.search)
  const bigBoard = searchParams.get('display') === 'bigboard'
  const { profile: sharedProfile } = useProfileContext()
  // Tournament State Management
  const [selectedPlayerCount, setSelectedPlayerCount] = useState(8)
  const [playerNames, setPlayerNames] = useState({
    4: ['Player 1', 'Player 2', 'Player 3', 'Player 4'],
    8: ['Mom', 'Dad', 'Sarah', 'Mike', 'Tommy', 'Lisa', 'Alex', 'Jordan'],
    16: Array.from({ length: 16 }, (_, i) => `Player ${i + 1}`),
    32: Array.from({ length: 32 }, (_, i) => `Player ${i + 1}`)
  })

  const [tournament, setTournament] = useState({
    id: null,
    name: `Tournament (8 Players)`,
    status: 'active',
    players: ['Mom', 'Dad', 'Sarah', 'Mike', 'Tommy', 'Lisa', 'Alex', 'Jordan'],
    bracket: null,
    currentRound: 'quarterfinals',
    winner: null,
    createdAt: null
  })

  const [chatMessages, setChatMessages] = useState([
    {
      id: 1,
      type: 'assistant',
      content: "ScoreKeeper Sam here! I'm your Tournament Commander with AI-powered bracket management and Elo/Glicko-2 ratings. What would you like to create?",
      timestamp: new Date()
    }
  ])

  const [inputMessage, setInputMessage] = useState('')
  const [isProcessing, setIsProcessing] = useState(false)
  const [aiStatus, setAiStatus] = useState('AI Ready')
  const [chatOpen, setChatOpen] = useState(false)
  const [activeView, setActiveView] = useState('highscores') // 'highscores' or 'tournament'

  // Leaderboard state
  const [leaderboardData, setLeaderboardData] = useState([])
  const [scoresCached, setScoresCached] = useState(false)
  const [pluginPaused, setPluginPaused] = useState(false)
  const [gameFilter, setGameFilter] = useState('')

  // Per-game summary
  const [byGame, setByGame] = useState(null)
  const [paused, setPaused] = useState(false)
  const [consent, setConsent] = useState({ accepted: false, scopes: [] })
  const { profile: profileData } = useProfileContext()
  const [useProfileForScore, setUseProfileForScore] = useState(false)

  // Reactive profile sync: auto-enable profile for scores when broadcast arrives
  useEffect(() => {
    if (profileData?.displayName) {
      setUseProfileForScore(true)
      setScoreForm(prev => ({ ...prev, player: prev.player || profileData.displayName }))
    }
  }, [profileData?.displayName])
  const [tournamentList, setTournamentList] = useState([])

  // Score submission state
  const [scoreForm, setScoreForm] = useState({ game: '', player: '', score: '' })
  const [scorePreview, setScorePreview] = useState(null)

  // Undo state for tracking last backup
  const [lastBackup, setLastBackup] = useState(null)

  // Voice / Speech Recognition state
  const [isListening, setIsListening] = useState(false)
  const [isSamSpeaking, setIsSamSpeaking] = useState(false)
  const recognitionRef = useRef(null)

  // Refs
  const chatMessagesRef = useRef(null)

  // AI integration using Panel Kit
  const { executeAction, isLoading } = useAIAction('scorekeeper')
  const initialBracketInit = useRef(false)
  const suppressAutoBracket = useRef(false)

  const addChatMessage = useCallback((type, content) => {
    setChatMessages(prev => [...prev, {
      id: Date.now(),
      type,
      content,
      timestamp: new Date()
    }])
  }, [])

  const generateBracket = useCallback((playerCount, names) => buildLocalBracket(playerCount, names), [])

  const adaptTournamentFromBackend = useCallback((data) => {
    if (!data || !Array.isArray(data.matches)) return null
    const playerCount = inferPlayerCount(data)
    const players = extractPlayersFromMatches(data.matches, playerCount)
    const bracket = buildBracketFromMatches(data.matches, playerCount) || buildLocalBracket(playerCount, players)
    const currentRound = deriveCurrentRound(data.matches, playerCount)

    const finalKey = ROUND_KEY_MAP[playerCount] ? ROUND_KEY_MAP[playerCount][ROUND_KEY_MAP[playerCount].length - 1] : 'finals'
    const finalMatch = Array.isArray(bracket?.[finalKey]) ? bracket[finalKey][0] : null
    const winnerObject = finalMatch?.winner || (data.winner ? createPlayerObject(data.winner, 'winner') : null)

    return {
      playerCount,
      playerNames: players,
      tournamentState: {
        id: data.id,
        name: data.name || `Tournament (${playerCount} Players)`,
        status: data.status || 'active',
        players,
        bracket,
        currentRound,
        winner: winnerObject,
        createdAt: data.created_at ? new Date(data.created_at) : null,
        game: data.game || 'General'
      }
    }
  }, [])

  const applyBackendTournament = useCallback((serverData, options = {}) => {
    const adapted = adaptTournamentFromBackend(serverData)
    if (!adapted) return false
    suppressAutoBracket.current = true
    initialBracketInit.current = true
    setTournament({
      ...adapted.tournamentState
    })
    setPlayerNames(prev => ({
      ...prev,
      [adapted.playerCount]: adapted.playerNames
    }))
    setSelectedPlayerCount(adapted.playerCount)
    setTournamentList(prev => Array.isArray(prev)
      ? prev.map(item => item.id === serverData.id
        ? {
          ...item,
          status: adapted.tournamentState.status,
          player_count: adapted.playerCount,
          created_at: serverData.created_at ?? item.created_at
        }
        : item)
      : prev
    )
    setTimeout(() => {
      suppressAutoBracket.current = false
    }, 0)
    if (!options?.silent) {
      addChatMessage('system', `Resumed tournament: ${adapted.tournamentState.name}`)
    }
    return true
  }, [adaptTournamentFromBackend, addChatMessage])

  // Auto-scroll chat to bottom
  useEffect(() => {
    if (chatMessagesRef.current) {
      chatMessagesRef.current.scrollTop = chatMessagesRef.current.scrollHeight
    }
  }, [chatMessages])

  // Load leaderboard on mount (read-only via gateway)
  useEffect(() => {
    (async () => {
      try {
        const result = await getLeaderboard({ limit: 10 })
        setLeaderboardData(result.scores || [])
        setScoresCached(!!result.cached)
        setPluginPaused(!!result.cached)
        // Auto-load per-game summary for the first game if available
        const first = (result.scores || [])[0]
        if (first && (first.gameId || first.game_id)) {
          const gid = first.gameId || first.game_id
          try {
            const details = await getByGame({ gameId: gid })
            setPaused(Boolean(details.cached))
            setByGame(details)
          } catch {
            setPaused(true)
            setByGame(null)
          }
        }
        // Load consent & profile for prefill
        try {
          const c = await getConsent()
          setConsent(c?.consent || { accepted: false, scopes: [] })
        } catch { /* ignore */ }
        // Legacy profile fetch as fallback (reactive sync via useEffect below)
        try {
          const p = await getProfile()
          const prof = p?.profile || null
          if (prof && prof.displayName) {
            setProfileData(prof)
            setUseProfileForScore(true)
            setScoreForm(prev => ({ ...prev, player: prev.player || prof.displayName }))
          }
        } catch { /* ignore */ }
        // List tournaments (for Resume Last)
        try {
          const lt = await listTournaments()
          const tournaments = Array.isArray(lt?.tournaments) ? lt.tournaments : []
          setTournamentList(tournaments)

          // Auto-resume most recent active tournament
          if (tournaments.length > 0) {
            const mostRecent = tournaments[0] // Already sorted newest first
            if (mostRecent.status === 'active') {
              try {
                const tournamentData = await getTournament(mostRecent.id)
                applyBackendTournament(tournamentData)
              } catch (err) {
                console.error('[ScoreKeeper] Failed to resume tournament:', err)
              }
            }
          }
        } catch { /* ignore */ }
      } catch (err) {
        // If plugin offline (503), show paused banner but do not block UI
        setPluginPaused(true)
      }
    })()
  }, [])

  // Reactive profile sync: when Vicky or another panel updates the profile, Sam knows immediately
  useEffect(() => {
    if (sharedProfile?.displayName) {
      setProfileData(prev => ({
        ...prev,
        displayName: sharedProfile.displayName,
        initials: sharedProfile.initials || '',
        userId: sharedProfile.userId || 'guest'
      }))
      setUseProfileForScore(true)
      setScoreForm(prev => ({ ...prev, player: sharedProfile.displayName }))
      console.log('[ScoreKeeper] Profile synced from context:', sharedProfile.displayName)
    }
  }, [sharedProfile])

  async function fetchByGame(gameId) {
    try {
      const j = await getByGame({ gameId })
      setPaused(Boolean(j.cached))
      setByGame(j)
    } catch {
      setPaused(true)
      setByGame(null)
    }
  }

  // WebSocket subscription for live score updates
  useEffect(() => {
    const isDev = window.location.port === '5173'
    const proto = window.location.protocol === 'https:' ? 'wss' : 'ws'
    const wsUrl = isDev
      ? 'ws://localhost:8787/scorekeeper/ws'
      : `${proto}://${window.location.host}/scorekeeper/ws`

    let ws
    try {
      ws = new WebSocket(wsUrl)
    } catch (err) {
      console.warn('[ScoreKeeper] WebSocket unavailable:', err)
    }

    const refreshLeaderboard = async () => {
      try {
        const result = await getLeaderboard({ limit: 10 })
        setLeaderboardData(result.scores || [])
        setScoresCached(!!result.cached)
        setPluginPaused(!!result.cached)
      } catch {
        // Ignore refresh errors
      }
    }

    if (ws) {
      ws.onmessage = (ev) => {
        try {
          const msg = JSON.parse(ev.data)
          if (msg?.type === 'score_record' || msg?.type === 'score_updated') {
            refreshLeaderboard()
          }
        } catch (err) {
          console.warn('[ScoreKeeper] WebSocket message parse failed:', err)
        }
      }
    }

    // Fallback: poll every 10 seconds
    const intervalId = setInterval(refreshLeaderboard, 10000)

    return () => {
      clearInterval(intervalId)
      if (ws) {
        try {
          ws.close()
        } catch { /* ignore */ }
      }
    }
  }, [])

  // Supabase Realtime subscription for cloud score inserts
  useEffect(() => {
    const channel = subscribeToScores((newRow) => {
      // When a new score lands in Supabase, refresh the local leaderboard
      (async () => {
        try {
          const result = await getLeaderboard({ limit: 10 })
          setLeaderboardData(result.scores || [])
          setScoresCached(!!result.cached)
          setPluginPaused(!!result.cached)
        } catch { /* ignore */ }
      })()
    })

    return () => {
      if (channel) {
        try { channel.unsubscribe() } catch { /* ignore */ }
      }
    }
  }, [])

  // Initialize Web Speech API recognition
  useEffect(() => {
    // Listen for external view-switch events (from persona card buttons)
    const handleViewSwitch = (e) => {
      if (e.detail === 'tournament') setActiveView('tournament')
      else if (e.detail === 'highscores') setActiveView('highscores')
    }
    window.addEventListener('sam-view', handleViewSwitch)

    const SpeechRecognition = window.SpeechRecognition || window.webkitSpeechRecognition
    if (!SpeechRecognition) return

    const recognition = new SpeechRecognition()
    recognition.continuous = false
    recognition.interimResults = false
    recognition.lang = 'en-US'

    recognition.onresult = (event) => {
      const transcript = event.results[0]?.[0]?.transcript
      if (transcript) {
        setInputMessage(transcript)
        // Auto-send after a short delay so user sees the transcript
        setTimeout(() => {
          setInputMessage(prev => {
            if (prev === transcript) {
              // Trigger send via ref callback
              document.querySelector('.panel-chat-sidebar .execute-btn')?.click()
            }
            return prev
          })
        }, 400)
      }
    }

    recognition.onend = () => setIsListening(false)
    recognition.onerror = () => setIsListening(false)

    recognitionRef.current = recognition

    return () => {
      window.removeEventListener('sam-view', handleViewSwitch)
      try { recognition.abort() } catch { /* ignore */ }
    }
  }, [])

  const toggleListening = useCallback(() => {
    const recognition = recognitionRef.current
    if (!recognition) return

    if (isListening) {
      recognition.abort()
      setIsListening(false)
    } else {
      try {
        recognition.start()
        setIsListening(true)
      } catch { /* already started */ }
    }
  }, [isListening])

  // Initialize bracket on component mount
  useEffect(() => {
    if (suppressAutoBracket.current) return
    if (initialBracketInit.current) return
    if (tournament.id) return
    initialBracketInit.current = true
    const bracket = generateBracket(selectedPlayerCount, playerNames[selectedPlayerCount])
    setTournament(prev => ({
      ...prev,
      players: playerNames[selectedPlayerCount].slice(0, selectedPlayerCount),
      bracket,
      status: prev.status === 'setup' ? 'setup' : 'active',
      currentRound: roundKeyFor(selectedPlayerCount, 1),
      winner: null
    }))
  }, [generateBracket, playerNames, selectedPlayerCount, tournament.id])

  // Update bracket when player count changes
  useEffect(() => {
    const bracket = generateBracket(selectedPlayerCount, playerNames[selectedPlayerCount])
    setTournament(prev => {
      if (suppressAutoBracket.current) return prev
      if (prev.id) return prev
      return {
        ...prev,
        name: `Tournament (${selectedPlayerCount} Players)`,
        players: playerNames[selectedPlayerCount].slice(0, selectedPlayerCount),
        bracket,
        status: 'active',
        winner: null,
        currentRound: roundKeyFor(selectedPlayerCount, 1)
      }
    })
  }, [selectedPlayerCount, generateBracket, playerNames])

  // Helper: map UI bracket location to backend match_index ordering
  const computeMatchIndex = useCallback((roundType, matchLocalIndex) => {
    // Offsets per player count (single elimination)
    if (selectedPlayerCount === 4) {
      if (roundType === 'semifinals') return matchLocalIndex // 0..1
      if (roundType === 'finals') return 2
    }
    if (selectedPlayerCount === 8) {
      if (roundType === 'quarterfinals') return matchLocalIndex // 0..3
      if (roundType === 'semifinals') return 4 + matchLocalIndex // 4..5
      if (roundType === 'finals') return 6
    }
    if (selectedPlayerCount === 16) {
      if (roundType === 'round1') return matchLocalIndex // 0..7
      if (roundType === 'quarterfinals') return 8 + matchLocalIndex // 8..11
      if (roundType === 'semifinals') return 12 + matchLocalIndex // 12..13
      if (roundType === 'finals') return 14
    }
    if (selectedPlayerCount === 32) {
      if (roundType === 'round1') return matchLocalIndex // 0..15
      if (roundType === 'round2') return 16 + matchLocalIndex // 16..23
      if (roundType === 'quarterfinals') return 24 + matchLocalIndex // 24..27
      if (roundType === 'semifinals') return 28 + matchLocalIndex // 28..29
      if (roundType === 'finals') return 30
    }
    return null
  }, [selectedPlayerCount])

  const advancePlayer = useCallback((matchId, playerId, roundType) => {
    setTournament(prev => {
      const newTournament = { ...prev }
      const bracket = { ...newTournament.bracket }

      let match, winner
      if (roundType === 'round1') {
        match = bracket.round1.find(m => m.id === matchId)
        winner = playerId === match.player1.id ? match.player1 : match.player2
        match.winner = winner

        const matchIndex = bracket.round1.findIndex(m => m.id === matchId)
        if (selectedPlayerCount === 16) {
          const nextMatchIndex = Math.floor(matchIndex / 2)
          const position = matchIndex % 2 === 0 ? 'player1' : 'player2'
          bracket.quarterfinals[nextMatchIndex][position] = winner
        } else if (selectedPlayerCount === 32) {
          const nextMatchIndex = Math.floor(matchIndex / 2)
          const position = matchIndex % 2 === 0 ? 'player1' : 'player2'
          bracket.round2[nextMatchIndex][position] = winner
        }

      } else if (roundType === 'round2') {
        match = bracket.round2.find(m => m.id === matchId)
        winner = playerId === match.player1.id ? match.player1 : match.player2
        match.winner = winner

        const matchIndex = bracket.round2.findIndex(m => m.id === matchId)
        const nextMatchIndex = Math.floor(matchIndex / 2)
        const position = matchIndex % 2 === 0 ? 'player1' : 'player2'
        bracket.quarterfinals[nextMatchIndex][position] = winner

      } else if (roundType === 'quarterfinals') {
        match = bracket.quarterfinals.find(m => m.id === matchId)
        winner = playerId === match.player1.id ? match.player1 : match.player2
        match.winner = winner

        const matchIndex = bracket.quarterfinals.findIndex(m => m.id === matchId)
        const nextMatchIndex = Math.floor(matchIndex / 2)
        const position = matchIndex % 2 === 0 ? 'player1' : 'player2'
        bracket.semifinals[nextMatchIndex][position] = winner

      } else if (roundType === 'semifinals') {
        match = bracket.semifinals.find(m => m.id === matchId)
        winner = playerId === match.player1.id ? match.player1 : match.player2
        match.winner = winner

        const matchIndex = bracket.semifinals.findIndex(m => m.id === matchId)
        const position = matchIndex === 0 ? 'player1' : 'player2'
        bracket.finals[0][position] = winner

      } else if (roundType === 'finals') {
        match = bracket.finals[0]
        winner = playerId === match.player1.id ? match.player1 : match.player2
        match.winner = winner
        newTournament.winner = winner
        newTournament.status = 'completed'
      }

      newTournament.bracket = bracket

      // Persist to backend if tournament exists
      try {
        if (newTournament.id) {
          // Compute match index for backend from local position
          let localIdx = -1
          if (roundType === 'round1') localIdx = bracket.round1.findIndex(m => m.id === matchId)
          else if (roundType === 'round2') localIdx = bracket.round2.findIndex(m => m.id === matchId)
          else if (roundType === 'quarterfinals') localIdx = bracket.quarterfinals.findIndex(m => m.id === matchId)
          else if (roundType === 'semifinals') localIdx = bracket.semifinals.findIndex(m => m.id === matchId)
          else if (roundType === 'finals') localIdx = 0
          const mi = computeMatchIndex(roundType, Math.max(0, localIdx))
          if (mi != null) {
            // Fire-and-forget preview (optional), then apply
            previewTournamentReport({ tournament_id: newTournament.id, match_index: mi, winner_player: winner.name })
              .catch(() => { })
            applyTournamentReport({ tournament_id: newTournament.id, match_index: mi, winner_player: winner.name })
              .then(async (result) => {
                if (result?.backup_path) {
                  setLastBackup(result.backup_path)
                }
                try {
                  const serverData = await getTournament(newTournament.id)
                  applyBackendTournament(serverData, { silent: true })
                  setTournamentList(prev => Array.isArray(prev)
                    ? prev.map(item => item.id === serverData.id
                      ? { ...item, status: serverData.status, player_count: serverData.player_count, created_at: serverData.created_at }
                      : item)
                    : prev
                  )
                  addChatMessage('system', `? Match recorded: ${winner.name} advances`)

                  if (serverData.status === 'completed') {
                    const finalWinner = typeof serverData.winner === 'string'
                      ? serverData.winner
                      : serverData.winner?.name || winner.name
                    addChatMessage('assistant', `?? Tournament Complete! Winner: ${finalWinner}`)
                  }
                } catch (err) {
                  console.error('[ScoreKeeper] Failed to fetch updated tournament:', err)
                }
              })
              .catch(() => { })
          } else {
            // No index mapping available; skip persist
          }
        } else {
          addChatMessage('assistant', 'Tip: Click "Create Custom Bracket" to persist results to backend.')
        }
      } catch { }

      return newTournament
    })
  }, [selectedPlayerCount, computeMatchIndex, previewTournamentReport, applyTournamentReport, getTournament, addChatMessage, applyBackendTournament])

  // Undo last score submission
  const undoLast = useCallback(async () => {
    if (!lastBackup) return;

    try {
      const result = await undoScorekeeper()
      if (result?.pre_restore_backup) {
        setLastBackup(result.pre_restore_backup)
      } else {
        setLastBackup(null)
      }

      addChatMessage('assistant', result?.message || 'Undo successful - state restored.')

      const leaderboard = await getLeaderboard({ limit: 10 })
      setLeaderboardData(leaderboard.scores || [])
    } catch (err) {
      addChatMessage('assistant', `Undo failed: ${err.message}`)
    }
  }, [lastBackup, addChatMessage])

  const restoreFromBackup = useCallback(async () => {
    if (!lastBackup) {
      addChatMessage('assistant', 'No backup available to restore.')
      return
    }

    try {
      const result = await restoreScorekeeper({ backupPath: lastBackup })
      if (result?.pre_restore_backup) {
        setLastBackup(result.pre_restore_backup)
      }
      addChatMessage('assistant', result?.message || 'Backup restored successfully.')

      const leaderboard = await getLeaderboard({ limit: 10 })
      setLeaderboardData(leaderboard.scores || [])
    } catch (err) {
      addChatMessage('assistant', `Restore failed: ${err.message}`)
    }
  }, [lastBackup, addChatMessage])

  const updatePlayerName = useCallback((index, name) => {
    setPlayerNames(prev => ({
      ...prev,
      [selectedPlayerCount]: prev[selectedPlayerCount].map((oldName, i) =>
        i === index ? name : oldName
      )
    }))
  }, [selectedPlayerCount])

  const createCustomBracket = useCallback(async () => {
    const currentNames = playerNames[selectedPlayerCount]
    const bracket = generateBracket(selectedPlayerCount, currentNames)

    // Try to create tournament in backend
    try {
      const result = await applyTournamentCreate({
        name: tournament.name || `Tournament (${selectedPlayerCount} Players)`,
        game: 'General',
        player_count: selectedPlayerCount
      })

      if (result?.tournament && applyBackendTournament(result.tournament, { silent: true })) {
        setTournamentList(prev => {
          const existing = Array.isArray(prev) ? prev.filter(item => item.id !== result.tournament.id) : []
          return [
            {
              id: result.tournament.id,
              name: result.tournament.name,
              status: result.tournament.status,
              player_count: result.tournament.player_count,
              created_at: result.tournament.created_at,
              path: ''
            },
            ...existing
          ]
        })
        if (result?.backup_path) {
          setLastBackup(result.backup_path)
        }
        addChatMessage('assistant', `Created ${selectedPlayerCount} player tournament! (ID: ${result.tournament.id})`)
      } else {
        setTournament({
          id: result.tournament_id || Date.now().toString(),
          name: `Tournament (${selectedPlayerCount} Players)`,
          status: 'active',
          players: currentNames.slice(0, selectedPlayerCount),
          bracket,
          currentRound: roundKeyFor(selectedPlayerCount, 1),
          winner: null,
          createdAt: new Date()
        })
        addChatMessage('assistant', `Created ${selectedPlayerCount} player tournament locally.`)
      }
    } catch (err) {
      // Fallback to local-only if backend fails
      setTournament({
        id: Date.now().toString(),
        name: `Tournament (${selectedPlayerCount} Players)`,
        status: 'active',
        players: currentNames.slice(0, selectedPlayerCount),
        bracket,
        currentRound: roundKeyFor(selectedPlayerCount, 1),
        winner: null,
        createdAt: new Date()
      })

      setPlayerNames(prev => ({
        ...prev,
        [selectedPlayerCount]: currentNames.slice(0, selectedPlayerCount)
      }))

      addChatMessage('assistant', `Created ${selectedPlayerCount} player bracket locally! Backend unavailable.`)
    }
  }, [selectedPlayerCount, playerNames, generateBracket, addChatMessage, tournament.name, applyBackendTournament])

  const processCommand = useCallback((message) => {
    const lowerMessage = message.toLowerCase()

    if (lowerMessage.includes('create tournament') || lowerMessage.includes('new tournament')) {
      createCustomBracket()
    } else if (lowerMessage.includes('reset') || lowerMessage.includes('clear')) {
      const resetPlayers = playerNames[selectedPlayerCount].slice(0, selectedPlayerCount)
      setTournament({
        id: null,
        name: `Tournament (${selectedPlayerCount} Players)`,
        status: 'setup',
        players: resetPlayers,
        bracket: generateBracket(selectedPlayerCount, resetPlayers),
        currentRound: roundKeyFor(selectedPlayerCount, 1),
        winner: null,
        createdAt: null
      })
      addChatMessage('assistant', 'Tournament reset! Ready to create a new tournament.')
    } else {
      addChatMessage('assistant', 'I can help you create tournaments and manage brackets. Try "Create tournament" or click "Create Custom Bracket" to get started!')
    }
  }, [selectedPlayerCount, createCustomBracket, addChatMessage, generateBracket, playerNames])

  const sendGuardRef = useRef(false)
  const handleSendMessage = useCallback(async () => {
    if (!inputMessage.trim() || isProcessing || isLoading) return
    if (sendGuardRef.current) return
    sendGuardRef.current = true

    const userMessage = inputMessage.trim()
    setInputMessage('')
    setIsProcessing(true)
    setAiStatus('Processing...')

    addChatMessage('user', userMessage)

    try {
      // Build tournament context for AI
      const context = {
        systemPrompt: `You are ScoreKeeper Sam, the Tournament Commander. You help manage tournaments and ratings.

Core capabilities:
- Tournament creation (4, 8, 16, 32, 64, 128 players)
- Seeding: random, Elo, Glicko-2, family-adjusted
- Match tracking and rating updates
- Leaderboard management

Seeding variants:
- Standard Elo: Pure skill (competitive)
- Glicko Conservative: Accounts for uncertainty (new players)
- Family Adjusted: Elo + 1000/(games+1) boost for newcomers

Communication style:
- Concise (2-3 sentences)
- Actionable tournament advice
- Encouraging to all skill levels
- No emoji unless user uses them first

Current tournament context will be provided. Use it to give specific advice.`,
        panel: 'scorekeeper',
        current_tournament: tournament.status !== 'setup' ? {
          name: tournament.name,
          status: tournament.status,
          player_count: tournament.players?.length || 0,
          current_round: tournament.currentRound,
          has_bracket: !!tournament.bracket
        } : null,
        player_count: selectedPlayerCount,
        leaderboard_size: leaderboardData?.length || 0
      }

      console.log('[ScoreKeeper] Sending chat message:', userMessage)
      console.log('[ScoreKeeper] Context:', context)

      // Call AI with tournament context
      const result = await executeAction('chat', {
        message: userMessage,
        context
      })

      console.log('[ScoreKeeper] AI response:', result)

      // Extract response
      const responseText = result?.message?.content || result?.response || 'I can help you create and manage tournaments. What would you like to do?'

      console.log('[ScoreKeeper] Extracted text:', responseText)

      addChatMessage('assistant', responseText)

      // Speak the response as Sam (fire-and-forget)
      setIsSamSpeaking(true)
      speakAsSam(responseText)
        .catch(() => {})
        .finally(() => setIsSamSpeaking(false))

      // Check if AI suggested an action and execute it
      const lowerResponse = responseText.toLowerCase()
      if (lowerResponse.includes('create') && (lowerResponse.includes('tournament') || lowerResponse.includes('bracket'))) {
        setTimeout(() => createCustomBracket(), 500)
      } else if (lowerResponse.includes('reset') || lowerResponse.includes('clear')) {
        setTimeout(() => processCommand('reset'), 500)
      }

      setAiStatus('AI Ready')
    } catch (error) {
      console.error('[ScoreKeeper] AI chat error:', error)
      console.error('[ScoreKeeper] Error details:', error?.message, error?.code, error)

      // Fallback to mock behavior with error message
      const errorMsg = error?.message || error?.code || 'Unknown error'
      addChatMessage('assistant', `Chat error: ${errorMsg}. Please check console for details.`)
      setAiStatus(`AI Error: ${errorMsg}`)
    } finally {
      setIsProcessing(false)
      setTimeout(() => { sendGuardRef.current = false }, 500)
    }
  }, [inputMessage, isProcessing, isLoading, addChatMessage, executeAction, tournament, selectedPlayerCount, leaderboardData])

  const handleChatOpen = useCallback(() => setChatOpen(true), [])
  const handleChatClose = useCallback(() => setChatOpen(false), [])

  // Big Board full-screen display (read-only)
  if (bigBoard) {
    return (
      <div className="scorekeeper-panel-wrapper" style={{ padding: 24 }}>
        <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', marginBottom: 12 }}>
          <div style={{ display: 'flex', alignItems: 'center', gap: 12 }}>
            <div style={{ fontSize: 48 }}>??</div>
            <div>
              <div style={{ fontSize: 28, fontWeight: 700, color: '#c8ff00' }}>ScoreKeeper Sam � Big Board</div>
              <div style={{ color: '#9ca3af' }}>Live leaderboard (read-only)</div>
            </div>
          </div>
          <div style={{ color: '#9ca3af' }}>{new Date().toLocaleString()}</div>
        </div>
        <div style={{ marginTop: 16 }}>
          <table style={{ width: '100%', borderCollapse: 'collapse', fontSize: 18 }}>
            <thead>
              <tr style={{ borderBottom: '2px solid rgba(200,255,0,0.4)' }}>
                <th style={{ textAlign: 'left', padding: 12 }}>Player</th>
                <th style={{ textAlign: 'left', padding: 12 }}>Score</th>
                <th style={{ textAlign: 'left', padding: 12 }}>Time</th>
              </tr>
            </thead>
            <tbody>
              {(leaderboardData || []).slice(0, 10).map((entry, idx) => {
                const isProfile = Boolean(entry?.player_source === 'profile' || entry?.player_userId)
                return (
                  <tr key={idx} style={{ borderBottom: '1px solid rgba(148,163,184,0.2)' }}>
                    <td style={{ padding: 12 }}>
                      {entry.player || entry.bestPlayer || '�'}
                      {(entry.player || entry.bestPlayer) && (
                        <span style={{
                          marginLeft: 8,
                          fontSize: 12,
                          padding: '2px 8px',
                          borderRadius: 12,
                          border: '1px solid rgba(200,255,0,0.3)',
                          background: isProfile ? 'rgba(200,255,0,0.12)' : 'rgba(148,163,184,0.15)',
                          color: isProfile ? '#c8ff00' : '#d1d5db'
                        }}>{isProfile ? 'Profile' : 'Guest'}</span>
                      )}
                    </td>
                    <td style={{ padding: 12 }}>{formatScoreValue(entry.score ?? entry.bestScore)}</td>
                    <td style={{ padding: 12 }}>{entry.timestamp ? new Date(entry.timestamp).toLocaleTimeString() : '�'}</td>
                  </tr>
                )
              })}
            </tbody>
          </table>
        </div>
      </div>
    )
  }

  return (
    <div className="scorekeeper-panel-wrapper">
      <div className="sam-dashboard">
        {/* === HEADER === */}
        <header className="sam-header glass-panel">
          <div className="sam-header-left">
            <div className="sam-header-game">
              <span className="material-symbols-outlined game-icon">videogame_asset</span>
              <div>
                <h1>ScoreKeeper Sam</h1>
                <p className="cabinet-id">HIGH SCORE TRACKER // {aiStatus.toUpperCase()}</p>
              </div>
            </div>
            <div className="sam-header-divider" />
            {leaderboardData.length > 0 && (
              <div className="sam-header-ticker">
                <span className="material-symbols-outlined">bolt</span>
                <span>{formatScoreValue(leaderboardData[0]?.score ?? leaderboardData[0]?.bestScore)} pts to beat!</span>
              </div>
            )}
          </div>
          <div className="sam-header-right">
            {/* View Toggle */}
            <div className="sam-view-toggle">
              <button
                className={activeView === 'highscores' ? 'active' : 'inactive'}
                onClick={() => setActiveView('highscores')}
              >
                ?? High Scores
              </button>
              <button
                className={activeView === 'tournament' ? 'active' : 'inactive'}
                onClick={() => setActiveView('tournament')}
              >
                ?? Tournament
              </button>
            </div>
            {/* Resume Last Tournament */}
            {tournamentList.length > 0 && (
              <button
                className="chat-toggle-btn"
                onClick={async () => {
                  try {
                    const last = tournamentList[0]
                    if (!last?.id) return
                    const srv = await getTournament(last.id)
                    applyBackendTournament(srv, { silent: false })
                    setActiveView('tournament')
                  } catch {
                    addChatMessage('assistant', 'Failed to resume last tournament')
                  }
                }}
                title="Resume Last Tournament"
              >
                ? Resume
              </button>
            )}
            {/* Chat Toggle */}
            <button className="chat-toggle-btn" onClick={handleChatOpen}>
              ?? Sam
            </button>
            {/* Sam Avatar */}
            <div className="sam-avatar-container">
              <div className="sam-avatar-img" style={{ backgroundImage: "url('/sam-avatar.jpeg')" }} />
              <div className="sam-avatar-status" />
            </div>
          </div>
        </header>

        {/* Plugin Paused Banner */}
        {(pluginPaused || scoresCached || paused) && (
          <div className="scorekeeper-paused-banner">
            ? Plugin offline � showing cached results
          </div>
        )}

        {/* ========== HIGH SCORES VIEW ========== */}
        {activeView === 'highscores' && (
          <div className="sam-main">
            {/* Left Column: Leaderboard (60%) */}
            <section className="sam-leaderboard glass-panel">
              <div className="sam-leaderboard-header">
                <h2>
                  <span className="material-symbols-outlined">leaderboard</span>
                  ALL-TIME LEGENDS
                </h2>
                <div className="sam-time-filters">
                  <button className="inactive">Today</button>
                  <button className="inactive">Weekly</button>
                  <button className="active">All-Time</button>
                </div>
              </div>
              <div className="sam-leaderboard-body">
                <table className="sam-leaderboard-table">
                  <thead>
                    <tr>
                      <th>Rank</th>
                      <th>Player</th>
                      <th>Score</th>
                      <th>Date</th>
                    </tr>
                  </thead>
                  <tbody>
                    {(leaderboardData || []).map((entry, idx) => {
                      const playerName = entry.player || entry.bestPlayer || '�'
                      const score = formatScoreValue(entry.score ?? entry.bestScore)
                      const dateStr = entry.timestamp ? new Date(entry.timestamp).toLocaleDateString(undefined, { month: 'short', day: 'numeric' }) : '�'
                      const gid = entry.gameId || entry.game_id

                      // Rank 1 � Gold
                      if (idx === 0) {
                        return (
                          <tr key={idx} className="sam-rank-row rank-1" onClick={() => gid && fetchByGame(gid)} style={{ cursor: gid ? 'pointer' : 'default' }}>
                            <td colSpan="4">
                              <div className="rank-row-inner">
                                <div className="rank-info-left">
                                  <div className="rank-badge">
                                    <span className="material-symbols-outlined" style={{ fontSize: '1.125rem' }}>emoji_events</span>
                                  </div>
                                  <span className="rank-number">#1</span>
                                  <div className="rank-player-section">
                                    <span className="rank-player-name">{playerName}</span>
                                    <span className="rank-tag">MVP</span>
                                  </div>
                                </div>
                                <div className="rank-info-right">
                                  <div className="rank-score-section">
                                    <span className="rank-score">{score}</span>
                                    <div className="rank-new-record">RECORD HOLDER</div>
                                  </div>
                                  <span className="rank-date">{dateStr}</span>
                                </div>
                              </div>
                            </td>
                          </tr>
                        )
                      }

                      // Rank 2 � Silver
                      if (idx === 1) {
                        return (
                          <tr key={idx} className="sam-rank-row rank-2" onClick={() => gid && fetchByGame(gid)} style={{ cursor: gid ? 'pointer' : 'default' }}>
                            <td colSpan="4">
                              <div className="rank-row-inner">
                                <div className="rank-info-left">
                                  <div className="rank-badge">
                                    <span className="material-symbols-outlined" style={{ fontSize: '1rem' }}>military_tech</span>
                                  </div>
                                  <span className="rank-number">#2</span>
                                  <div className="rank-player-section">
                                    <span className="rank-player-name">{playerName}</span>
                                  </div>
                                </div>
                                <div className="rank-info-right">
                                  <div className="rank-score-section">
                                    <span className="rank-score">{score}</span>
                                  </div>
                                  <span className="rank-date">{dateStr}</span>
                                </div>
                              </div>
                            </td>
                          </tr>
                        )
                      }

                      // Rank 3 � Bronze
                      if (idx === 2) {
                        return (
                          <tr key={idx} className="sam-rank-row rank-3" onClick={() => gid && fetchByGame(gid)} style={{ cursor: gid ? 'pointer' : 'default' }}>
                            <td colSpan="4">
                              <div className="rank-row-inner">
                                <div className="rank-info-left">
                                  <div className="rank-badge">
                                    <span className="material-symbols-outlined" style={{ fontSize: '1rem' }}>military_tech</span>
                                  </div>
                                  <span className="rank-number">#3</span>
                                  <div className="rank-player-section">
                                    <span className="rank-player-name">{playerName}</span>
                                  </div>
                                </div>
                                <div className="rank-info-right">
                                  <div className="rank-score-section">
                                    <span className="rank-score">{score}</span>
                                  </div>
                                  <span className="rank-date">{dateStr}</span>
                                </div>
                              </div>
                            </td>
                          </tr>
                        )
                      }

                      // Standard rows (#4+)
                      return (
                        <tr key={idx} className="sam-rank-row rank-standard" onClick={() => gid && fetchByGame(gid)} style={{ cursor: gid ? 'pointer' : 'default' }}>
                          <td>#{idx + 1}</td>
                          <td>{playerName}</td>
                          <td>{score}</td>
                          <td>{dateStr}</td>
                        </tr>
                      )
                    })}
                    {leaderboardData.length === 0 && (
                      <tr>
                        <td colSpan="4" style={{ textAlign: 'center', padding: '2rem', color: 'var(--sam-text-muted)' }}>
                          No scores recorded yet. Submit a score below to get started!
                        </td>
                      </tr>
                    )}
                  </tbody>
                </table>
              </div>
            </section>

            {/* Right Column: Sidebar (40%) */}
            <aside className="sam-sidebar">
              {/* Personal Stats Card */}
              <div className="sam-personal-stats glass-panel-highlight">
                <div className="bg-icon">
                  <span className="material-symbols-outlined">person</span>
                </div>
                <h3>
                  <span className="material-symbols-outlined">badge</span>
                  Personal Performance
                </h3>
                <div className="sam-stats-main">
                  <div>
                    <p className="stat-label">High Score</p>
                    <p className="stat-value-large">
                      {leaderboardData.length > 0 ? formatScoreValue(leaderboardData[0]?.score ?? leaderboardData[0]?.bestScore) : '�'}
                    </p>
                  </div>
                  <div style={{ textAlign: 'right' }}>
                    <p className="stat-label">Rank</p>
                    <p className="stat-value-rank">#1</p>
                  </div>
                </div>
                <div className="sam-progress-bar">
                  <div className="fill" style={{ width: leaderboardData.length > 0 ? '100%' : '0%' }} />
                </div>
                <p className="sam-progress-label">
                  {leaderboardData.length > 0 ? `${leaderboardData.length} scores tracked` : 'No data yet'}
                </p>
                <div className="sam-stats-grid">
                  <div>
                    <p className="stat-mini-label">Total Games</p>
                    <p className="stat-mini-value">{leaderboardData.length}</p>
                  </div>
                  <div>
                    <p className="stat-mini-label">Status</p>
                    <p className="stat-mini-value stat-green">
                      {pluginPaused ? 'Cached' : 'Live'} <span className="material-symbols-outlined" style={{ fontSize: '0.75rem', verticalAlign: 'middle' }}>{pluginPaused ? 'cloud_off' : 'arrow_upward'}</span>
                    </p>
                  </div>
                </div>
              </div>

              {/* Recent Records */}
              <div className="sam-recent-records glass-panel">
                <div className="sam-recent-records-header">
                  <h3>
                    <span className="material-symbols-outlined">new_releases</span>
                    Recent Records
                  </h3>
                  <span className="live-label">LIVE FEED</span>
                </div>
                <div className="sam-recent-records-body">
                  {(leaderboardData || []).slice(0, 5).map((entry, idx) => (
                    <div key={idx} className="sam-record-item">
                      <div style={{ display: 'flex', alignItems: 'center', gap: '0.5rem', overflow: 'hidden', flex: 1 }}>
                        <div className={`record-rank ${idx < 3 ? 'highlight' : 'standard'}`}>#{idx + 1}</div>
                        <span className="record-name">{entry.player || entry.bestPlayer || '�'}</span>
                      </div>
                      <div style={{ textAlign: 'right' }}>
                        <span className="record-score">{formatScoreValue(entry.score ?? entry.bestScore)}</span>
                        {idx === 0 && <span className="record-new">NEW!</span>}
                      </div>
                    </div>
                  ))}
                  {leaderboardData.length === 0 && (
                    <div style={{ textAlign: 'center', color: 'var(--sam-text-dim)', fontSize: '0.8rem' }}>
                      No recent records
                    </div>
                  )}
                </div>
              </div>

              {/* Cabinet Analytics */}
              <div className="sam-cabinet-analytics glass-panel">
                <h3>Cabinet Analytics</h3>
                <div className="sam-analytics-grid">
                  <div className="sam-analytics-card">
                    <div className="card-icon primary">
                      <span className="material-symbols-outlined">joystick</span>
                    </div>
                    <p className="card-value">{leaderboardData.length}</p>
                    <p className="card-label">Total Scores</p>
                  </div>
                  <div className="sam-analytics-card">
                    <div className="card-icon secondary">
                      <span className="material-symbols-outlined">schedule</span>
                    </div>
                    <p className="card-value">{tournamentList.length}</p>
                    <p className="card-label">Tournaments</p>
                  </div>
                </div>
                <div className="sam-cabinet-health">
                  <div className="health-header">
                    <span className="health-label">SYSTEM STATUS</span>
                    <span className="health-value">{pluginPaused ? '? Cached' : '? Live'}</span>
                  </div>
                  <div className="health-bar">
                    <div className="health-bar-fill" style={{ width: pluginPaused ? '50%' : '98%' }} />
                  </div>
                </div>
              </div>
            </aside>
          </div>
        )}

        {/* ========== TOURNAMENT VIEW ========== */}
        {activeView === 'tournament' && (
          <div className="sam-tournament-view">
            {/* Left: Bracket Display */}
            <div className="sam-bracket-display glass-panel">
              <div className="bracket-header">
                <h2>
                  <span className="material-symbols-outlined">trophy</span>
                  {tournament.name}
                </h2>
                <span style={{ fontSize: '0.75rem', color: 'var(--sam-text-muted)' }}>
                  {tournament.status === 'active' ? '? Active' : tournament.status === 'completed' ? '? Completed' : '? Setup'}
                </span>
              </div>
              <div className="sam-bracket-body">
                {tournament.status === 'setup' ? (
                  <div style={{ display: 'flex', flexDirection: 'column', alignItems: 'center', justifyContent: 'center', height: '100%', gap: '1rem', color: 'var(--sam-text-muted)' }}>
                    <span className="material-symbols-outlined" style={{ fontSize: '4rem', color: 'var(--sam-primary)', opacity: 0.3 }}>emoji_events</span>
                    <h2 style={{ margin: 0, color: 'white' }}>Ready to Create Tournament</h2>
                    <p>Enter player names and click "Create Custom Bracket" to begin</p>
                  </div>
                ) : (
                  <div className="bracket-grid">
                    {tournament.bracket?.round1?.length > 0 && (
                      <div className="round">
                        <div className="round-label">ROUND 1</div>
                        {tournament.bracket.round1.map((match) => (
                          <BracketMatch key={match.id} match={match} roundType="round1" onPlayerClick={advancePlayer} />
                        ))}
                      </div>
                    )}
                    {tournament.bracket?.round2?.length > 0 && (
                      <div className="round">
                        <div className="round-label">ROUND 2</div>
                        {tournament.bracket.round2.map((match) => (
                          <BracketMatch key={match.id} match={match} roundType="round2" onPlayerClick={advancePlayer} />
                        ))}
                      </div>
                    )}
                    {tournament.bracket?.quarterfinals?.length > 0 && (
                      <div className="round">
                        <div className="round-label">QUARTERFINALS</div>
                        {tournament.bracket.quarterfinals.map((match) => (
                          <BracketMatch key={match.id} match={match} roundType="quarterfinals" onPlayerClick={advancePlayer} />
                        ))}
                      </div>
                    )}
                    {tournament.bracket?.semifinals?.length > 0 && (
                      <div className="round">
                        <div className="round-label">SEMIFINALS</div>
                        {tournament.bracket.semifinals.map((match) => (
                          <BracketMatch key={match.id} match={match} roundType="semifinals" onPlayerClick={advancePlayer} />
                        ))}
                      </div>
                    )}
                    {tournament.bracket?.finals?.length > 0 && (
                      <div className="round">
                        <div className="round-label">FINALS</div>
                        <BracketMatch match={tournament.bracket.finals[0]} roundType="finals" onPlayerClick={advancePlayer} />
                        <div className="tournament-winner-display">
                          <div className="trophy-icon">??</div>
                          <div style={{ fontSize: '1.25rem', fontWeight: 700, color: tournament.winner ? '#ffd700' : 'var(--sam-text-muted)' }}>
                            {tournament.winner ? tournament.winner.name : 'TBD'}
                          </div>
                        </div>
                      </div>
                    )}
                  </div>
                )}
              </div>
            </div>

            {/* Right: Setup Panel */}
            <div className="sam-setup-panel glass-panel">
              <div className="section-title">Tournament Name</div>
              <input
                type="text"
                className="player-input"
                value={tournament.name}
                onChange={(e) => setTournament(prev => ({ ...prev, name: e.target.value }))}
                placeholder="Tournament Name"
                style={{ marginBottom: '1rem' }}
              />

              <div className="section-title">Quick Start</div>
              <div className="preset-buttons">
                <button className="preset-btn" onClick={() => alert('Family Tournament preset � Available soon')}>?? Family</button>
                <button className="preset-btn" onClick={() => alert('Friends Night preset � Available soon')}>?? Friends</button>
                <button className="preset-btn" onClick={() => alert('Random Players � Available soon')}>?? Random</button>
                <button className="preset-btn" onClick={() => alert('Load Saved Group � Available soon')}>?? Load Saved</button>
              </div>

              <div className="section-title">Player Count</div>
              <div className="player-count-buttons">
                {PLAYER_COUNTS.map(count => (
                  <button
                    key={count}
                    className={`player-count-btn ${selectedPlayerCount === count ? 'selected' : ''}`}
                    onClick={() => setSelectedPlayerCount(count)}
                  >
                    {count}P
                  </button>
                ))}
              </div>

              <div className="section-title" style={{ marginTop: '1rem' }}>Submit Score</div>
              <div style={{ display: 'flex', gap: '0.25rem', alignItems: 'center', marginBottom: '0.5rem' }}>
                <label style={{ display: 'flex', alignItems: 'center', gap: '0.375rem', fontSize: '0.8rem' }}>
                  <input
                    type="checkbox"
                    checked={useProfileForScore}
                    onChange={(e) => {
                      const on = e.target.checked
                      setUseProfileForScore(on)
                      if (on && profileData?.displayName) {
                        setScoreForm(prev => ({ ...prev, player: profileData.displayName }))
                      }
                    }}
                    disabled={!profileData}
                  />
                  Use Profile {profileData?.displayName ? `(${profileData.displayName})` : ''}
                </label>
              </div>
              <input type="text" className="player-input" placeholder="Game" value={scoreForm.game} onChange={(e) => setScoreForm({ ...scoreForm, game: e.target.value })} />
              <input type="text" className="player-input" placeholder="Player Name" value={useProfileForScore && profileData?.displayName ? profileData.displayName : scoreForm.player} onChange={(e) => setScoreForm({ ...scoreForm, player: e.target.value })} disabled={useProfileForScore && !!profileData?.displayName} />
              <input type="number" className="player-input" placeholder="Score" value={scoreForm.score} onChange={(e) => setScoreForm({ ...scoreForm, score: e.target.value })} />
              <div style={{ display: 'flex', gap: '0.25rem', marginTop: '0.5rem', flexWrap: 'wrap' }}>
                <button className="action-btn" onClick={async () => {
                  try {
                    const eligible = Boolean(consent?.accepted && (consent?.scopes || []).includes('leaderboard_public'))
                    const payload = { ...scoreForm, ...(useProfileForScore && profileData ? { player: profileData.displayName, player_userId: profileData.userId, player_source: 'profile', publicLeaderboardEligible: eligible } : { player_source: 'guest', publicLeaderboardEligible: false }) }
                    const result = await previewScoreSubmit(payload)
                    setScorePreview(result)
                    addChatMessage('assistant', 'Score preview ready!')
                  } catch (err) { addChatMessage('assistant', `Preview failed: ${err.message}`) }
                }} disabled={!scoreForm.game || !scoreForm.player || !scoreForm.score}>Preview</button>
                <button className="action-btn" onClick={async () => {
                  try {
                    const eligible = Boolean(consent?.accepted && (consent?.scopes || []).includes('leaderboard_public'))
                    const payload = { ...scoreForm, ...(useProfileForScore && profileData ? { player: profileData.displayName, player_userId: profileData.userId, player_source: 'profile', publicLeaderboardEligible: eligible } : { player_source: 'guest', publicLeaderboardEligible: false }) }
                    try {
                      const matches = await resolveGameByTitle(scoreForm.game)
                      const first = Array.isArray(matches) && matches.length > 0 ? matches[0] : null
                      if (first && first.id) { await submitScoreViaPlugin({ gameId: first.id, player: payload.player, score: Number(payload.score) }); addChatMessage('assistant', `Score submitted via plugin for ${payload.player}`) }
                    } catch { /* fallback */ }
                    const result = await applyScoreSubmit(payload)
                    if (result.backup_path) { setLastBackup(result.backup_path); addChatMessage('assistant', `Score submitted for ${scoreForm.player}!`) }
                    else { addChatMessage('assistant', `Score submitted for ${scoreForm.player}!`) }
                    setScoreForm({ game: '', player: '', score: '' })
                    setScorePreview(null)
                    const leaderboard = await getLeaderboard({ limit: 10 })
                    setLeaderboardData(leaderboard.scores || [])
                    setScoresCached(!!leaderboard.cached)
                    setPluginPaused(!!leaderboard.cached)
                  } catch (err) { addChatMessage('assistant', `Submit failed: ${err.message}`) }
                }} disabled={!scorePreview}>Apply</button>
                <button className="action-btn ghost-btn" onClick={undoLast} disabled={!lastBackup}>Undo</button>
              </div>
              {scorePreview && (
                <div style={{ marginTop: '0.5rem', padding: '0.5rem', background: 'rgba(13, 204, 242, 0.1)', borderRadius: '0.375rem' }}>
                  <pre style={{ fontSize: '0.7rem', color: 'var(--sam-primary)', margin: 0, whiteSpace: 'pre-wrap' }}>{JSON.stringify(scorePreview, null, 2)}</pre>
                </div>
              )}

              <div className="section-title" style={{ marginTop: '1rem' }}>Player Names</div>
              <div style={{ display: 'flex', gap: '0.25rem', marginBottom: '0.5rem' }}>
                <button className="action-btn" onClick={() => {
                  if (!profileData?.displayName) return
                  setPlayerNames(prev => {
                    const copy = { ...prev }
                    const names = [...copy[selectedPlayerCount]]
                    const emptyIndex = names.findIndex(n => !n || n.startsWith('Player '))
                    const idx = emptyIndex >= 0 ? emptyIndex : 0
                    names[idx] = profileData.displayName
                    copy[selectedPlayerCount] = names
                    return copy
                  })
                }} disabled={!profileData?.displayName}>Add Myself</button>
              </div>
              <div className="player-inputs">
                {Array.from({ length: selectedPlayerCount }, (_, index) => (
                  <input key={index} type="text" className="player-input" placeholder={`Player ${index + 1}`} value={playerNames[selectedPlayerCount][index] || ''} onChange={(e) => updatePlayerName(index, e.target.value)} />
                ))}
              </div>

              <div className="create-bracket-section">
                <button className="create-bracket-btn" onClick={createCustomBracket}>Create Custom Bracket</button>
                <div className="players-entered">{(tournament.players?.length || 0)} players entered</div>
              </div>
            </div>
          </div>
        )}

        {/* ========== FOOTER � Quick Score Entry (High Scores view only) ========== */}
        {activeView === 'highscores' && (
          <footer className="sam-footer glass-panel">
            <form className="sam-score-form" onSubmit={(e) => { e.preventDefault() }}>
              <div className="sam-game-input">
                <span className="material-symbols-outlined game-icon" style={{ fontSize: '1.25rem' }}>sports_esports</span>
                <input type="text" placeholder="Game title..." value={scoreForm.game} onChange={(e) => setScoreForm({ ...scoreForm, game: e.target.value })} />
              </div>
              <div className="sam-player-select">
                <span className="material-symbols-outlined select-icon">account_circle</span>
                <select
                  value={useProfileForScore && profileData?.displayName ? 'profile' : 'guest'}
                  onChange={(e) => {
                    const isProfile = e.target.value === 'profile'
                    setUseProfileForScore(isProfile)
                    if (isProfile && profileData?.displayName) {
                      setScoreForm(prev => ({ ...prev, player: profileData.displayName }))
                    }
                  }}
                >
                  <option value="guest">Guest</option>
                  {profileData?.displayName && <option value="profile">{profileData.displayName}</option>}
                </select>
              </div>
              <div className="sam-score-input">
                <span className="input-prefix">PTS:</span>
                <input type="text" placeholder="00,000,000" value={scoreForm.score} onChange={(e) => setScoreForm({ ...scoreForm, score: e.target.value })} />
              </div>
              <button type="button" className="sam-undo-btn" onClick={undoLast} disabled={!lastBackup} title={lastBackup ? 'Undo last score' : 'No backup available'}>
                <span className="material-symbols-outlined">undo</span>
              </button>
              <button
                type="button"
                className="sam-submit-btn"
                disabled={!scoreForm.game || !scoreForm.score}
                onClick={async () => {
                  try {
                    const eligible = Boolean(consent?.accepted && (consent?.scopes || []).includes('leaderboard_public'))
                    const payload = {
                      ...scoreForm,
                      ...(useProfileForScore && profileData ? {
                        player: profileData.displayName, player_userId: profileData.userId, player_source: 'profile', publicLeaderboardEligible: eligible
                      } : { player_source: 'guest', publicLeaderboardEligible: false })
                    }
                    try {
                      const matches = await resolveGameByTitle(scoreForm.game)
                      const first = Array.isArray(matches) && matches.length > 0 ? matches[0] : null
                      if (first && first.id) {
                        await submitScoreViaPlugin({ gameId: first.id, player: payload.player, score: Number(payload.score) })
                        addChatMessage('assistant', `Score submitted via plugin for ${payload.player}`)
                      }
                    } catch { /* fallback */ }
                    const result = await applyScoreSubmit(payload)
                    if (result?.backup_path) setLastBackup(result.backup_path)
                    addChatMessage('assistant', `Score submitted for ${scoreForm.player || 'Guest'}!`)
                    setScoreForm({ game: '', player: '', score: '' })
                    setScorePreview(null)
                    const leaderboard = await getLeaderboard({ limit: 10 })
                    setLeaderboardData(leaderboard.scores || [])
                    setScoresCached(!!leaderboard.cached)
                    setPluginPaused(!!leaderboard.cached)
                  } catch (err) {
                    addChatMessage('assistant', `Submit failed: ${err.message}`)
                  }
                }}
              >
                <span>Log Score</span>
                <span className="material-symbols-outlined">publish</span>
              </button>
            </form>
          </footer>
        )}
      </div>

      {/* Chat Sidebar */}
      {chatOpen && (
        <div className="panel-chat-sidebar" role="dialog" aria-label="Chat with Sam">
          <div className="chat-header">
            <img src="/sam-avatar.jpeg" alt="Sam" className="chat-avatar" />
            <div className="chat-info">
              <h3>ScoreKeeper Sam</h3>
              <div className="chat-status">� Ready to assist</div>
            </div>
            <button className="chat-close-btn" onClick={handleChatClose} aria-label="Close chat">�</button>
          </div>

          <div className="welcome-message">
            Welcome to ScoreKeeper Sam! I'm your Tournament Commander, ready to manage competitions, create brackets, and track scores. What can I help you with today?
          </div>

          <div className="chat-messages" ref={chatMessagesRef}>
            {chatMessages.map((message) => (
              <div key={message.id} className={`message ${message.type}`}>
                <div className="message-avatar">{message.type === 'user' ? '??' : '??'}</div>
                <div className="message-content">{message.content}</div>
              </div>
            ))}
            {isProcessing && (
              <div className="message assistant">
                <div className="message-avatar">??</div>
                <div className="message-content">Processing command...</div>
              </div>
            )}
          </div>

          <div className="chat-input-area">
            <div className="input-container">
              <button
                className={`voice-btn ${isListening ? 'listening' : ''} ${isSamSpeaking ? 'speaking' : ''}`}
                aria-label={isListening ? 'Stop listening' : 'Voice input'}
                onClick={isListening ? toggleListening : isSamSpeaking ? () => { stopSpeaking(); setIsSamSpeaking(false) } : toggleListening}
                title={isListening ? 'Listening... click to stop' : isSamSpeaking ? 'Sam is speaking... click to stop' : 'Click to speak'}
              >
                {isListening ? '??' : isSamSpeaking ? '??' : '??'}
              </button>
              <input
                type="text"
                className="chat-input"
                placeholder="Type your command..."
                value={inputMessage}
                onChange={(e) => setInputMessage(e.target.value)}
                onKeyPress={(e) => e.key === 'Enter' && handleSendMessage()}
                disabled={isProcessing}
              />
              <button className="execute-btn" onClick={handleSendMessage} disabled={isProcessing || !inputMessage.trim()}>
                {isProcessing ? 'PROCESSING...' : 'EXECUTE'}
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  )
}

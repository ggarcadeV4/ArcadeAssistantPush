import React, { useEffect, useState, Suspense } from 'react'
import { useLocation, useNavigate } from 'react-router-dom'
import ErrorBoundary from './ErrorBoundary'
import { stopSpeaking } from '../services/ttsClient'

// ── Lazy-loaded Gem Panels ────────────────────────────────────────────────────
// Every panel is dynamically imported so Vite can code-split them into
// separate chunks. Only the active panel's JS is fetched on navigation.
const LEDBlinkyPanel = React.lazy(() => import('./led-blinky/LEDBlinkyPanelWrapper'))
const GunnerPanel = React.lazy(() => import('./gunner/GunnerPanel'))
const ControllerPanel = React.lazy(() => import('../panels/controller/ControllerPanel'))
const ControllerChuckPanel = React.lazy(() => import('./ControllerChuckPanel'))
const ControllerChuckPanelRedesign = React.lazy(() => import('../panels/controller/ControllerChuckPanel'))
const ConsoleWizardPanel = React.lazy(() => import('../panels/console-wizard/ConsoleWizardPanel'))
const VoicePanel = React.lazy(() => import('../panels/voice/VoicePanel'))
const SystemHealthPanel = React.lazy(() => import('../panels/system-health/SystemHealthPanel'))
const LaunchBoxPanel = React.lazy(() => import('../panels/launchbox/LaunchBoxPanel'))
const ContentDisplayManager = React.lazy(() => import('../panels/launchbox/ContentDisplayManager'))
const DiagnosticsPanel = React.lazy(() => import('../panels/diagnostics/DiagnosticsPanel'))
const DeweyPanel = React.lazy(() => import('../panels/dewey/DeweyPanel'))
const ScoreKeeperPanel = React.lazy(() => import('../panels/scorekeeper/ScoreKeeperPanel'))
const CabinetHighScoresPanel = React.lazy(() => import('../panels/scorekeeper/CabinetHighScoresPanel'))

// Dewey is accessed directly via /assistants?agent=dewey, not from the personas grid
const personas = [
  {
    id: 'launchbox',
    name: 'LaunchBox LoRa',
    role: 'AI Agent: LoRa',
    summary: 'Launch retro titles, manage playlists, and import content sources.',
    hero: '/lora-hero.png',
    avatar: '/lora-avatar.jpeg'
  },
  {
    id: 'dewey',
    name: 'Dewey AI Assistant',
    role: 'AI Agent: Dewey',
    summary: 'Ask questions, browse manuals, and get step-by-step repair help.',
    hero: '/dewey-hero.png',
    avatar: '/dewey-avatar.jpeg'
  },
  {
    id: 'scorekeeper',
    name: 'Historian / Scorekeeper',
    role: 'AI Agent: Scores',
    summary: 'Track high scores, manage tournaments, and archive run histories.',
    hero: '/sam-hero.png',
    avatar: '/sam-avatar.jpeg'
  },
  {
    id: 'voice',
    name: 'Voice Assistant',
    role: 'AI Agent: Voice',
    summary: 'Hands-free control, speech input, and text-to-speech.',
    hero: '/voice-hero.png',
    avatar: '/vicky-avatar.jpeg'
  },
  {
    id: 'interface',
    name: 'Arcade Interface',
    role: 'Control Panel',
    summary: 'Unified arcade controls, overlays, and quick actions.',
    hero: '/chuck-hero.png',
    avatar: '/chuck-avatar.jpeg'
  },
  {
    id: 'controller-wizard',
    name: 'Console Controller Wizard',
    role: 'AI Agent: Controls',
    summary: 'Emulator profiles and console controller mapping (NES/SNES/etc).',
    hero: '/wiz-hero.png',
    avatar: '/wiz-avatar.jpeg'
  },
  {
    id: 'led',
    name: 'LED Blinky',
    role: 'Lighting',
    summary: 'Game-aware button lighting and effects integrated with LaunchBox/MAME.',
    hero: '/led-hero.png',
    avatar: '/led-avatar.jpeg'
  },
  {
    id: 'lightguns',
    name: 'Light Guns',
    role: 'Calibration',
    summary: 'Sinden/Gun4IR setup, auto-calibration, and CRT-friendly profiles.',
    hero: '/lightguns-hero.png',
    avatar: '/gunner-avatar.jpeg'
  },
  {
    id: 'health',
    name: 'System Health Integration',
    role: 'System',
    summary: 'Monitor drives, builds, emulators, and configs in real time.',
    hero: '/doc-hero.png',
    avatar: '/doc-avatar.jpeg'
  }
]

function chunk(arr, size) {
  const out = []
  for (let i = 0; i < arr.length; i += size) out.push(arr.slice(i, i + size))
  return out
}

function PersonaCard({ p }) {
  const navigate = useNavigate()

  const handleLaunchPanel = () => {
    console.log('Launching panel for:', p.id)
    navigate(`/assistants?agent=${p.id}`)
  }

  const handleChatWithAI = () => {
    console.log('Chat with AI for:', p.id)
    navigate(`/assistants?agent=${p.id}`)
  }

  return (
    <div className="card persona-card">
      <div className="persona-hero">
        <img src={p.hero} alt={`${p.name} hero`} className="persona-hero-img" />
        <img src={p.avatar} alt={`${p.name} avatar`} className="persona-avatar" />
      </div>
      <div className="persona-body">
        <h3 className="mb-1">{p.name}</h3>
        <div className="text-sm mb-1" aria-label="role">{p.role}</div>
        <p className="text-sm">{p.summary}</p>
      </div>
      <div className="persona-actions">
        <button className="btn btn-primary" onClick={handleLaunchPanel} aria-label={`Launch ${p.name} panel`}>Launch Panel</button>
        {p.id === 'scorekeeper' ? (
          <button className="btn btn-success" onClick={() => navigate('/assistants?agent=scorekeeper&action=highscores')} aria-label="View High Scores">View High Scores</button>
        ) : (
          <button className="btn btn-success" onClick={handleChatWithAI} aria-label={`Chat with ${p.name}`}>Chat with AI</button>
        )}
      </div>
    </div>
  )
}

export default function Assistants() {
  const location = useLocation()
  const searchParams = new URLSearchParams(location.search)
  const contextValue = (searchParams.get('context') || '').trim()
  const noHandoff = searchParams.has('nohandoff')
  const showDeweyBadge = Boolean(contextValue) && !noHandoff

  // Stop any ongoing TTS when navigating between agents or away from panel
  useEffect(() => {
    stopSpeaking()
    return () => stopSpeaking()
  }, [location.pathname, location.search])
  const [showDeweyBadgeVisual, setShowDeweyBadgeVisual] = useState(showDeweyBadge)

  useEffect(() => {
    if (!showDeweyBadge) {
      setShowDeweyBadgeVisual(false)
      return
    }

    setShowDeweyBadgeVisual(true)
    const timer = setTimeout(() => {
      setShowDeweyBadgeVisual(false)
    }, 5000)

    return () => clearTimeout(timer)
  }, [showDeweyBadge, contextValue])

  // Check for both 'agent' and 'chat' parameters (for backwards compatibility)
  const agent = searchParams.get('agent') || searchParams.get('chat')

  const Badge = showDeweyBadge ? (
    <div
      className="aa-dewey-handoff-badge"
      aria-label="Context carried from Dewey"
      style={{
        position: 'fixed',
        top: 12,
        right: 16,
        background: '#0891b2',
        color: '#fff',
        padding: '4px 10px',
        borderRadius: '999px',
        fontSize: '12px',
        letterSpacing: '0.3px',
        zIndex: 1000,
        boxShadow: '0 2px 10px rgba(0,0,0,0.25)',
        pointerEvents: 'none',
        userSelect: 'none',
        opacity: showDeweyBadgeVisual ? 1 : 0,
        transition: 'opacity 220ms ease'

      }}
    >
      From Dewey
    </div>
  ) : null

  // If LED agent is requested, render the LED Blinky Panel
  if (agent === 'led' || agent === 'led-blinky') {
    return <>
      {Badge}
      <ErrorBoundary><Suspense fallback={<div className="loading-panel">Loading LED Blinky...</div>}><LEDBlinkyPanel /></Suspense></ErrorBoundary>
    </>
  }

  // If Light Guns agent is requested, render the Light Guns Panel
  if (agent === 'lightguns' || agent === 'light-guns' || agent === 'gunner') {
    return <>
      {Badge}
      <ErrorBoundary><Suspense fallback={<div className="loading-panel">Loading Gunner...</div>}><GunnerPanel /></Suspense></ErrorBoundary>
    </>
  }

  // Controller Chuck - direct panel (no shell wrapper, no tabs)
  if (
    agent === 'chuck' ||
    agent === 'controller-chuck' ||
    agent === 'controller_chuck' ||
    agent === 'controller'
  ) {
    return <>
      {Badge}
      <ErrorBoundary><Suspense fallback={<div className="loading-panel">Loading Controller Chuck...</div>}><ControllerChuckPanelRedesign /></Suspense></ErrorBoundary>
    </>
  }

  // Map generic interface keys directly to Chuck's panel (bypassing the tab shell)
  if (agent === 'interface' || agent === 'arcade-interface') {
    return <>
      {Badge}
      <ErrorBoundary><Suspense fallback={<div className="loading-panel">Loading Controller Chuck...</div>}><ControllerChuckPanelRedesign /></Suspense></ErrorBoundary>
    </>
  }

  // Legacy deprecated stub - basic device table only, kept for reference
  if (agent === 'chuck-legacy' || agent === 'controller-chuck-legacy' || agent === 'chuck-redesign') {
    return <>
      {Badge}
      <ErrorBoundary><Suspense fallback={<div className="loading-panel">Loading Controller Chuck...</div>}><ControllerChuckPanel /></Suspense></ErrorBoundary>
    </>
  }

  // Diagnostics-focused variants remain available via explicit aliases
  if (agent === 'controller-panel' || agent === 'controller-legacy' || agent === 'interface-legacy') {
    return <>
      {Badge}
      <ErrorBoundary><Suspense fallback={<div className="loading-panel">Loading Controller Panel...</div>}><ControllerPanel /></Suspense></ErrorBoundary>
    </>
  }

  // Controller Wizard is a separate panel for console emulators
  if (agent === 'controller-wizard' || agent === 'console_wizard') {
    return <>
      {Badge}
      <ErrorBoundary><Suspense fallback={<div className="loading-panel">Loading Console Wizard...</div>}><ConsoleWizardPanel /></Suspense></ErrorBoundary>
    </>
  }

  // Voice Assistant panel
  if (agent === 'voice') {
    return <>
      {Badge}
      <ErrorBoundary><Suspense fallback={<div className="loading-panel">Loading Voice Assistant...</div>}><VoicePanel /></Suspense></ErrorBoundary>
    </>
  }

  // LaunchBox panel (LoRa) - check for action parameter
  if (agent === 'launchbox' || agent === 'lora') {
    const action = searchParams.get('action')

    // If action=import, show the Content & Display Manager
    if (action === 'import') {
      return <>
        {Badge}
        <ErrorBoundary><Suspense fallback={<div className="loading-panel">Loading Content Manager...</div>}><ContentDisplayManager /></Suspense></ErrorBoundary>
      </>
    }

    // Default: show the LaunchBox panel (lazy loaded to avoid TDZ)
    return <>
      {Badge}
      <ErrorBoundary>
        <Suspense fallback={<div className="loading-panel">Loading LaunchBox...</div>}>
          <LaunchBoxPanel />
        </Suspense>
      </ErrorBoundary>
    </>
  }

  // System Health panel (Doc) - also handles diagnostics
  if (agent === 'health' || agent === 'system-health' || agent === 'doc' || agent === 'diagnostics' || agent === 'diag') {
    return <>
      {Badge}
      <ErrorBoundary><Suspense fallback={<div className="loading-panel">Loading System Health...</div>}><SystemHealthPanel /></Suspense></ErrorBoundary>
    </>
  }

  // Dewey AI Assistant panel
  if (agent === 'dewey') {
    return <>
      {Badge}
      <ErrorBoundary><Suspense fallback={<div className="loading-panel">Loading Dewey...</div>}><DeweyPanel /></Suspense></ErrorBoundary>
    </>
  }

  // ScoreKeeper panel (Sam / Historian) - check for action parameter
  if (agent === 'scorekeeper' || agent === 'sam' || agent === 'historian') {
    const action = searchParams.get('action')

    // If action=highscores, show the Cabinet High Scores panel
    if (action === 'highscores') {
      return <>
        {Badge}
        <ErrorBoundary><Suspense fallback={<div className="loading-panel">Loading High Scores...</div>}><CabinetHighScoresPanel /></Suspense></ErrorBoundary>
      </>
    }

    // Default: show the ScoreKeeper panel
    return <>
      {Badge}
      <ErrorBoundary><Suspense fallback={<div className="loading-panel">Loading ScoreKeeper...</div>}><ScoreKeeperPanel /></Suspense></ErrorBoundary>
    </>
  }

  // Otherwise render the normal assistants grid
  const rows = chunk(personas, 3)
  const rowThemes = ['row-blue', 'row-green', 'row-purple']
  return (
    <div className="assistants-page">
      {rows.map((row, idx) => (
        <section className={`persona-section ${rowThemes[idx] || ''}`} key={idx}>
          <div className="container">
            <div className="persona-grid">
              {row.map(p => (
                <PersonaCard key={p.id} p={p} />
              ))}
            </div>
          </div>
        </section>
      ))}
    </div>
  )
}

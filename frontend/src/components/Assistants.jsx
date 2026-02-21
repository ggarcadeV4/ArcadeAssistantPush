import React, { useEffect, useState, Suspense } from 'react'
import { useLocation, useNavigate } from 'react-router-dom'
import LEDBlinkyPanel from './led-blinky/LEDBlinkyPanelNew'
import ErrorBoundary from './ErrorBoundary'
import LightGunsPanel from '../panels/lightguns/LightGunsPanel'
import ControllerPanel from '../panels/controller/ControllerPanel'
import ControllerChuckPanel from '../panels/controller/ControllerChuckPanel'
import ConsoleWizardPanel from '../panels/console-wizard/ConsoleWizardPanel'
import VoicePanel from '../panels/voice/VoicePanel'
import SystemHealthPanel from '../panels/system-health/SystemHealthPanel'
// CIRCULAR DEPENDENCY FIX: Use React.lazy to break TDZ error
const LaunchBoxPanel = React.lazy(() => import('../panels/launchbox/LaunchBoxPanel'))
import ContentDisplayManager from '../panels/launchbox/ContentDisplayManager'
import DiagnosticsPanel from '../panels/diagnostics/DiagnosticsPanel'
import DeweyPanel from '../panels/dewey/DeweyPanel'
import ScoreKeeperPanel from '../panels/scorekeeper/ScoreKeeperPanel'
import CabinetHighScoresPanel from '../panels/scorekeeper/CabinetHighScoresPanel'
import { stopSpeaking } from '../services/ttsClient'

// ─── Command Center Agent Grid ─────────────────────────────────────────
const agentCards = [
  {
    id: 'lora',
    name: 'Launchbox Lora',
    subtitle: '3D Integration',
    glowClass: 'cc-glow-magenta',
    panelClass: 'cc-lora-panel',
    isPrimary: true,
    charImage: '/characters/lora-char.png',
    subtitleColor: '#d946ef',
  },
  {
    id: 'dewey',
    name: 'Dewey',
    subtitle: 'Cabinet Assistant',
    glowClass: 'cc-glow-blue',
    charImage: '/characters/dewey-char.png',
    subtitleColor: '#38bdf8',
  },
  {
    id: 'sam',
    name: 'Sam',
    subtitle: 'Scorekeeper',
    glowClass: 'cc-glow-blue',
    charImage: '/characters/sam-char.png',
    subtitleColor: '#38bdf8',
  },
  {
    id: 'voice',
    name: 'Vicki Voice',
    subtitle: 'Natural Input',
    glowClass: 'cc-glow-green',
    charImage: '/characters/vicki-char.png',
    subtitleColor: '#4ade80',
  },
  {
    id: 'chuck',
    name: 'Chuck',
    subtitle: 'Controller Core',
    glowClass: 'cc-glow-green',
    charImage: '/characters/chuck-char.png',
    subtitleColor: '#4ade80',
  },
  {
    id: 'controller-wizard',
    name: 'Wizard',
    subtitle: 'Mapping Logic',
    glowClass: 'cc-glow-green',
    charImage: '/characters/wizard-char.png',
    subtitleColor: '#4ade80',
  },
  {
    id: 'led-blinky',
    name: 'Blinky',
    subtitle: 'LED Dynamics',
    glowClass: 'cc-glow-magenta',
    charImage: '/characters/blinky-char.png',
    subtitleColor: '#d946ef',
  },
  {
    id: 'gunner',
    name: 'Gunner',
    subtitle: 'Aim & Sync',
    glowClass: 'cc-glow-magenta',
    charImage: '/characters/gunner-char.png',
    subtitleColor: '#d946ef',
  },
  {
    id: 'doc',
    name: 'Doc',
    subtitle: 'System Health',
    glowClass: 'cc-glow-magenta',
    charImage: '/characters/doc-char.png',
    subtitleColor: '#d946ef',
  },
]

function AgentCard({ agent }) {
  const navigate = useNavigate()
  const containerClass = [
    'cc-glass-container',
    agent.glowClass,
    agent.panelClass || '',
  ].filter(Boolean).join(' ')

  const handleOpen = () => {
    navigate(`/assistants?agent=${agent.id}`)
  }

  return (
    <div className={containerClass} onClick={handleOpen} role="button" tabIndex={0}
      onKeyDown={(e) => e.key === 'Enter' && handleOpen()}
      aria-label={`Open ${agent.name} panel`}
    >
      {/* Lora special bg glow */}
      {agent.isPrimary && <div className="cc-lora-bg-glow" />}

      {/* Character pop-out image */}
      <img
        src={agent.charImage}
        alt={agent.name}
        className={`cc-char-pop-out${agent.isPrimary ? ' cc-char-primary' : ''}`}
        loading="lazy"
      />

      {/* Bottom gradient overlay */}
      <div className="cc-card-gradient" />

      {/* Card info */}
      <div className="cc-card-info">
        <div className="cc-card-text">
          <h3 className="cc-card-name">{agent.name}</h3>
          <p className="cc-card-subtitle" style={{ color: agent.subtitleColor }}>
            {agent.subtitle}
          </p>
        </div>
        <button
          className={agent.isPrimary ? 'cc-pill-button-magenta' : 'cc-pill-button'}
          onClick={(e) => { e.stopPropagation(); handleOpen() }}
        >
          OPEN
        </button>
      </div>
    </div>
  )
}

function CommandCenterGrid() {
  const [time, setTime] = useState(new Date())

  useEffect(() => {
    const timer = setInterval(() => setTime(new Date()), 60000)
    return () => clearInterval(timer)
  }, [])

  return (
    <div className="cc-dashboard">
      {/* Header */}
      <header className="cc-header">
        <div className="cc-header-left">
          <h1 className="cc-title">ARCADE ASSISTANT</h1>
          <p className="cc-subtitle">
            <span className="cc-status-dot" />
            Master Command Dashboard • System Online
          </p>
        </div>
        <div className="cc-header-right">
          <div className="cc-header-user">
            <div className="cc-user-info">
              <span className="cc-user-name">Admin User</span>
              <span className="cc-user-level">Lvl 99 Operative</span>
            </div>
            <div className="cc-user-avatar">GG</div>
          </div>
        </div>
      </header>

      {/* 3x3 Agent Grid */}
      <div className="cc-agent-grid">
        {agentCards.map(agent => (
          <AgentCard key={agent.id} agent={agent} />
        ))}
      </div>

      {/* Footer Stats */}
      <footer className="cc-footer">
        <div className="cc-footer-stats">
          <div className="cc-stat">
            <span className="cc-stat-label">Total Games Indexed</span>
            <span className="cc-stat-value">7,170</span>
          </div>
          <div className="cc-stat">
            <span className="cc-stat-label">System Load</span>
            <span className="cc-stat-value cc-stat-green">
              14%
              <span className="cc-stat-bars">
                <span className="cc-bar cc-bar-1" />
                <span className="cc-bar cc-bar-2" />
                <span className="cc-bar cc-bar-3" />
              </span>
            </span>
          </div>
          <div className="cc-stat">
            <span className="cc-stat-label">Active Neural Nodes</span>
            <span className="cc-stat-value cc-stat-blue">09<span className="cc-stat-dim">/</span>09</span>
          </div>
        </div>
        <div className="cc-footer-status">
          <span className="cc-pulse-container">
            <span className="cc-pulse-ring" />
            <span className="cc-pulse-dot" />
          </span>
          <span className="cc-footer-status-text">Hyper-link protocols active</span>
        </div>
      </footer>
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
        boxShadow: '0 2px 10px rgba(0,0,0,0.25)'
      }}
    >
      From Dewey
    </div>
  ) : null

  // If LED agent is requested, render the LED Blinky Panel
  if (agent === 'led' || agent === 'led-blinky') {
    return <>
      {Badge}
      <ErrorBoundary><LEDBlinkyPanel /></ErrorBoundary>
    </>
  }

  // If Light Guns agent is requested, render the Light Guns Panel
  if (agent === 'lightguns' || agent === 'light-guns' || agent === 'gunner') {
    const showProfiles = searchParams.get('profiles') === '1'
    return <>
      {Badge}
      <ErrorBoundary><LightGunsPanel showProfilesSection={showProfiles} /></ErrorBoundary>
    </>
  }

  // If Controller Chuck (pin mapping) is requested
  if (agent === 'chuck' || agent === 'controller-chuck' || agent === 'controller_chuck') {
    return <>
      {Badge}
      <ErrorBoundary><ControllerChuckPanel /></ErrorBoundary>
    </>
  }

  // If Controller agent is requested, always show the Controller Panel (diagnostics)
  if (agent === 'controller') {
    return <>
      {Badge}
      <ErrorBoundary><ControllerPanel /></ErrorBoundary>
    </>
  }

  // Map generic interface keys to the Controller Panel layout
  if (agent === 'interface' || agent === 'arcade-interface') {
    return <>
      {Badge}
      <ErrorBoundary><ControllerPanel /></ErrorBoundary>
    </>
  }

  // Controller Wizard is a separate panel for console emulators
  if (agent === 'controller-wizard' || agent === 'console_wizard') {
    return <>
      {Badge}
      <ErrorBoundary><ConsoleWizardPanel /></ErrorBoundary>
    </>
  }

  // Voice Assistant panel
  if (agent === 'voice') {
    return <>
      {Badge}
      <ErrorBoundary><VoicePanel /></ErrorBoundary>
    </>
  }

  // LaunchBox panel (LoRa) - check for action parameter
  if (agent === 'launchbox' || agent === 'lora') {
    const action = searchParams.get('action')

    // If action=import, show the Content & Display Manager
    if (action === 'import') {
      return <>
        {Badge}
        <ErrorBoundary><ContentDisplayManager /></ErrorBoundary>
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
      <ErrorBoundary><SystemHealthPanel /></ErrorBoundary>
    </>
  }

  // Dewey AI Assistant panel
  if (agent === 'dewey') {
    return <>
      {Badge}
      <ErrorBoundary><DeweyPanel /></ErrorBoundary>
    </>
  }

  // ScoreKeeper panel (Sam / Historian) - check for action parameter
  if (agent === 'scorekeeper' || agent === 'sam' || agent === 'historian') {
    const action = searchParams.get('action')

    // If action=highscores, show the Cabinet High Scores panel
    if (action === 'highscores') {
      return <>
        {Badge}
        <ErrorBoundary><CabinetHighScoresPanel /></ErrorBoundary>
      </>
    }

    // Default: show the ScoreKeeper panel
    return <>
      {Badge}
      <ErrorBoundary><ScoreKeeperPanel /></ErrorBoundary>
    </>
  }

  // ─── Default: Render Command Center Dashboard ──────────────────────────
  return <CommandCenterGrid />
}

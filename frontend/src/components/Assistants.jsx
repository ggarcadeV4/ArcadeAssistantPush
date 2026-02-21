import React, { useEffect, Suspense } from 'react'
import { useLocation, useNavigate } from 'react-router-dom'
// CIRCULAR DEPENDENCY FIX: Use React.lazy to break TDZ error (same pattern as LaunchBox)
const LEDBlinkyPanel = React.lazy(() => import('./led-blinky/LEDBlinkyPanelNew'))
import ErrorBoundary from './ErrorBoundary'
// Old monolithic panel (preserved for rollback):
// import LightGunsPanel from '../panels/lightguns/LightGunsPanel'
import GunnerPanel from './gunner/GunnerPanel'
import ControllerPanel from '../panels/controller/ControllerPanel'
import ControllerChuckPanel from './ControllerChuckPanel'
import ControllerChuckPanelRedesign from '../panels/controller/ControllerChuckPanel'
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

// Dewey is accessed directly via /assistants?agent=dewey, not from the personas grid
const personas = []

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
        <button className="btn btn-success" onClick={handleChatWithAI} aria-label={`Chat with ${p.name}`}>Chat with AI</button>
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
    return <>
      {Badge}
      <ErrorBoundary><GunnerPanel /></ErrorBoundary>
    </>
  }

  // Controller Chuck default interface (full board + mappings + chat)
  if (
    agent === 'chuck' ||
    agent === 'controller-chuck' ||
    agent === 'controller_chuck' ||
    agent === 'controller' ||
    agent === 'interface' ||
    agent === 'arcade-interface'
  ) {
    return <>
      {Badge}
      <ErrorBoundary><ControllerPanel /></ErrorBoundary>
    </>
  }

  // Legacy minimal Chuck panel remains available via explicit aliases
  if (agent === 'chuck-legacy' || agent === 'controller-chuck-legacy') {
    return <>
      {Badge}
      <ErrorBoundary><ControllerChuckPanel /></ErrorBoundary>
    </>
  }

  // Redesigned Chuck panel remains available via explicit aliases
  if (agent === 'chuck-redesign' || agent === 'controller-chuck-redesign') {
    return <>
      {Badge}
      <ErrorBoundary><ControllerChuckPanelRedesign /></ErrorBoundary>
    </>
  }

  // Diagnostics-focused variants remain available via explicit aliases
  if (agent === 'controller-panel' || agent === 'controller-legacy' || agent === 'interface-legacy') {
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

  // Otherwise render the normal assistants grid
  const rows = chunk(personas, 3)
  return (
    <div className="assistants-page">
      {rows.map((row, idx) => (
        <section className="persona-section" key={idx}>
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

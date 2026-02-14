import React, { useEffect, useState } from 'react'
import { Link, useNavigate } from 'react-router-dom'

export default function Home() {
  const navigate = useNavigate()
  const [health, setHealth] = useState(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState(null)

  useEffect(() => {
    let active = true
    async function load() {
      try {
        const res = await fetch('/api/health')
        if (!res.ok) throw new Error(`HTTP ${res.status}`)
        const data = await res.json()
        if (active) setHealth(data)
      } catch (e) {
        if (active) setError(e.message)
      } finally {
        if (active) setLoading(false)
      }
    }
    load()
    return () => { active = false }
  }, [])

  const featured = [
    {
      key: 'launchbox-lora',
      badge: 'AI Agent: LoRa',
      title: 'LaunchBox LoRa',
      description: 'Launch retro titles, manage playlists, and import content sources.',
      heroVariant: 'launchbox',
      heroImage: '/lora-hero.png',
      actions: [
        { label: 'Open LaunchBox', href: '/assistants?agent=launchbox' },
        { label: 'Import Content', href: '/assistants?agent=launchbox&action=import', tone: 'primary' }
      ]
    },
    {
      key: 'dewey',
      badge: 'AI Agent: Dewey',
      title: 'Dewey AI Assistant',
      description: 'Ask questions, browse manuals, and get step-by-step repair help.',
      heroImage: '/dewey-hero.png',
      avatarImage: 'https://cdn.builder.io/api/v1/image/assets%2Fcc9e651c6f1243a198a541b6b2de51c9%2F7b415039c28c4e23ad685db43c8f98bb?format=webp&width=256',
      actions: [
        { label: 'Chat with Dewey', href: '/assistants?chat=dewey', tone: 'primary' },
        { label: 'Voice Mode', href: '/assistants?chat=dewey&voice=on' }
      ]
    },
    {
      key: 'historian',
      badge: 'AI Agent: Scores',
      title: 'Historian / Scorekeeper',
      description: 'Track high scores, manage tournaments, and archive run histories.',
      heroVariant: 'historian',
      heroImage: '/sam-hero.png',
      actions: [
        { label: 'View Scores', href: '/assistants?agent=scorekeeper&action=highscores', tone: 'primary' },
        { label: 'Tournaments', href: '/assistants?agent=scorekeeper&tournaments=1' }
      ]
    }
  ]

  const featuredGreen = [
    {
      key: 'voice-assistant',
      badge: 'AI Agent: Voice',
      title: 'Voice Assistant',
      description: 'Hands-free control, speech input, and text-to-speech.',
      heroVariant: 'voice',
      heroImage: '/voice-hero.png',
      actions: [
        { label: 'Open Voice', href: '/assistants?agent=voice', tone: 'primary' },
        { label: 'Mic Setup', href: '/mic-test' }
      ]
    },
    {
      key: 'arcade-interface',
      badge: 'Control Panel',
      title: 'Arcade Interface',
      description: 'Unified arcade controls, overlays, and quick actions.',
      heroVariant: 'interface',
      heroImage: '/chuck-hero.png',
      fallbackHeroImage: 'https://cdn.builder.io/api/v1/image/assets%2Fcc9e651c6f1243a198a541b6b2de51c9%2Fcebd44275f8143bbaa8e4cb5d52dee04?format=webp&width=800',
      actions: [
        { label: 'Open Controls', href: '/assistants?agent=interface', tone: 'primary' },
        { label: 'Settings', href: '/config' }
      ]
    },
    {
      key: 'controller-wizard',
      badge: 'AI Agent: Controls',
      title: 'Console Controller Wizard',
      description: 'Emulator profiles and console controller mapping (NES/SNES/etc).',
      heroVariant: 'controls',
      heroImage: '/wiz-hero.png',
      fallbackHeroImage: 'https://cdn.builder.io/api/v1/image/assets%2Fcc9e651c6f1243a198a541b6b2de51c9%2Fc4a38b3a1b854cd7bb3e741b9559b02f?format=webp&width=800',
      actions: [
        { label: 'Open Wizard', href: '/controller-wizard', tone: 'primary' }
      ]
    }
  ]

  const featuredPurple = [
    {
      key: 'led-blinky',
      badge: 'Lighting',
      title: 'LED Blinky',
      description: 'Game-aware button lighting and effects integrated with LaunchBox/MAME.',
      heroVariant: 'led',
      heroImage: '/led-hero.png',
      actions: [
        { label: 'Open LED Blinky', href: '/assistants?agent=led', tone: 'primary' },
        { label: 'Effects', href: '/assistants?agent=led&effects=1' }
      ]
    },
    {
      key: 'light-guns',
      badge: 'Calibration',
      title: 'Light Guns',
      description: 'Sinden/Gun4IR setup, auto-calibration, and CRT-friendly profiles.',
      heroVariant: 'lightguns',
      heroImage: '/lightguns-hero.png',
      actions: [
        { label: 'Setup Wizard', href: '/assistants?agent=lightguns', tone: 'primary' },
        { label: 'Profiles', href: '/assistants?agent=lightguns&profiles=1' }
      ]
    },
    {
      key: 'health-integration',
      badge: 'System',
      title: 'System Health Integration',
      description: 'Monitor drives, builds, emulators, and configs in real-time.',
      heroVariant: 'health',
      heroImage: '/doc-hero.png',
      actions: [
        { label: 'Open Health', href: '/assistants?agent=health', tone: 'primary' },
        { label: 'Settings', href: '/config' }
      ]
    }
  ]

  const panels = [
    {
      key: 'system-health',
      title: 'System Health',
      description: 'Gateway and Backend status overview',
      content: (
        <div>
          {loading && <div className="text-sm">Checking...</div>}
          {error && <div className="text-sm text-error">Error: {error}</div>}
          {health && (
            <div className="text-sm">
              <div className="mb-1"><span className={`status-indicator ${health.status === 'ok' ? 'status-ok' : 'status-error'}`} />Gateway: {health.gateway?.env || 'running'}</div>
              <div className="mb-1"><span className={`status-indicator ${health.fastapi?.connected ? 'status-ok' : 'status-error'}`} />FastAPI: {health.fastapi?.connected ? 'connected' : 'down'}</div>
              {health.fastapi?.details && (
                <div className="text-sm">Paths: {health.fastapi.details.sanctioned_paths?.join(', ')}</div>
              )}
            </div>
          )}
          <div className="mt-2"><Link className="btn btn-primary" to="/assistants?agent=health">Open Health</Link></div>
        </div>
      )
    },
    {
      key: 'mic-test',
      title: 'Microphone Test',
      description: 'Record and visualize audio input',
      action: <Link className="btn btn-primary" to="/mic-test">Open Mic Test</Link>
    },
    {
      key: 'config-manager',
      title: 'Config Manager',
      description: 'Inspect current policies and manifest',
      action: <Link className="btn btn-primary" to="/config">Open Config Manager</Link>
    },
    { key: 'controller-status', title: 'Controller Status', description: 'Verify controller input maps', footer: <div className="text-sm text-center">Coming via FastAPI input service</div> },
    { key: 'api-keys', title: 'API Keys', description: 'Manage AI and TTS keys securely', footer: <div className="text-sm text-center">Managed server-side</div> },
    { key: 'ai-test', title: 'AI Test', description: 'Ping AI gateway route', footer: <div className="text-sm text-center">Use /api/ai endpoints</div> },
    { key: 'debug', title: 'Debug Tools', description: 'Inspect logs and status', footer: <div className="text-sm text-center">See logs/agent_calls</div> },
    { key: 'session-log', title: 'Session Log', description: 'Append session entries to README', footer: <div className="text-sm text-center">POST /api/local/docs/session_log/append</div> },
    { key: 'screen-capture', title: 'Screen Capture', description: 'Capture current screen snapshot', footer: <div className="text-sm text-center">GET /api/local/screen/capture</div> },
    {
      key: 'assistant-dewey',
      title: 'Dewey AI Assistant',
      description: 'Knowledge-focused assistant for manuals, how-tos, and cabinet documentation.',
      content: (
        <div className="persona-card">
          <div className="persona-hero">
            <img src="https://cdn.builder.io/api/v1/image/assets%2Fcc9e651c6f1243a198a541b6b2de51c9%2F605b75621ffb4c908103019bba1c19b9?format=webp&width=800" alt="Dewey hero" className="persona-hero-img" />
            <img src="https://cdn.builder.io/api/v1/image/assets%2Fcc9e651c6f1243a198a541b6b2de51c9%2F7b415039c28c4e23ad685db43c8f98bb?format=webp&width=800" alt="Dewey avatar" className="persona-avatar" />
          </div>
          <div className="persona-body">
            <p className="text-sm">Answers from manuals, knowledgebase, and repair docs.</p>
          </div>
          <div className="persona-actions">
            <a className="btn btn-primary" href="/assistants">Launch Panel</a>
            <a className="btn btn-success" href="/assistants?chat=dewey">Chat with AI</a>
          </div>
        </div>
      )
    }
  ]

  return (
    <>
      <div className="container feature-row row-blue">
        <div className="grid feature-grid">
          {featured.map(f => (
            <div key={f.key} className="card feature-card">
              <div className="feature-header">
                <span className="chip chip-primary">{f.badge}</span>
              </div>
              <div className={`feature-hero ${f.heroVariant ? `hero-${f.heroVariant}` : ''}`}>
                {f.heroImage && (
                  <img
                    className="feature-hero-img"
                    src={f.heroImage}
                    alt={f.title}
                    onError={(e) => {
                      if (f.fallbackHeroImage && e.currentTarget.src !== f.fallbackHeroImage) {
                        e.currentTarget.src = f.fallbackHeroImage
                      }
                    }}
                  />
                )}
                {f.avatarImage && <img className="feature-avatar" src={f.avatarImage} alt="avatar" />}
              </div>
              <div className="feature-body">
                <h3 className="mb-2">{f.title}</h3>
                <p className="text-sm">{f.description}</p>
              </div>
              <div className="feature-actions">
                {f.actions.map((a, i) => (
                  <button
                    key={i}
                    type="button"
                    className={`btn ${a.tone === 'primary' ? 'btn-primary' : ''}`}
                    onClick={() => navigate(a.href)}
                  >
                    {a.label}
                  </button>
                ))}
              </div>
            </div>
          ))}
        </div>
      </div>

      <div className="container feature-row row-green">
        <div className="grid feature-grid">
          {featuredGreen.map(f => (
            <div key={f.key} className="card feature-card">
              <div className="feature-header">
                <span className="chip chip-primary">{f.badge}</span>
              </div>
              <div className={`feature-hero ${f.heroVariant ? `hero-${f.heroVariant}` : ''}`}>
                {f.heroImage && (
                  <img
                    className="feature-hero-img"
                    src={f.heroImage}
                    alt={f.title}
                    onError={(e) => {
                      if (f.fallbackHeroImage && e.currentTarget.src !== f.fallbackHeroImage) {
                        e.currentTarget.src = f.fallbackHeroImage
                      }
                    }}
                  />
                )}
              </div>
              <div className="feature-body">
                <h3 className="mb-2">{f.title}</h3>
                <p className="text-sm">{f.description}</p>
              </div>
              <div className="feature-actions">
                {f.actions.map((a, i) => (
                  <button
                    key={i}
                    type="button"
                    className={`btn ${a.tone === 'primary' ? 'btn-primary' : ''}`}
                    onClick={() => navigate(a.href)}
                  >
                    {a.label}
                  </button>
                ))}
              </div>
            </div>
          ))}
        </div>
      </div>

      <div className="container feature-row row-purple">
        <div className="grid feature-grid">
          {featuredPurple.map(f => (
            <div key={f.key} className="card feature-card">
              <div className="feature-header">
                <span className="chip chip-primary">{f.badge}</span>
              </div>
              <div className={`feature-hero ${f.heroVariant ? `hero-${f.heroVariant}` : ''}`}>
                {f.heroImage && (
                  <img
                    className="feature-hero-img"
                    src={f.heroImage}
                    alt={f.title}
                    onError={(e) => {
                      if (f.fallbackHeroImage && e.currentTarget.src !== f.fallbackHeroImage) {
                        e.currentTarget.src = f.fallbackHeroImage
                      }
                    }}
                  />
                )}
              </div>
              <div className="feature-body">
                <h3 className="mb-2">{f.title}</h3>
                <p className="text-sm">{f.description}</p>
              </div>
              <div className="feature-actions">
                {f.actions.map((a, i) => (
                  <button
                    key={i}
                    type="button"
                    className={`btn ${a.tone === 'primary' ? 'btn-primary' : ''}`}
                    onClick={() => navigate(a.href)}
                  >
                    {a.label}
                  </button>
                ))}
              </div>
            </div>
          ))}
        </div>
      </div>

    </>
  )
}

import React, { Suspense, lazy } from 'react'
import { Routes, Route, Navigate, useLocation } from 'react-router-dom'
import ErrorBoundary from './components/ErrorBoundary'

// Lazy load components for performance
const Home = lazy(() => import('./components/Home'))
const MicTest = lazy(() => import('./components/MicTest'))
const SystemHealth = lazy(() => import('./components/SystemHealth'))
const ConfigManager = lazy(() => import('./components/ConfigManager'))
const Assistants = lazy(() => import('./components/Assistants'))
const ConsoleWizardPanel = lazy(() => import('./panels/console-wizard/ConsoleWizardPanel'))
const MarqueeDisplay = lazy(() => import('./panels/marquee/MarqueeDisplay'))
const MarqueeDisplayV2 = lazy(() => import('./panels/marquee/MarqueeDisplayV2'))
const MarqueeText = lazy(() => import('./panels/marquee/MarqueeText'))
const MarqueeMedia = lazy(() => import('./panels/marquee/MarqueeMedia'))

// Loading fallback component
const PageLoader = () => (
  <div style={{
    display: 'flex',
    justifyContent: 'center',
    alignItems: 'center',
    height: '100vh',
    color: '#c8ff00',
    background: '#0a0e1a'
  }}>
    Loading...
  </div>
)

function App() {
  const location = useLocation()
  console.log('[App] React tree mounted - route:', location.pathname + location.search)
  const appClass = 'app theme-arcade'

  const requestOverlayHide = () => {
    try {
      const url = new URL(window.location.href)
      url.searchParams.set('__overlay_cmd', 'hide')
      url.searchParams.set('_', String(Date.now()))
      window.location.assign(url.toString())
    } catch {
      try { window.close() } catch { }
    }
  }

  // Dewey Concierge Mode: ?mode=overlay renders Dewey in a compact overlay
  const params = new URLSearchParams(location.search)
  const isOverlayMode = params.get('mode') === 'overlay'
  const overlayAgent = params.get('agent')

  if (isOverlayMode) {
    return (
      <Suspense fallback={<PageLoader />}>
        <div className={appClass} style={{ background: 'transparent', minHeight: '100vh', position: 'relative' }}>
          <button
            type="button"
            onClick={requestOverlayHide}
            aria-label="Close Dewey overlay"
            title="Close"
            style={{
              position: 'fixed',
              top: 10,
              right: 12,
              zIndex: 10000,
              width: 30,
              height: 30,
              borderRadius: 999,
              border: '1px solid rgba(120, 255, 240, 0.6)',
              background: 'rgba(6, 18, 28, 0.82)',
              color: '#a6fff5',
              fontSize: 20,
              lineHeight: '26px',
              cursor: 'pointer',
              boxShadow: '0 0 12px rgba(0, 240, 220, 0.25)'
            }}
          >
            ×
          </button>
          <ErrorBoundary>
            {overlayAgent
              ? <Assistants />
              : <Navigate to="/assistants?agent=dewey&mode=overlay" replace />}
          </ErrorBoundary>
        </div>
      </Suspense>
    )
  }

  return (
    <Suspense fallback={<PageLoader />}>
      <div className={appClass}>
        <main>
          <Suspense fallback={<PageLoader />}>
            <Routes>
              <Route path="/" element={<ErrorBoundary><Home /></ErrorBoundary>} />
              <Route path="/mic-test" element={<ErrorBoundary><MicTest /></ErrorBoundary>} />
              <Route path="/health" element={<Navigate to="/assistants?agent=health" replace />} />
              <Route path="/config" element={<ErrorBoundary><ConfigManager /></ErrorBoundary>} />
              <Route path="/assistants" element={<ErrorBoundary><Assistants /></ErrorBoundary>} />
              <Route path="/controller-wizard" element={<ErrorBoundary><ConsoleWizardPanel /></ErrorBoundary>} />
              <Route path="/console-wizard" element={<ErrorBoundary><ConsoleWizardPanel /></ErrorBoundary>} />
              <Route path="/marquee" element={<ErrorBoundary><MarqueeDisplay /></ErrorBoundary>} />
              <Route path="/marquee-v2" element={<ErrorBoundary><MarqueeDisplayV2 /></ErrorBoundary>} />
              <Route path="/marquee-text" element={<ErrorBoundary><MarqueeText /></ErrorBoundary>} />
              <Route path="/marquee-media" element={<ErrorBoundary><MarqueeMedia /></ErrorBoundary>} />
            </Routes>
          </Suspense>
        </main>
      </div>
    </Suspense>
  )
}

export default App
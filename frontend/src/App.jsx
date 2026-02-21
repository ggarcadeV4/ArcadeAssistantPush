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
const HotkeyOverlay = lazy(() => import('./components/HotkeyOverlay'))
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
  // Apply dark arcade theme to all pages
  const appClass = 'app theme-arcade'

  // Dewey Concierge Mode: ?mode=overlay renders only the chat component
  const params = new URLSearchParams(window.location.search)
  const isOverlayMode = params.get('mode') === 'overlay'

  if (isOverlayMode) {
    return (
      <Suspense fallback={<PageLoader />}>
        <div className={appClass} style={{ background: 'transparent' }}>
          <ErrorBoundary>
            <Home />
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
              {/* Console Wizard with Wiz - Step-by-step RetroArch configuration */}
              <Route path="/controller-wizard" element={<ErrorBoundary><ConsoleWizardPanel /></ErrorBoundary>} />
              <Route path="/console-wizard" element={<ErrorBoundary><ConsoleWizardPanel /></ErrorBoundary>} />
              <Route path="/marquee" element={<ErrorBoundary><MarqueeDisplay /></ErrorBoundary>} />
              <Route path="/marquee-v2" element={<ErrorBoundary><MarqueeDisplayV2 /></ErrorBoundary>} />
              <Route path="/marquee-text" element={<ErrorBoundary><MarqueeText /></ErrorBoundary>} />
              <Route path="/marquee-media" element={<ErrorBoundary><MarqueeMedia /></ErrorBoundary>} />
            </Routes>
          </Suspense>
        </main>
        {/* Global hotkey overlay (A key via backend hotkey manager) */}
        <Suspense fallback={null}>
          <HotkeyOverlay />
        </Suspense>
      </div>
    </Suspense>
  )
}

export default App



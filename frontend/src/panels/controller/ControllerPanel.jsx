/**
 * ControllerPanel.jsx — Smart Shell (Phase 2 Refactor)
 * ====================================================
 *
 * Thin routing shell that mounts either:
 *   • ControllerChuckPanel  — arcade cabinet hardware (Chuck persona)
 *   • ConsoleWizardPanel    — home console emulator config (Wizard persona)
 *
 * Persists the user's last-selected view via localStorage so returning
 * to the panel resumes where they left off.  Also honours ?view=chuck
 * or ?view=wizard query params for deep-linking.
 */

import React, { useState, useCallback, useMemo, Suspense } from 'react';
import { useLocation, useSearchParams } from 'react-router-dom';
import ControllerChuckPanel from './ControllerChuckPanel';
import ConsoleWizardPanel from '../../panels/console-wizard/ConsoleWizardPanel';
import ErrorBoundary from '../../components/ErrorBoundary';
import './controller-shell.css';

const VIEW_KEY = 'controller_active_view';
const VIEWS = {
  chuck: {
    id: 'chuck',
    label: '🕹️ Arcade Cabinet',
    subtitle: 'Chuck — Hardware & Pin Mapping',
    Component: ControllerChuckPanel,
  },
  wizard: {
    id: 'wizard',
    label: '🎮 Console Wizard',
    subtitle: 'Emulator Config & Profiles',
    Component: ConsoleWizardPanel,
  },
};

function resolveInitialView(searchParams) {
  const param = searchParams.get('view');
  if (param && VIEWS[param]) return param;
  try {
    const stored = localStorage.getItem(VIEW_KEY);
    if (stored && VIEWS[stored]) return stored;
  } catch { /* localStorage unavailable */ }
  return 'chuck'; // Default to arcade cabinet view
}

export default function ControllerPanel() {
  const [searchParams, setSearchParams] = useSearchParams();
  const [activeView, setActiveView] = useState(() => resolveInitialView(searchParams));

  const switchView = useCallback((viewId) => {
    if (!VIEWS[viewId]) return;
    setActiveView(viewId);
    try { localStorage.setItem(VIEW_KEY, viewId); } catch { /* noop */ }
    // Update URL without page reload
    const next = new URLSearchParams(searchParams);
    next.set('view', viewId);
    setSearchParams(next, { replace: true });
  }, [searchParams, setSearchParams]);

  const current = VIEWS[activeView] || VIEWS.chuck;

  return (
    <div className="controller-shell">
      {/* ── View Switcher Tabs ── */}
      <div className="controller-shell-tabs" role="tablist" aria-label="Controller view selector">
        {Object.values(VIEWS).map((v) => (
          <button
            key={v.id}
            role="tab"
            aria-selected={activeView === v.id}
            className={`controller-shell-tab ${activeView === v.id ? 'active' : ''}`}
            onClick={() => switchView(v.id)}
          >
            <span className="controller-shell-tab-label">{v.label}</span>
            <span className="controller-shell-tab-subtitle">{v.subtitle}</span>
          </button>
        ))}
      </div>

      {/* ── Active Panel ── */}
      <div className="controller-shell-content" role="tabpanel">
        <ErrorBoundary>
          <current.Component />
        </ErrorBoundary>
      </div>
    </div>
  );
}

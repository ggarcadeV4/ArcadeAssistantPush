/**
 * GamepadSetupOverlay.jsx
 *
 * Guided controller configuration for external gamepads (8BitDo, Xbox, PS4, Switch Pro).
 * Uses the Browser Gamepad API for real-time input detection — zero backend latency.
 *
 * Sections:
 *  1. Controller Detection & Profile Selection
 *  2. Digital Twin (interactive SVG mirror)
 *  3. Guided Button Mapping Wizard
 *  4. Analog Stick Calibration with deadzone adjustment
 *  5. RetroArch Config Preview / Apply
 */
import React, { useState, useEffect, useCallback, useRef, useMemo } from 'react';
import ControllerSVG from './ControllerSVG';
import './gamepad-setup.css';

/* ── Wizard sequence: the order in which we ask the user to press buttons ── */
const WIZARD_SEQUENCE = [
  { key: 'up',     label: 'D-Pad UP ↑',      group: 'dpad' },
  { key: 'down',   label: 'D-Pad DOWN ↓',    group: 'dpad' },
  { key: 'left',   label: 'D-Pad LEFT ←',    group: 'dpad' },
  { key: 'right',  label: 'D-Pad RIGHT →',   group: 'dpad' },
  { key: 'a',      label: 'A (South)',        group: 'face' },
  { key: 'b',      label: 'B (East)',         group: 'face' },
  { key: 'x',      label: 'X (West)',         group: 'face' },
  { key: 'y',      label: 'Y (North)',        group: 'face' },
  { key: 'l',      label: 'L1 (Left Bumper)', group: 'shoulder' },
  { key: 'r',      label: 'R1 (Right Bumper)',group: 'shoulder' },
  { key: 'zl',     label: 'L2 (Left Trigger)',group: 'trigger' },
  { key: 'zr',     label: 'R2 (Right Trigger)',group: 'trigger' },
  { key: 'select', label: 'SELECT / MINUS',   group: 'meta' },
  { key: 'start',  label: 'START / PLUS',     group: 'meta' },
  { key: 'l3',     label: 'L3 (Left Stick Click)',  group: 'stick' },
  { key: 'r3',     label: 'R3 (Right Stick Click)', group: 'stick' },
];

const API_BASE = '';
const deviceId = window.AA_DEVICE_ID || (() => {
  console.warn('[Wiz] window.AA_DEVICE_ID not available, ' +
    'falling back to cabinet-001. Cabinet identity may not be unique.');
  return 'cabinet-001';
})();
const HEADERS = (scope = 'state') => ({
  'Content-Type': 'application/json',
  'x-device-id': deviceId,
  'x-panel': 'console-wizard',
  'x-scope': scope,
});

export default function GamepadSetupOverlay({ onClose, fetchJSON }) {
  // ── State ─────────────────────────────────────────────
  const [phase, setPhase]           = useState('detect');  // detect | wizard | calibrate | complete
  const [profiles, setProfiles]     = useState([]);
  const [selectedProfile, setSelectedProfile] = useState(null);
  const [gamepadIndex, setGamepadIndex]       = useState(null);
  const [gamepadName, setGamepadName]         = useState('');
  const [connected, setConnected]   = useState(false);

  // Wizard state
  const [wizardStep, setWizardStep] = useState(0);
  const [mappings, setMappings]     = useState({});  // { key: buttonIndex }
  const [pressedButtons, setPressedButtons] = useState(new Set());

  // Calibration state
  const [stickPositions, setStickPositions] = useState({ lx: 0, ly: 0, rx: 0, ry: 0 });
  const [deadzone, setDeadzone]             = useState(0.15);

  // Config apply
  const [configPreview, setConfigPreview] = useState(null);
  const [applying, setApplying]           = useState(false);
  const [applyResult, setApplyResult]     = useState(null);
  const [prefsSaved, setPrefsSaved]       = useState(false);

  // Refs
  const rafRef    = useRef(null);
  const prevBtns  = useRef([]);

  // ── Load profiles from backend ────────────────────────
  useEffect(() => {
    const load = async () => {
      try {
        const fn = fetchJSON || (async (url) => {
          const r = await fetch(`${API_BASE}${url}`, { headers: HEADERS() });
          return r.json();
        });
        const data = await fn('/api/local/console/profiles');
        setProfiles(data?.profiles ?? []);
      } catch (err) {
        console.warn('[GamepadSetup] Failed to load profiles:', err);
      }
    };
    load();
  }, [fetchJSON]);

  // ── Load saved preferences on mount ───────────────────
  useEffect(() => {
    const loadPrefs = async () => {
      try {
        const fn = fetchJSON || (async (url) => {
          const r = await fetch(`${API_BASE}${url}`, { headers: HEADERS() });
          return r.json();
        });
        const data = await fn('/api/local/console/gamepad/preferences');
        if (data?.status === 'ok' && data.preferences) {
          const p = data.preferences;
          if (p.profile_id) setSelectedProfile(p.profile_id);
          if (p.mappings && Object.keys(p.mappings).length > 0) setMappings(p.mappings);
          if (typeof p.deadzone === 'number') setDeadzone(p.deadzone);
          console.log('[GamepadSetup] Loaded saved preferences:', p.profile_id);
        }
      } catch (err) {
        console.warn('[GamepadSetup] No saved preferences:', err);
      }
    };
    loadPrefs();
  }, [fetchJSON]);

  // ── Save preferences helper ───────────────────────────
  const savePreferences = useCallback(async (finalMappings, finalDeadzone) => {
    if (!selectedProfile) return;
    try {
      const fn = fetchJSON || (async (url, opts) => {
        const r = await fetch(`${API_BASE}${url}`, {
          method: opts?.method ?? 'GET',
          headers: HEADERS(opts?.scope ?? 'state'),
          body: opts?.body ? JSON.stringify(opts.body) : undefined,
        });
        return r.json();
      });
      const result = await fn('/api/local/console/gamepad/preferences', {
        method: 'POST',
        scope: 'config',
        body: {
          profile_id: selectedProfile,
          gamepad_name: gamepadName || null,
          mappings: finalMappings || mappings,
          deadzone: finalDeadzone ?? deadzone,
          calibration: {
            lx_range: [-1.0, 1.0],
            ly_range: [-1.0, 1.0],
            rx_range: [-1.0, 1.0],
            ry_range: [-1.0, 1.0],
          },
        },
      });
      if (result?.status === 'saved') {
        setPrefsSaved(true);
        console.log('[GamepadSetup] Preferences saved:', result);
      }
    } catch (err) {
      console.error('[GamepadSetup] Failed to save preferences:', err);
    }
  }, [selectedProfile, gamepadName, mappings, deadzone, fetchJSON]);

  // ── Browser Gamepad API polling loop ──────────────────
  const pollGamepad = useCallback(() => {
    const gamepads = navigator.getGamepads ? navigator.getGamepads() : [];
    let gp = null;

    // Use selected index, or find first connected
    if (gamepadIndex !== null) {
      gp = gamepads[gamepadIndex];
    } else {
      for (let i = 0; i < gamepads.length; i++) {
        if (gamepads[i]?.connected) {
          gp = gamepads[i];
          setGamepadIndex(i);
          setGamepadName(gp.id);
          setConnected(true);
          break;
        }
      }
    }

    if (!gp) {
      setConnected(false);
      rafRef.current = requestAnimationFrame(pollGamepad);
      return;
    }

    if (!connected) setConnected(true);

    // ─ Track pressed buttons ─
    const nowPressed = new Set();
    gp.buttons.forEach((btn, idx) => {
      if (btn.pressed) nowPressed.add(idx);
    });

    // Also check axes for D-pad (some controllers use axes for dpad)
    // Axis 6/7 or 9 are sometimes used for dpad on some controllers
    const axes = gp.axes;
    if (axes.length >= 2) {
      if (axes[0] < -0.5) nowPressed.add('axis-0-neg');
      if (axes[0] > 0.5) nowPressed.add('axis-0-pos');
      if (axes[1] < -0.5) nowPressed.add('axis-1-neg');
      if (axes[1] > 0.5) nowPressed.add('axis-1-pos');
    }

    // Detect newly pressed button (rising edge)
    const newPresses = [];
    nowPressed.forEach(idx => {
      if (!prevBtns.current.includes(idx)) newPresses.push(idx);
    });
    prevBtns.current = [...nowPressed];

    // Map button index to SVG button key for pressed-state highlight
    const svgPressed = new Set();
    // Reverse-lookup: if a mapped key has a buttonIndex that's in nowPressed, show it
    Object.entries(mappings).forEach(([key, btnIdx]) => {
      if (nowPressed.has(btnIdx)) svgPressed.add(key);
    });
    setPressedButtons(svgPressed);

    // ─ Stick positions for calibration ─
    if (axes.length >= 4) {
      setStickPositions({
        lx: axes[0] || 0,
        ly: axes[1] || 0,
        rx: axes[2] || 0,
        ry: axes[3] || 0,
      });
    }

    // ─ Wizard: capture button press ─
    if (phase === 'wizard' && newPresses.length > 0) {
      const step = WIZARD_SEQUENCE[wizardStep];
      if (step) {
        const capturedIdx = newPresses[0];
        setMappings(prev => ({ ...prev, [step.key]: capturedIdx }));
        // Auto-advance
        if (wizardStep < WIZARD_SEQUENCE.length - 1) {
          setWizardStep(s => s + 1);
        } else {
          // All buttons mapped → go to calibration
          setPhase('calibrate');
          // Auto-save preferences with the final mapping set
          const finalMap = { ...mappings, [step.key]: capturedIdx };
          savePreferences(finalMap, deadzone);
        }
      }
    }

    rafRef.current = requestAnimationFrame(pollGamepad);
  }, [gamepadIndex, connected, phase, wizardStep, mappings]);

  useEffect(() => {
    rafRef.current = requestAnimationFrame(pollGamepad);
    return () => {
      if (rafRef.current) cancelAnimationFrame(rafRef.current);
    };
  }, [pollGamepad]);

  // ── Gamepad connect/disconnect events ─────────────────
  useEffect(() => {
    const handleConnect = (e) => {
      console.log('[GamepadSetup] Gamepad connected:', e.gamepad.id);
      setGamepadIndex(e.gamepad.index);
      setGamepadName(e.gamepad.id);
      setConnected(true);
    };
    const handleDisconnect = (e) => {
      console.log('[GamepadSetup] Gamepad disconnected:', e.gamepad.id);
      if (e.gamepad.index === gamepadIndex) {
        setConnected(false);
        setGamepadIndex(null);
      }
    };
    window.addEventListener('gamepadconnected', handleConnect);
    window.addEventListener('gamepaddisconnected', handleDisconnect);
    return () => {
      window.removeEventListener('gamepadconnected', handleConnect);
      window.removeEventListener('gamepaddisconnected', handleDisconnect);
    };
  }, [gamepadIndex]);

  // ── Derived values ────────────────────────────────────
  const mappedSet = useMemo(() => new Set(Object.keys(mappings)), [mappings]);
  const currentWizStep = WIZARD_SEQUENCE[wizardStep] ?? null;
  const progress = (Object.keys(mappings).length / WIZARD_SEQUENCE.length) * 100;

  // ── Handlers ──────────────────────────────────────────
  const handleStartWizard = useCallback(() => {
    setMappings({});
    setWizardStep(0);
    setPhase('wizard');
  }, []);

  const handleSkip = useCallback(() => {
    if (wizardStep < WIZARD_SEQUENCE.length - 1) {
      setWizardStep(s => s + 1);
    } else {
      setPhase('calibrate');
    }
  }, [wizardStep]);

  const handleUndo = useCallback(() => {
    if (wizardStep > 0) {
      const prevStep = WIZARD_SEQUENCE[wizardStep - 1];
      setMappings(prev => {
        const next = { ...prev };
        delete next[prevStep.key];
        return next;
      });
      setWizardStep(s => s - 1);
    }
  }, [wizardStep]);

  const handleProfileSelect = useCallback((profileId) => {
    setSelectedProfile(profileId);
  }, []);

  const handlePreviewConfig = useCallback(async () => {
    if (!selectedProfile) return;
    try {
      const fn = fetchJSON || (async (url, opts) => {
        const r = await fetch(`${API_BASE}${url}`, {
          method: opts?.method ?? 'GET',
          headers: HEADERS(opts?.scope ?? 'state'),
          body: opts?.body ? JSON.stringify(opts.body) : undefined,
        });
        return r.json();
      });
      const data = await fn('/api/local/console/retroarch/config/preview', {
        method: 'POST',
        scope: 'state',
        body: {
          profile_id: selectedProfile,
          player: 1,
          mappings: Object.keys(mappings).length > 0 ? mappings : undefined,
          deadzone,
        },
      });
      setConfigPreview(data);
    } catch (err) {
      console.error('[GamepadSetup] Preview failed:', err);
    }
  }, [selectedProfile, fetchJSON]);

  const handleApplyConfig = useCallback(async () => {
    if (!selectedProfile) return;
    setApplying(true);
    try {
      const fn = fetchJSON || (async (url, opts) => {
        const r = await fetch(`${API_BASE}${url}`, {
          method: opts?.method ?? 'GET',
          headers: HEADERS(opts?.scope ?? 'state'),
          body: opts?.body ? JSON.stringify(opts.body) : undefined,
        });
        return r.json();
      });
      const data = await fn('/api/local/console/retroarch/config/apply', {
        method: 'POST',
        scope: 'config',
        body: {
          profile_id: selectedProfile,
          player: 1,
          mappings: Object.keys(mappings).length > 0 ? mappings : undefined,
          deadzone,
        },
      });
      setApplyResult(data);
      setPhase('complete');
    } catch (err) {
      console.error('[GamepadSetup] Apply failed:', err);
    } finally {
      setApplying(false);
    }
  }, [selectedProfile, fetchJSON]);

  const handleFinishCalibration = useCallback(() => {
    if (selectedProfile) {
      handlePreviewConfig();
    }
    setPhase('complete');
  }, [selectedProfile, handlePreviewConfig]);

  // ══════════════════════════════════════════════════════
  // RENDER
  // ══════════════════════════════════════════════════════

  // ── Detection / Profile Selection ─────────────────────
  if (phase === 'detect') {
    return (
      <div className="gp-setup">
        <div className="gp-header">
          <span className="gp-header__icon">🎮</span>
          <div className="gp-header__info">
            <div className="gp-header__title">
              Controller Setup
              <span className={`gp-status-dot gp-status-dot--${connected ? 'connected' : 'waiting'}`} />
            </div>
            <div className="gp-header__subtitle">
              {connected ? gamepadName : 'Plug in a controller or press a button to detect…'}
            </div>
          </div>
        </div>

        {connected && (
          <div className="gp-section" style={{ borderColor: 'rgba(34, 197, 94, 0.3)', background: 'linear-gradient(135deg, rgba(34, 197, 94, 0.08), rgba(16, 185, 129, 0.04))' }}>
            <div className="gp-section__title" style={{ color: '#22c55e' }}>
              <span className="material-symbols-outlined" style={{ fontSize: '1rem' }}>check_circle</span>
              Controller Detected: <strong style={{ color: '#bbf7d0' }}>{gamepadName}</strong>
            </div>
          </div>
        )}

        <div className="gp-section">
          <div className="gp-section__title">
            Select Your Controller Profile
          </div>
          <p style={{ color: '#94a3b8', fontSize: '0.85rem', margin: '0 0 0.75rem' }}>
            {connected
              ? 'Select the profile that matches your connected controller, then start the guided wizard.'
              : 'Choose a profile to preview the controller layout. Plug in your controller for full mapping.'}
          </p>
          <div className="gp-profiles">
            {profiles.map(p => (
              <button
                key={p.profile_id}
                className={`gp-profile-chip ${selectedProfile === p.profile_id ? 'gp-profile-chip--active' : ''}`}
                onClick={() => handleProfileSelect(p.profile_id)}
              >
                {p.name}
              </button>
            ))}
          </div>
        </div>

        {/* Show controller preview when profile selected */}
        {selectedProfile && (
          <div className="gp-twin" style={{ padding: '1rem' }}>
            <div className="gp-twin__svg-wrap" style={{ maxWidth: '420px' }}>
              <ControllerSVG
                activeButton={null}
                pressedButtons={pressedButtons}
                mappedButtons={mappedSet}
                profileId={selectedProfile}
              />
            </div>
          </div>
        )}

        <div style={{ display: 'flex', gap: '0.75rem', justifyContent: 'center' }}>
          <button
            className="gp-btn gp-btn--primary"
            onClick={handleStartWizard}
          >
            🧙‍♂️ Start Guided Wizard
          </button>
          {selectedProfile && (
            <button className="gp-btn gp-btn--amber" onClick={handlePreviewConfig}>
              Preview RetroArch Config
            </button>
          )}
        </div>
      </div>
    );
  }

  // ── Wizard Phase ──────────────────────────────────────
  if (phase === 'wizard') {
    return (
      <div className="gp-setup">
        <div className="gp-header">
          <span className="gp-header__icon">🧙‍♂️</span>
          <div className="gp-header__info">
            <div className="gp-header__title">
              Guided Button Mapping
              <span className={`gp-status-dot gp-status-dot--${connected ? 'connected' : 'disconnected'}`} />
            </div>
            <div className="gp-header__subtitle">{gamepadName}</div>
          </div>
          <div className="gp-header__actions">
            <button className="gp-btn" onClick={() => setPhase('detect')}>Cancel</button>
          </div>
        </div>

        <div className="gp-body">
          {/* Digital Twin */}
          <div className="gp-twin">
            <div className="gp-twin__svg-wrap">
              <ControllerSVG
                activeButton={currentWizStep?.key}
                pressedButtons={pressedButtons}
                mappedButtons={mappedSet}
                profileId={selectedProfile}
              />
            </div>

            {currentWizStep && (
              <div className="gp-wizard-prompt">
                <div className="gp-wizard-prompt__text">
                  Press <strong>{currentWizStep.label}</strong> on your controller
                </div>
                <div className="gp-wizard-prompt__progress">
                  <div className="gp-wizard-prompt__bar">
                    <div className="gp-wizard-prompt__fill" style={{ width: `${progress}%` }} />
                  </div>
                  <span className="gp-wizard-prompt__count">
                    {Object.keys(mappings).length} / {WIZARD_SEQUENCE.length}
                  </span>
                </div>
                <div className="gp-wizard-actions">
                  <button className="gp-btn" onClick={handleUndo} disabled={wizardStep === 0}>
                    ↩ Undo
                  </button>
                  <button className="gp-btn" onClick={handleSkip}>
                    Skip →
                  </button>
                </div>
              </div>
            )}
          </div>

          {/* Sidebar: mapping list */}
          <div className="gp-sidebar">
            <div className="gp-sidebar__title">Button Mappings</div>
            {WIZARD_SEQUENCE.map((step, idx) => {
              const mapped = mappings[step.key];
              const isCurrent = idx === wizardStep;
              const isDone = mapped !== undefined;
              return (
                <div
                  key={step.key}
                  className={`gp-mapping-row ${isCurrent ? 'gp-mapping-row--active' : ''} ${isDone ? 'gp-mapping-row--done' : ''}`}
                >
                  <span className="gp-mapping-row__label">{step.label}</span>
                  {isDone ? (
                    <span className="gp-mapping-row__value">btn {mapped}</span>
                  ) : isCurrent ? (
                    <span className="gp-mapping-row__pending">⏳ waiting…</span>
                  ) : (
                    <span className="gp-mapping-row__pending">—</span>
                  )}
                </div>
              );
            })}
          </div>
        </div>
      </div>
    );
  }

  // ── Calibration Phase ─────────────────────────────────
  if (phase === 'calibrate') {
    const scopeSize = 100;
    const clamp = (v) => Math.max(-1, Math.min(1, v));
    const toPx = (v) => ((clamp(v) + 1) / 2) * scopeSize;

    return (
      <div className="gp-setup">
        <div className="gp-header">
          <span className="gp-header__icon">🎯</span>
          <div className="gp-header__info">
            <div className="gp-header__title">
              Analog Stick Calibration
              <span className={`gp-status-dot gp-status-dot--${connected ? 'connected' : 'disconnected'}`} />
            </div>
            <div className="gp-header__subtitle">Move both sticks to verify tracking. Adjust deadzone as needed.</div>
          </div>
          <div className="gp-header__actions">
            <button className="gp-btn gp-btn--primary" onClick={handleFinishCalibration}>
              ✅ Finish
            </button>
          </div>
        </div>

        <div className="gp-body" style={{ gridTemplateColumns: '1fr' }}>
          <div className="gp-twin">
            <div className="gp-twin__svg-wrap" style={{ maxWidth: '400px' }}>
              <ControllerSVG
                activeButton={null}
                pressedButtons={pressedButtons}
                mappedButtons={mappedSet}
                profileId={selectedProfile}
              />
            </div>

            <div className="gp-calibration">
              <div className="gp-calibration__title">Live Analog Tracking</div>
              <div className="gp-sticks">
                {/* Left Stick */}
                <div className="gp-stick">
                  <div className="gp-stick__label">Left Stick</div>
                  <div className="gp-stick__scope">
                    <div
                      className="gp-stick__deadzone"
                      style={{
                        width: `${deadzone * scopeSize}px`,
                        height: `${deadzone * scopeSize}px`,
                      }}
                    />
                    <div
                      className="gp-stick__dot"
                      style={{
                        left: `${toPx(stickPositions.lx)}px`,
                        top: `${toPx(stickPositions.ly)}px`,
                      }}
                    />
                  </div>
                </div>

                {/* Right Stick */}
                <div className="gp-stick">
                  <div className="gp-stick__label">Right Stick</div>
                  <div className="gp-stick__scope">
                    <div
                      className="gp-stick__deadzone"
                      style={{
                        width: `${deadzone * scopeSize}px`,
                        height: `${deadzone * scopeSize}px`,
                      }}
                    />
                    <div
                      className="gp-stick__dot"
                      style={{
                        left: `${toPx(stickPositions.rx)}px`,
                        top: `${toPx(stickPositions.ry)}px`,
                      }}
                    />
                  </div>
                </div>
              </div>

              <div className="gp-deadzone">
                <span className="gp-deadzone__label">Deadzone</span>
                <input
                  type="range"
                  className="gp-deadzone__slider"
                  min="0"
                  max="50"
                  value={Math.round(deadzone * 100)}
                  onChange={e => setDeadzone(parseInt(e.target.value, 10) / 100)}
                />
                <span className="gp-deadzone__value">{Math.round(deadzone * 100)}%</span>
              </div>
            </div>
          </div>
        </div>
      </div>
    );
  }

  // ── Complete Phase ────────────────────────────────────
  if (phase === 'complete') {
    return (
      <div className="gp-setup">
        <div className="gp-complete">
          <div className="gp-complete__icon">✅</div>
          <div className="gp-complete__title">Controller Setup Complete!</div>
          <div className="gp-complete__sub">
            {Object.keys(mappings).length} of {WIZARD_SEQUENCE.length} buttons mapped
            {prefsSaved ? ' • Preferences saved' : ''}
            {applyResult ? ' • RetroArch config written' : ''}
          </div>
          <div className="gp-complete__actions">
            <button className="gp-btn" onClick={handleStartWizard}>
              🔄 Re-Map
            </button>
            {selectedProfile && !applyResult && (
              <button
                className="gp-btn gp-btn--primary"
                onClick={handleApplyConfig}
                disabled={applying}
              >
                {applying ? 'Applying…' : '📝 Apply RetroArch Config'}
              </button>
            )}
            {onClose && (
              <button className="gp-btn" onClick={onClose}>
                Done
              </button>
            )}
          </div>
        </div>

        {/* Show config preview if available */}
        {configPreview?.cfg_content && (
          <div className="gp-section">
            <div className="gp-section__title">RetroArch Config Preview</div>
            <pre style={{
              background: 'rgba(15, 23, 42, 0.8)',
              padding: '0.75rem',
              borderRadius: '8px',
              fontSize: '0.72rem',
              color: '#94a3b8',
              overflow: 'auto',
              maxHeight: '240px',
              fontFamily: "'Fira Code', monospace",
            }}>
              {configPreview.cfg_content}
            </pre>
          </div>
        )}
      </div>
    );
  }

  return null;
}

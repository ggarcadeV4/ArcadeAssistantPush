/**
 * MappingOverlay.jsx — Guided Controller Mapping Interface
 * ═══════════════════════════════════════════════════════════
 *
 * Visual overlay for step-by-step button mapping.
 * Calls the existing Learn Wizard backend API:
 *   /learn-wizard/start → /learn-wizard/confirm → /learn-wizard/save
 *
 * Inspired by the Stitch 8-BitDo Controller Mapping & Calibration Overlay.
 */

import React, { useState, useEffect, useCallback, useRef, memo } from 'react';
import './mapping-overlay.css';

// ── Constants ────────────────────────────────────────────────────────────────

const API_BASE = '/api/local/controller';
const STATE_HEADERS = { 'x-scope': 'state' };
const CONFIG_HEADERS = { 'Content-Type': 'application/json', 'x-scope': 'config', 'x-panel': 'mapping-overlay' };

/**
 * Player layouts matching the cabinet:
 * P1/P2 = 8 buttons + 4 dirs + start + coin = 14 each
 * P3/P4 = 4 buttons + 4 dirs + start + coin = 10 each
 */
const PLAYER_DEFS = [
  { id: 'p1', label: 'PLAYER 1', buttons: 8, row: 'front' },
  { id: 'p2', label: 'PLAYER 2', buttons: 8, row: 'front' },
  { id: 'p3', label: 'PLAYER 3', buttons: 4, row: 'back' },
  { id: 'p4', label: 'PLAYER 4', buttons: 4, row: 'back' },
];

const DIRECTIONS = ['up', 'down', 'left', 'right'];
const DIR_SYMBOLS = { up: '↑', down: '↓', left: '←', right: '→' };

/** Parse a control key like "p1.button3" → { player: 'p1', type: 'button', num: 3 } */
function parseControlKey(key) {
  if (!key || !key.includes('.')) return null;
  const [player, control] = key.split('.');
  if (DIRECTIONS.includes(control)) {
    return { player, type: 'direction', dir: control };
  }
  if (control === 'start') return { player, type: 'util', label: 'START' };
  if (control === 'coin') return { player, type: 'util', label: 'COIN' };
  const btnMatch = control.match(/^button(\d+)$/);
  if (btnMatch) return { player, type: 'button', num: parseInt(btnMatch[1], 10) };
  return { player, type: 'unknown', raw: control };
}

/** Get a friendly display name for a control key */
function displayName(key) {
  const parsed = parseControlKey(key);
  if (!parsed) return key;
  const pLabel = parsed.player.toUpperCase().replace('P', 'Player ');
  if (parsed.type === 'direction') return `${pLabel} — ${parsed.dir.toUpperCase()} ${DIR_SYMBOLS[parsed.dir]}`;
  if (parsed.type === 'button') return `${pLabel} — Button ${parsed.num}`;
  if (parsed.type === 'util') return `${pLabel} — ${parsed.label}`;
  return `${pLabel} — ${parsed.raw}`;
}


// ── Sub-components ──────────────────────────────────────────────────────────

/** Direction arrow indicator on the joystick graphic */
const DirArrow = memo(({ dir, state }) => (
  <div className={`mapping-dir-arrow ${dir} ${state}`}>
    {DIR_SYMBOLS[dir]}
  </div>
));
DirArrow.displayName = 'DirArrow';


/** Single arcade button circle */
const MappingButton = memo(({ num, state }) => (
  <div className={`mapping-btn ${state}`}>
    {num}
  </div>
));
MappingButton.displayName = 'MappingButton';


/** Utility button (START / COIN) */
const MappingUtilBtn = memo(({ label, state }) => (
  <div className={`mapping-util-btn ${state}`}>
    {label}
  </div>
));
MappingUtilBtn.displayName = 'MappingUtilBtn';


/** One player's control section */
const PlayerSection = memo(({ player, currentControl, captures }) => {
  const isActive = currentControl?.startsWith(player.id + '.');
  const parsed = parseControlKey(currentControl);

  /** Get state class for a specific control */
  const getState = (controlKey) => {
    if (currentControl === controlKey) return 'waiting';
    if (captures[controlKey]) return 'confirmed';
    return '';
  };

  // Button layout: P1/P2 = top row {1,2,3,7}, bottom row {4,5,6,8}
  //                P3/P4 = top row {1,2}, bottom row {3,4}
  const topRow = player.buttons === 8 ? [1, 2, 3, 7] : [1, 2];
  const bottomRow = player.buttons === 8 ? [4, 5, 6, 8] : [3, 4];

  return (
    <div className={`mapping-player-section ${isActive ? 'active-player' : ''}`}>
      <div className="mapping-player-label">{player.label}</div>

      <div className="mapping-joystick-area">
        {/* Joystick graphic with directional arrows */}
        <div className="mapping-joystick">
          {DIRECTIONS.map((dir) => (
            <DirArrow
              key={dir}
              dir={dir}
              state={getState(`${player.id}.${dir}`)}
            />
          ))}
        </div>

        {/* Button grid */}
        <div className="mapping-buttons-grid">
          <div className="mapping-buttons-row">
            {topRow.map((n) => (
              <MappingButton
                key={n}
                num={n}
                state={getState(`${player.id}.button${n}`)}
              />
            ))}
          </div>
          <div className="mapping-buttons-row">
            {bottomRow.map((n) => (
              <MappingButton
                key={n}
                num={n}
                state={getState(`${player.id}.button${n}`)}
              />
            ))}
          </div>
        </div>
      </div>

      {/* START / COIN utility buttons */}
      <div className="mapping-util-row">
        <MappingUtilBtn label="START" state={getState(`${player.id}.start`)} />
        <MappingUtilBtn label="COIN"  state={getState(`${player.id}.coin`)} />
      </div>
    </div>
  );
});
PlayerSection.displayName = 'PlayerSection';


// ── Main Overlay Component ──────────────────────────────────────────────────

export default function MappingOverlay({ onClose, onSaved, latestInput }) {
  // Wizard state
  const [phase, setPhase]           = useState('idle'); // idle | mapping | complete | saving | saved | error
  const [currentControl, setCurrentControl] = useState(null);
  const [currentIndex, setCurrentIndex]     = useState(0);
  const [totalControls, setTotalControls]   = useState(0);
  const [captures, setCaptures]     = useState({});
  const [chuckPrompt, setChuckPrompt] = useState('');
  const [encoderInfo, setEncoderInfo] = useState(null);
  const [modeWarning, setModeWarning] = useState(null);
  const [saveResult, setSaveResult]   = useState(null);
  const [errorMsg, setErrorMsg]       = useState(null);

  // Track latestInput changes to auto-confirm
  const lastProcessedInput = useRef(null);

  // ── Start the wizard ──────────────────────────────────────────────────────

  const startWizard = useCallback(async () => {
    setPhase('mapping');
    setErrorMsg(null);
    try {
      const res = await fetch(`${API_BASE}/learn-wizard/start?players=4&buttons=8&auto_advance=true`, {
        method: 'POST',
        headers: STATE_HEADERS,
      });
      if (!res.ok) throw new Error(`Start failed (${res.status})`);
      const data = await res.json();

      setCurrentControl(data.current_control);
      setCurrentIndex(data.current_index || 0);
      setTotalControls(data.total_controls || 0);
      setChuckPrompt(data.chuck_prompt || '');
      if (data.detected_board) {
        setEncoderInfo({ board: data.detected_board, mode: data.detected_mode });
      }
      if (data.mode_warning) setModeWarning(data.mode_warning);
    } catch (err) {
      setPhase('error');
      setErrorMsg(err.message);
    }
  }, []);

  // Auto-start on mount
  useEffect(() => {
    startWizard();
    // Cleanup: stop wizard if overlay closes
    return () => {
      fetch(`${API_BASE}/learn-wizard/stop`, { method: 'POST', headers: STATE_HEADERS }).catch(() => {});
    };
  }, [startWizard]);

  // ── Auto-confirm when a new input arrives ─────────────────────────────────

  useEffect(() => {
    if (phase !== 'mapping' || !latestInput) return;

    // Deduplicate
    const inputKey = latestInput.timestamp || latestInput.pin || JSON.stringify(latestInput);
    if (lastProcessedInput.current === inputKey) return;
    lastProcessedInput.current = inputKey;

    // Auto-confirm
    confirmCapture();
  }, [latestInput, phase]); // eslint-disable-line react-hooks/exhaustive-deps

  // ── Wizard actions ────────────────────────────────────────────────────────

  const confirmCapture = useCallback(async () => {
    if (phase !== 'mapping') return;
    try {
      const res = await fetch(`${API_BASE}/learn-wizard/confirm`, {
        method: 'POST',
        headers: STATE_HEADERS,
      });
      if (!res.ok) throw new Error(`Confirm failed (${res.status})`);
      const data = await res.json();

      if (data.status === 'complete') {
        setPhase('complete');
        setCaptures(data.captures || {});
        setChuckPrompt(data.chuck_prompt || 'All controls mapped!');
        setCurrentControl(null);
      } else if (data.status === 'next') {
        // Update captures with the one just confirmed
        setCaptures((prev) => ({
          ...prev,
          [data.captured]: { confirmed: true },
        }));
        setCurrentControl(data.next_control);
        setCurrentIndex(data.current_index);
        setChuckPrompt(data.chuck_prompt || '');
      } else if (data.status === 'no_capture') {
        setChuckPrompt(data.chuck_prompt || 'Press the button again.');
      }
    } catch (err) {
      setErrorMsg(err.message);
    }
  }, [phase]);

  const skipControl = useCallback(async () => {
    try {
      const res = await fetch(`${API_BASE}/learn-wizard/skip`, {
        method: 'POST',
        headers: STATE_HEADERS,
      });
      if (!res.ok) return;
      const data = await res.json();

      if (data.status === 'complete') {
        setPhase('complete');
        setCurrentControl(null);
        setChuckPrompt(data.chuck_prompt || '');
      } else {
        setCurrentControl(data.next_control);
        setChuckPrompt(data.chuck_prompt || '');
      }
    } catch (_) { /* swallow */ }
  }, []);

  const undoCapture = useCallback(async () => {
    try {
      const res = await fetch(`${API_BASE}/learn-wizard/undo`, {
        method: 'POST',
        headers: STATE_HEADERS,
      });
      if (!res.ok) return;
      const data = await res.json();

      if (data.status === 'undone') {
        setCurrentControl(data.current_control);
        setCurrentIndex(data.current_index);
        setChuckPrompt(data.chuck_prompt || '');
        // Remove the undone capture
        setCaptures((prev) => {
          const next = { ...prev };
          delete next[data.current_control];
          return next;
        });
      } else {
        setChuckPrompt(data.chuck_prompt || '');
      }
    } catch (_) { /* swallow */ }
  }, []);

  const saveAllMappings = useCallback(async () => {
    setPhase('saving');
    try {
      const res = await fetch(`${API_BASE}/learn-wizard/save`, {
        method: 'POST',
        headers: CONFIG_HEADERS,
      });
      if (!res.ok) throw new Error(`Save failed (${res.status})`);
      const data = await res.json();
      setSaveResult(data);
      setPhase('saved');
      setChuckPrompt(data.chuck_prompt || `Saved ${data.controls_mapped} controls!`);
      onSaved?.(data);
    } catch (err) {
      setPhase('error');
      setErrorMsg(err.message);
    }
  }, [onSaved]);

  const handleClose = useCallback(() => {
    fetch(`${API_BASE}/learn-wizard/stop`, { method: 'POST', headers: STATE_HEADERS }).catch(() => {});
    onClose?.();
  }, [onClose]);


  // ── Render ────────────────────────────────────────────────────────────────

  const progressPct = totalControls > 0 ? (currentIndex / totalControls) * 100 : 0;
  const capturedCount = Object.keys(captures).length;

  return (
    <div className="mapping-overlay">

      {/* Header */}
      <div className="mapping-header">
        <h2>Map Controls</h2>
        <div style={{ display: 'flex', alignItems: 'center', gap: '0.8rem' }}>
          {encoderInfo && (
            <span className={`mapping-encoder-badge ${modeWarning ? 'warning' : ''}`}>
              {encoderInfo.board} ({encoderInfo.mode})
            </span>
          )}
          <button className="mapping-close-btn" onClick={handleClose}>✕ Close</button>
        </div>
      </div>

      {/* Error state */}
      {phase === 'error' && (
        <div className="mapping-instruction" style={{ borderColor: 'rgba(255,80,80,0.4)' }}>
          <div className="mapping-instruction-text" style={{ color: '#ff6b6b' }}>
            ⚠️ {errorMsg || 'Something went wrong'}
          </div>
          <button className="mapping-action-btn" onClick={startWizard} style={{ marginTop: '0.8rem' }}>
            Retry
          </button>
        </div>
      )}

      {/* Idle / loading */}
      {phase === 'idle' && (
        <div className="mapping-instruction">
          <div className="mapping-instruction-text">Starting wizard…</div>
        </div>
      )}

      {/* Mapping phase */}
      {phase === 'mapping' && (
        <>
          {/* Instruction banner */}
          <div className="mapping-instruction">
            <div className="mapping-instruction-text">
              Press <span className="control-name">{displayName(currentControl)}</span> on your panel
            </div>
            {modeWarning && (
              <div style={{ fontSize: '0.75rem', color: '#ffb347', marginTop: '0.4rem' }}>
                ⚠ {modeWarning}
              </div>
            )}
          </div>

          {/* Progress bar */}
          <div className="mapping-progress-wrap">
            <div className="mapping-progress-bar">
              <div className="mapping-progress-fill" style={{ width: `${progressPct}%` }} />
            </div>
            <div className="mapping-progress-label">
              <span>{capturedCount} captured</span>
              <span>{currentIndex + 1} / {totalControls}</span>
            </div>
          </div>
        </>
      )}

      {/* Complete phase */}
      {(phase === 'complete' || phase === 'saving' || phase === 'saved') && (
        <div className="mapping-complete-banner">
          {phase === 'saving' ? (
            <>
              <h3><span className="mapping-saving-spinner" /> Saving…</h3>
              <p>Writing to controls.json and cascading to emulators…</p>
            </>
          ) : phase === 'saved' ? (
            <>
              <h3>✅ Controls Saved!</h3>
              <p>{chuckPrompt}</p>
              {saveResult?.mame_config?.status === 'success' && (
                <p style={{ color: '#4cff8e', fontSize: '0.8rem', marginTop: '0.3rem' }}>
                  ✓ MAME config updated
                </p>
              )}
              {saveResult?.teknoparrot_config?.profiles_updated > 0 && (
                <p style={{ color: '#4cff8e', fontSize: '0.8rem' }}>
                  ✓ TeknoParrot: {saveResult.teknoparrot_config.profiles_updated} profiles updated
                </p>
              )}
            </>
          ) : (
            <>
              <h3>🎉 All Controls Mapped!</h3>
              <p>{capturedCount} controls captured. Click "Save All" to write changes.</p>
            </>
          )}
        </div>
      )}

      {/* Control panel visualization */}
      {(phase === 'mapping' || phase === 'complete') && (
        <div className="mapping-panel">
          <div className="mapping-players-grid">
            {/* Back row: P3, P4 */}
            {PLAYER_DEFS.filter((p) => p.row === 'back').map((player) => (
              <PlayerSection
                key={player.id}
                player={player}
                currentControl={currentControl}
                captures={captures}
              />
            ))}
            {/* Front row: P1, P2 */}
            {PLAYER_DEFS.filter((p) => p.row === 'front').map((player) => (
              <PlayerSection
                key={player.id}
                player={player}
                currentControl={currentControl}
                captures={captures}
              />
            ))}
          </div>
        </div>
      )}

      {/* Action buttons */}
      <div className="mapping-actions">
        {phase === 'mapping' && (
          <>
            <button className="mapping-action-btn" onClick={skipControl}>Skip</button>
            <button className="mapping-action-btn" onClick={undoCapture}>Undo</button>
            <button className="mapping-action-btn" onClick={handleClose}>Cancel</button>
          </>
        )}
        {phase === 'complete' && (
          <>
            <button className="mapping-action-btn" onClick={undoCapture}>← Back</button>
            <button className="mapping-action-btn primary" onClick={saveAllMappings}>
              Save All ({capturedCount} controls)
            </button>
          </>
        )}
        {phase === 'saved' && (
          <button className="mapping-action-btn primary" onClick={handleClose}>
            Done — Close
          </button>
        )}
      </div>
    </div>
  );
}

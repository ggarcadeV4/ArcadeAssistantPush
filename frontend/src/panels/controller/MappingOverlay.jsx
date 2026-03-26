import React, { memo, useCallback, useEffect, useMemo, useRef, useState } from 'react';
import { ExecutionCard } from '../controller/ExecutionCard';
import './mapping-overlay.css';

const API_BASE = '/api/local/controller';

function resolveDeviceId() {
  if (typeof window !== 'undefined' && window.AA_DEVICE_ID) {
    return window.AA_DEVICE_ID;
  }
  return 'controller_chuck';
}

function buildHeaders(scope = 'state') {
  return {
    'Content-Type': 'application/json',
    'x-scope': scope,
    'x-panel': 'mapping-overlay',
    'x-device-id': resolveDeviceId(),
  };
}

const PLAYER_DEFS = [
  { id: 'p1', label: 'PLAYER 1', buttons: 8, row: 'front' },
  { id: 'p2', label: 'PLAYER 2', buttons: 8, row: 'front' },
  { id: 'p3', label: 'PLAYER 3', buttons: 4, row: 'back' },
  { id: 'p4', label: 'PLAYER 4', buttons: 4, row: 'back' },
];

const DIRECTIONS = ['up', 'down', 'left', 'right'];
const DIR_SYMBOLS = { up: '^', down: 'v', left: '<', right: '>' };

function parseControlKey(key) {
  if (!key || !key.includes('.')) return null;
  const [player, control] = key.split('.');
  if (DIRECTIONS.includes(control)) {
    return { player, type: 'direction', dir: control };
  }
  if (control === 'start') return { player, type: 'util', label: 'START' };
  if (control === 'coin') return { player, type: 'util', label: 'COIN' };
  const buttonMatch = control.match(/^button(\d+)$/);
  if (buttonMatch) return { player, type: 'button', num: Number(buttonMatch[1]) };
  return { player, type: 'unknown', raw: control };
}

function displayName(key) {
  const parsed = parseControlKey(key);
  if (!parsed) return key || 'Unknown control';
  const playerLabel = parsed.player.toUpperCase().replace('P', 'Player ');
  if (parsed.type === 'direction') {
    return `${playerLabel} ${parsed.dir.toUpperCase()} ${DIR_SYMBOLS[parsed.dir]}`;
  }
  if (parsed.type === 'button') {
    return `${playerLabel} Button ${parsed.num}`;
  }
  if (parsed.type === 'util') {
    return `${playerLabel} ${parsed.label}`;
  }
  return `${playerLabel} ${parsed.raw}`;
}

const DirArrow = memo(function DirArrow({ dir, state }) {
  return <div className={`mapping-dir-arrow ${dir} ${state}`}>{DIR_SYMBOLS[dir]}</div>;
});

const MappingButton = memo(function MappingButton({ num, state }) {
  return <div className={`mapping-btn ${state}`}>{num}</div>;
});

const MappingUtilBtn = memo(function MappingUtilBtn({ label, state }) {
  return <div className={`mapping-util-btn ${state}`}>{label}</div>;
});

const PlayerSection = memo(function PlayerSection({
  player,
  currentControl,
  captures,
  flashedControl,
}) {
  const isActive = currentControl?.startsWith(`${player.id}.`);

  const getState = (controlKey) => {
    if (controlKey === currentControl) return 'waiting';
    if (controlKey === flashedControl) return 'just-confirmed';
    if (captures[controlKey]) return 'confirmed';
    return '';
  };

  const topRow = player.buttons === 8 ? [1, 2, 3, 7] : [1, 2];
  const bottomRow = player.buttons === 8 ? [4, 5, 6, 8] : [3, 4];

  return (
    <div className={`mapping-player-section ${isActive ? 'active-player' : ''}`}>
      <div className="mapping-player-label">{player.label}</div>

      <div className="mapping-joystick-area">
        <div className="mapping-joystick">
          {DIRECTIONS.map((dir) => (
            <DirArrow
              key={dir}
              dir={dir}
              state={getState(`${player.id}.${dir}`)}
            />
          ))}
        </div>

        <div className="mapping-buttons-grid">
          <div className="mapping-buttons-row">
            {topRow.map((num) => (
              <MappingButton
                key={num}
                num={num}
                state={getState(`${player.id}.button${num}`)}
              />
            ))}
          </div>
          <div className="mapping-buttons-row">
            {bottomRow.map((num) => (
              <MappingButton
                key={num}
                num={num}
                state={getState(`${player.id}.button${num}`)}
              />
            ))}
          </div>
        </div>
      </div>

      <div className="mapping-util-row">
        <MappingUtilBtn label="START" state={getState(`${player.id}.start`)} />
        <MappingUtilBtn label="COIN" state={getState(`${player.id}.coin`)} />
      </div>
    </div>
  );
});

export default function MappingOverlay({
  onClose,
  onSaved,
  latestInput,
  playerMode = '4p',
}) {
  const [phase, setPhase] = useState('idle');
  const [sessionId, setSessionId] = useState(null);
  const [buttonOrder, setButtonOrder] = useState([]);
  const [currentControl, setCurrentControl] = useState(null);
  const [currentIndex, setCurrentIndex] = useState(0);
  const [totalControls, setTotalControls] = useState(0);
  const [captures, setCaptures] = useState({});
  const [flashedControl, setFlashedControl] = useState(null);
  const [chuckPrompt, setChuckPrompt] = useState('');
  const [encoderInfo, setEncoderInfo] = useState(null);
  const [modeWarning, setModeWarning] = useState(null);
  const [commitResult, setCommitResult] = useState(null);
  const [errorMsg, setErrorMsg] = useState(null);
  const [executeLoading, setExecuteLoading] = useState(false);

  const lastProcessedInputRef = useRef(null);
  const sessionIdRef = useRef(null);

  useEffect(() => {
    sessionIdRef.current = sessionId;
  }, [sessionId]);

  const cancelWizard = useCallback(async (activeSessionId = null) => {
    const target = activeSessionId || sessionIdRef.current;
    if (!target) return;
    try {
      await fetch(`${API_BASE}/wizard/cancel`, {
        method: 'POST',
        headers: buildHeaders('state'),
        body: JSON.stringify({ session_id: target }),
      });
    } catch {
      // Best effort cleanup only.
    }
  }, []);

  const startWizard = useCallback(async () => {
    setPhase('mapping');
    setErrorMsg(null);
    setCommitResult(null);
    setCaptures({});
    setFlashedControl(null);
    lastProcessedInputRef.current = null;

    try {
      const res = await fetch(`${API_BASE}/wizard/start`, {
        method: 'POST',
        headers: buildHeaders('state'),
        body: JSON.stringify({ player_mode: playerMode }),
      });
      if (!res.ok) throw new Error(`Start failed (${res.status})`);
      const data = await res.json();

      setSessionId(data.session_id || null);
      setButtonOrder(Array.isArray(data.buttons) ? data.buttons : []);
      setCurrentControl(data.next_button || data.next || null);
      setCurrentIndex(data.progress || 0);
      setTotalControls(data.total || data.buttons?.length || 0);
      setChuckPrompt(data.chuck_prompt || 'Press the highlighted control on your panel.');
      if (data.detected_board) {
        setEncoderInfo({ board: data.detected_board, mode: data.detected_mode });
      } else {
        setEncoderInfo(null);
      }
      setModeWarning(data.mode_warning || null);
    } catch (err) {
      setPhase('error');
      setErrorMsg(err.message || 'Failed to start mapping wizard.');
    }
  }, [playerMode]);

  useEffect(() => {
    startWizard();
    return () => {
      cancelWizard();
    };
  }, [cancelWizard, startWizard]);

  const captureControl = useCallback(async (inputEvent) => {
    if (phase !== 'mapping' || !sessionId || !currentControl || !inputEvent) return;

    try {
      const res = await fetch(`${API_BASE}/wizard/capture`, {
        method: 'POST',
        headers: buildHeaders('state'),
        body: JSON.stringify({
          session_id: sessionId,
          button_name: currentControl,
          input_event: inputEvent,
        }),
      });
      if (!res.ok) throw new Error(`Capture failed (${res.status})`);
      const data = await res.json();

      setCaptures((prev) => ({
        ...prev,
        [currentControl]: {
          pin: inputEvent.pin,
          keycode: inputEvent.keycode,
          source_id: inputEvent.source_id,
          confirmed: true,
        },
      }));
      setFlashedControl(currentControl);
      window.setTimeout(() => {
        setFlashedControl((prev) => (prev === currentControl ? null : prev));
      }, 600);

      if (data.status === 'complete') {
        setPhase('complete');
        setCurrentControl(null);
        setCurrentIndex(data.progress || totalControls);
        setChuckPrompt('All controls mapped. Review the proposal and press EXECUTE to commit.');
        return;
      }

      if (data.status === 'captured') {
        setCurrentControl(data.next_button || data.next || null);
        setCurrentIndex(data.progress || 0);
        setChuckPrompt(
          `Captured ${displayName(data.button_name)}. Press ${displayName(data.next_button)} next.`,
        );
      }
    } catch (err) {
      setErrorMsg(err.message || 'Capture failed.');
      setPhase('error');
    }
  }, [currentControl, phase, sessionId, totalControls]);

  useEffect(() => {
    if (phase !== 'mapping' || !latestInput || !sessionId || !currentControl) return;

    const inputKey = latestInput.timestamp || latestInput.pin || JSON.stringify(latestInput);
    if (lastProcessedInputRef.current === inputKey) return;
    lastProcessedInputRef.current = inputKey;

    captureControl(latestInput);
  }, [captureControl, currentControl, latestInput, phase, sessionId]);

  const skipControl = useCallback(() => {
    if (!sessionId || !currentControl) return;

    (async () => {
      try {
        const res = await fetch(`${API_BASE}/wizard/capture`, {
          method: 'POST',
          headers: buildHeaders('state'),
          body: JSON.stringify({
            session_id: sessionId,
            button_name: currentControl,
            skip: true,
          }),
        });
        if (!res.ok) throw new Error(`Skip failed (${res.status})`);
        const data = await res.json();

        setCaptures((prev) => ({
          ...prev,
          [currentControl]: { skipped: true },
        }));

        if (data.status === 'complete') {
          setPhase('complete');
          setCurrentControl(null);
          setCurrentIndex(data.progress || totalControls);
          setChuckPrompt('All controls processed. Review the proposal and press EXECUTE to commit.');
          return;
        }

        setCurrentControl(data.next_button || data.next || null);
        setCurrentIndex(data.progress || currentIndex + 1);
        setChuckPrompt(`Skipped ${displayName(currentControl)}. Move to ${displayName(data.next_button)}.`);
      } catch (err) {
        setErrorMsg(err.message || 'Skip failed.');
        setPhase('error');
      }
    })();
  }, [currentControl, currentIndex, sessionId, totalControls]);

  const undoCapture = useCallback(async () => {
    if (!sessionId) return;

    try {
      const res = await fetch(`${API_BASE}/wizard/capture`, {
        method: 'POST',
        headers: buildHeaders('state'),
        body: JSON.stringify({ session_id: sessionId, rollback: true }),
      });
      if (!res.ok) throw new Error(`Undo failed (${res.status})`);
      const data = await res.json();

      if (data.status === 'rolled_back') {
        setPhase('mapping');
        setCurrentControl(data.next_button || data.button_name || null);
        setCurrentIndex(data.progress || 0);
        setChuckPrompt(`Rolled back ${displayName(data.button_name)}. Press it again.`);
        setCaptures((prev) => {
          const next = { ...prev };
          delete next[data.button_name];
          return next;
        });
      } else {
        setChuckPrompt('Nothing to undo.');
      }
    } catch (err) {
      setErrorMsg(err.message || 'Undo failed.');
      setPhase('error');
    }
  }, [sessionId]);

  const commitWizard = useCallback(async () => {
    if (!sessionId) return;

    setExecuteLoading(true);
    setPhase('committing');

    try {
      const res = await fetch(`${API_BASE}/wizard/commit`, {
        method: 'POST',
        headers: buildHeaders('config'),
        body: JSON.stringify({ session_id: sessionId }),
      });
      if (!res.ok) throw new Error(`Commit failed (${res.status})`);
      const data = await res.json();
      if (data.status !== 'committed') {
        throw new Error(data.message || 'Commit failed.');
      }

      setCommitResult(data);
      setPhase('committed');
      setChuckPrompt(`Saved ${data.controls_mapped} controls and prepared the cascade.`);
      setSessionId(null);
      onSaved?.(data);
    } catch (err) {
      setErrorMsg(err.message || 'Commit failed.');
      setPhase('error');
      throw err;
    } finally {
      setExecuteLoading(false);
    }
  }, [onSaved, sessionId]);

  const handleClose = useCallback(() => {
    if (phase !== 'committed') {
      cancelWizard();
    }
    onClose?.();
  }, [cancelWizard, onClose, phase]);

  const progressPct = totalControls > 0 ? (currentIndex / totalControls) * 100 : 0;
  const capturedCount = Object.keys(captures).length;
  const visiblePlayers = useMemo(
    () => PLAYER_DEFS.filter((player) => playerMode === '4p' || player.row === 'front'),
    [playerMode],
  );
  const executionProposal = useMemo(() => ({
    display: Object.entries(captures)
      .map(([controlKey, capture]) => `${displayName(controlKey)} = GPIO ${capture?.pin ?? 'skip'}`)
      .join('; '),
    payload: { session_id: sessionId },
  }), [captures, sessionId]);

  return (
    <div className="mapping-overlay">
      <div className="mapping-header">
        <h2>Guided Control Wizard</h2>
        <div style={{ display: 'flex', alignItems: 'center', gap: '0.8rem' }}>
          {encoderInfo && (
            <span className={`mapping-encoder-badge ${modeWarning ? 'warning' : ''}`}>
              {encoderInfo.board} ({encoderInfo.mode})
            </span>
          )}
          <button className="mapping-close-btn" onClick={handleClose}>Close</button>
        </div>
      </div>

      {phase === 'error' && (
        <div className="mapping-instruction" style={{ borderColor: 'rgba(255,80,80,0.4)' }}>
          <div className="mapping-instruction-text" style={{ color: '#ff6b6b' }}>
            {errorMsg || 'Something went wrong.'}
          </div>
          <button className="mapping-action-btn" onClick={startWizard} style={{ marginTop: '0.8rem' }}>
            Retry
          </button>
        </div>
      )}

      {phase === 'idle' && (
        <div className="mapping-instruction">
          <div className="mapping-instruction-text">Starting wizard...</div>
        </div>
      )}

      {phase === 'mapping' && (
        <>
          <div className="mapping-instruction">
            <div className="mapping-instruction-text">
              Press <span className="control-name">{displayName(currentControl)}</span> on your panel
            </div>
            {modeWarning && (
              <div style={{ fontSize: '0.75rem', color: '#FFA500', marginTop: '0.4rem' }}>
                Warning: {modeWarning}
              </div>
            )}
          </div>

          <div className="mapping-progress-wrap">
            <div className="mapping-progress-bar">
              <div className="mapping-progress-fill" style={{ width: `${progressPct}%` }} />
            </div>
            <div className="mapping-progress-label">
              <span>{capturedCount}/{totalControls} mapped</span>
              <span>{Math.min(currentIndex + 1, totalControls)} / {totalControls}</span>
            </div>
          </div>
        </>
      )}

      {(phase === 'complete' || phase === 'committing' || phase === 'committed') && (
        <div className="mapping-complete-banner">
          {phase === 'committing' ? (
            <>
              <h3><span className="mapping-saving-spinner" /> Saving...</h3>
              <p>Writing to controls.json and cascading to emulators...</p>
            </>
          ) : phase === 'committed' ? (
            <>
              <h3>Controls Saved</h3>
              <p>{chuckPrompt}</p>
              {commitResult?.cascade_result?.triggered && (
                <p style={{ color: '#00FF00', fontSize: '0.8rem', marginTop: '0.3rem' }}>
                  Cascade queued: {commitResult.cascade_result.job_id}
                </p>
              )}
            </>
          ) : (
            <>
              <h3>All Controls Mapped</h3>
              <p>Review the summary below and press EXECUTE to commit.</p>
            </>
          )}
        </div>
      )}

      {(phase === 'mapping' || phase === 'complete' || phase === 'committing' || phase === 'committed') && (
        <div className="mapping-panel">
          <div className="mapping-players-grid">
            {visiblePlayers.filter((player) => player.row === 'back').map((player) => (
              <PlayerSection
                key={player.id}
                player={player}
                currentControl={currentControl}
                captures={captures}
                flashedControl={flashedControl}
              />
            ))}
            {visiblePlayers.filter((player) => player.row === 'front').map((player) => (
              <PlayerSection
                key={player.id}
                player={player}
                currentControl={currentControl}
                captures={captures}
                flashedControl={flashedControl}
              />
            ))}
          </div>
        </div>
      )}

      {phase === 'complete' && executionProposal.display && (
        <ExecutionCard
          proposal={executionProposal}
          onExecute={commitWizard}
          onCancel={handleClose}
          loading={executeLoading}
        />
      )}

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
            <button className="mapping-action-btn" onClick={undoCapture}>Back</button>
            <button className="mapping-action-btn" onClick={handleClose}>Cancel</button>
          </>
        )}
        {phase === 'committed' && (
          <button className="mapping-action-btn primary" onClick={handleClose}>
            Done - Close
          </button>
        )}
      </div>
    </div>
  );
}

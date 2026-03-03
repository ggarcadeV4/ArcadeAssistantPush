/**
 * ControllerChuckPanel.jsx
 * Visual arcade cabinet controller layout for Chuck persona.
 *
 * BUTTON LAW (doctrine — do not change):
 *   Top row:    1  2  3  7      (P1/P2: 8-button)
 *   Bottom row: 4  5  6  8
 *   P3/P4: 4-button only → top: 1  2  |  bottom: 4  5
 *
 * PHYSICAL LAYOUT (matches cabinet top-to-bottom):
 *   Row 1: Player 3 | Player 4   ← 4-button (back players)
 *   Row 2: Player 1 | Player 2   ← 8-button (front players)
 */

import React, {
  useState, useEffect, useCallback, useMemo, useRef, memo
} from 'react';
import { controllerAIChat } from '../../services/controllerAI';
import { logChatHistory } from '../../services/supabaseClient';
import { useInputDetection } from '../../hooks/useInputDetection';
import { speak, stopSpeaking } from '../../services/ttsClient';
import { useProfileContext } from '../../context/ProfileContext';
import {
  fetchBaseline,
  fetchCascadeStatus,
  getCascadePreference,
  requestCascade,
  setCascadePreference,
} from './apiHelpers';
import { EngineeringBaySidebar } from '../_kit/EngineeringBaySidebar';
import { chuckContextAssembler } from './chuckContextAssembler';
import { chuckChips } from './chuckChips';
import './controller-chuck.css';
import './chuck-sidebar.css';
import '../_kit/EngineeringBaySidebar.css';

// ── Constants ───────────────────────────────────────────────────────────────
const API_BASE = '/api/local/controller';
const HARDWARE_API = '/api/local/hardware';
const CHUCK_VOICE_ID = 'f5HLTX707KIM4SzJYzSz';

const CHUCK_GREET = "Yo! Chuck here. Let's get this cabinet wired up right.";

/** Chuck persona config for EngineeringBaySidebar */
const CHUCK_PERSONA = {
  id: 'chuck',
  name: 'CHUCK',
  icon: '⚙️',
  icon2: '🕹️',
  accentColor: '#FBBF24',
  accentGlow: 'rgba(251,191,36,0.35)',
  scannerLabel: 'ANALYZING...',
  voiceProfile: 'chuck',
  emptyHint: 'Ask Chuck about controller mappings, GPIO, or arcade setup.',
  chips: chuckChips,
};

/** Flame SVG background — matches the physical panel aesthetic */
const FlameSVG = memo(() => (
  <div className="chuck-flames" aria-hidden="true">
    <svg viewBox="0 0 1200 80" preserveAspectRatio="none" xmlns="http://www.w3.org/2000/svg">
      <defs>
        <linearGradient id="fg1" x1="0" y1="1" x2="0" y2="0">
          <stop offset="0%" stopColor="#ff6600" stopOpacity="0.9" />
          <stop offset="100%" stopColor="#ff2200" stopOpacity="0" />
        </linearGradient>
        <linearGradient id="fg2" x1="0" y1="1" x2="0" y2="0">
          <stop offset="0%" stopColor="#ff4400" stopOpacity="0.7" />
          <stop offset="100%" stopColor="#ff8800" stopOpacity="0" />
        </linearGradient>
      </defs>
      {/* Flame tongues across the bottom */}
      <path d="M0,80 C30,50 50,30 80,60 C100,80 120,20 150,55 C170,75 200,10 230,50 C255,80 280,30 310,60 L310,80Z" fill="url(#fg1)" />
      <path d="M280,80 C310,45 340,20 370,55 C395,78 420,15 450,50 C475,78 510,25 540,58 C565,78 590,30 620,60 L620,80Z" fill="url(#fg2)" />
      <path d="M580,80 C615,42 645,18 680,52 C705,75 735,12 765,48 C792,76 820,22 855,56 C878,76 905,28 935,62 L935,80Z" fill="url(#fg1)" />
      <path d="M880,80 C920,40 950,15 990,50 C1015,74 1045,10 1075,46 C1100,72 1130,20 1160,55 C1180,70 1200,40 1200,60 L1200,80Z" fill="url(#fg2)" />
    </svg>
  </div>
));
FlameSVG.displayName = 'FlameSVG';

/** Button layout per player type */
const LAYOUT_8BTN = {
  topRow: [1, 2, 3, 7],
  bottomRow: [4, 5, 6, 8],
};
const LAYOUT_4BTN = {
  topRow: [1, 2],
  bottomRow: [3, 4],
};

/** Player meta — visual order top→bottom = back→front of cabinet */
const PLAYERS_4P = [
  { id: 'p3', label: 'PLAYER 3', cls: 'p3', layout: LAYOUT_4BTN },
  { id: 'p4', label: 'PLAYER 4', cls: 'p4', layout: LAYOUT_4BTN },
  { id: 'p1', label: 'PLAYER 1', cls: 'p1', layout: LAYOUT_8BTN },
  { id: 'p2', label: 'PLAYER 2', cls: 'p2', layout: LAYOUT_8BTN },
];

const PLAYERS_2P = [
  { id: 'p1', label: 'PLAYER 1', cls: 'p1', layout: LAYOUT_8BTN },
  { id: 'p2', label: 'PLAYER 2', cls: 'p2', layout: LAYOUT_8BTN },
];

// ── Sub-components ───────────────────────────────────────────────────────────

/** 8-way joystick graphic with ↑↓←→ mapping overlay */
const DIRS = ['up', 'down', 'left', 'right'];
const DIR_PATHS = {
  up: 'M18,5 L25,17 H11 Z',
  down: 'M18,31 L25,19 H11 Z',
  left: 'M5,18 L17,11 V25 Z',
  right: 'M31,18 L19,11 V25 Z',
};

const JoystickGraphic = memo(({ onDirClick, mappingDir, confirmedDir }) => (
  <div className="chuck-joystick-wrap">
    <div className="chuck-joystick">
      <div className="chuck-joystick-diag" />
      <div className="chuck-joystick-inner" />

      {/* Directional arrow overlay — clickable SVG zones */}
      <svg
        className="chuck-dir-overlay"
        viewBox="0 0 36 36"
        xmlns="http://www.w3.org/2000/svg"
        onClick={(e) => e.stopPropagation()}
      >
        {DIRS.map((dir) => (
          <path
            key={dir}
            d={DIR_PATHS[dir]}
            data-dir={dir}
            className={
              `chuck-dir-arrow`
              + (mappingDir === dir ? ' waiting' : '')
              + (confirmedDir?.dir === dir ? ' confirmed' : '')
            }
            onClick={(e) => { e.stopPropagation(); onDirClick?.(dir); }}
          />
        ))}
      </svg>

      {/* Confirmation badge for confirmed direction */}
      {confirmedDir && (
        <div className="chuck-mapped-badge dir">
          ✓ GPIO {confirmedDir.pin}
        </div>
      )}
    </div>
    <span className="chuck-joystick-label">8-WAY</span>
  </div>
));
JoystickGraphic.displayName = 'JoystickGraphic';


/** Single arcade button circle */
const ArcadeButton = memo(({ num, pinLabel, pressed, waiting, confirmed, onClick }) => (
  <div
    className="chuck-btn-circle"
    data-btn={String(num)}
    onClick={onClick}
    title={`Button ${num}${pinLabel ? ` — Pin ${pinLabel}` : ''}`}
  >
    <div className={`chuck-btn-circle-face${pressed ? ' pressed' : ''}${waiting ? ' waiting' : ''}${confirmed ? ' confirmed' : ''}`}>
      {num}
    </div>
    {confirmed && (
      <div className="chuck-mapped-badge">✓ GPIO {confirmed.pin}</div>
    )}
    <span className={`chuck-btn-pin ${pinLabel ? 'mapped' : ''}`}>
      {pinLabel || '—'}
    </span>
  </div>
));
ArcadeButton.displayName = 'ArcadeButton';


/** START / SELECT utility button */
const UtilButton = memo(({ label, pinLabel }) => (
  <div className="chuck-util-btn">
    <div className="chuck-util-btn-face">{label}</div>
    <span className="chuck-util-label">{pinLabel || '—'}</span>
  </div>
));
UtilButton.displayName = 'UtilButton';

/** One player card (joystick + button grid + utilities) */
const PlayerCard = memo(({ player, mapping, pressedKeys, onButtonClick, playerMode, activePlayer, focusOrigin, isReturning, onReturnEnd, onFocus, latestInput }) => {
  const { id, label, cls, layout } = player;
  const cardRef = useRef(null);

  // Determine focus state
  const isFocused = activePlayer === id;
  const isDimmed = activePlayer !== null && activePlayer !== id && !isReturning;
  const focusClass = isFocused
    ? ' focus-active'
    : isReturning
      ? ' focus-returning'
      : isDimmed
        ? ' focus-dimmed'
        : '';

  const getPin = useCallback((controlKey) => {
    const entry = mapping?.[`${id}.${controlKey}`];
    return entry?.pin != null ? String(entry.pin) : null;
  }, [id, mapping]);

  const isPressed = useCallback((controlKey) => {
    return pressedKeys?.has(`${id}.${controlKey}`) ?? false;
  }, [id, pressedKeys]);

  const handleBtn = useCallback((num) => {
    onButtonClick?.(`${id}.button${num}`);
  }, [id, onButtonClick]);

  // Directional mapping state — null means idle
  const [mappingDir, setMappingDir] = useState(null);
  // Button mapping state — which button number is waiting for cabinet input
  const [mappingButton, setMappingButton] = useState(null);

  // Confirmation state — set briefly after a physical press is received
  const [confirmedButton, setConfirmedButton] = useState(null); // { num, pin }
  const [confirmedDir, setConfirmedDir] = useState(null); // { dir, pin }

  // ── Listen for incoming hardware signal ──────────────────────────
  // When this card is in a waiting state and latestInput arrives,
  // fire the confirmation animation and clear the waiting state.
  useEffect(() => {
    if (!latestInput || (!mappingButton && !mappingDir)) return;

    const pin = latestInput.pin ?? latestInput.key ?? '?';

    if (mappingButton !== null) {
      setConfirmedButton({ num: mappingButton, pin });
      setMappingButton(null);
      const t = setTimeout(() => setConfirmedButton(null), 1800);
      return () => clearTimeout(t);
    }
    if (mappingDir !== null) {
      setConfirmedDir({ dir: mappingDir, pin });
      setMappingDir(null);
      const t = setTimeout(() => setConfirmedDir(null), 1800);
      return () => clearTimeout(t);
    }
  }, [latestInput]); // eslint-disable-line react-hooks/exhaustive-deps

  const handleDirClick = useCallback((dir) => {
    setMappingDir((prev) => (prev === dir ? null : dir));
    setMappingButton(null);
    setConfirmedButton(null);
    onFocus?.(id, cardRef.current?.getBoundingClientRect());
  }, [id, onFocus]);

  const handleMapBtn = useCallback((num, e) => {
    e.stopPropagation();
    setMappingButton((prev) => (prev === num ? null : num));
    setMappingDir(null);
    setConfirmedDir(null);
    onFocus?.(id, cardRef.current?.getBoundingClientRect());
  }, [id, onFocus]);

  // CSS vars for FLIP entry + return-to-grid exit — apply to both active & returning
  const flipStyle = (isFocused || isReturning) && focusOrigin ? {
    '--flip-x': `${focusOrigin.dx}px`,
    '--flip-y': `${focusOrigin.dy}px`,
    '--flip-w': `${focusOrigin.w}px`,
  } : {};

  return (
    <div
      ref={cardRef}
      className={`chuck-player-card ${cls}${playerMode === '2p' ? ' mode-2p' : ''}${focusClass}`}
      style={flipStyle}
      onAnimationEnd={(e) => {
        if (e.animationName === 'return-to-grid') onReturnEnd?.();
      }}
      onClick={() => {
        if (mappingDir || mappingButton) {
          setMappingDir(null);
          setMappingButton(null);
          return;
        }
        onFocus?.(isFocused ? null : id, isFocused ? null : cardRef.current?.getBoundingClientRect());
      }}
    >
      <div className="chuck-player-header">
        <span className="chuck-player-badge">{label}</span>
        <span className="chuck-player-status">GPIO BANK {cls.toUpperCase()}</span>
      </div>

      <div className="chuck-controller-layout">
        <JoystickGraphic
          onDirClick={handleDirClick}
          mappingDir={mappingDir}
          confirmedDir={confirmedDir}
        />

        <div className="chuck-button-area">
          {/* Top row */}
          <div className="chuck-button-row">
            {layout.topRow.map((n) => (
              <ArcadeButton
                key={n}
                num={n}
                pinLabel={getPin(`button${n}`)}
                pressed={isPressed(`button${n}`)}
                waiting={mappingButton === n}
                confirmed={confirmedButton?.num === n ? confirmedButton : null}
                onClick={(e) => handleMapBtn(n, e)}
              />
            ))}
          </div>
          {/* Bottom row */}
          <div className="chuck-button-row">
            {layout.bottomRow.map((n) => (
              <ArcadeButton
                key={n}
                num={n}
                pinLabel={getPin(`button${n}`)}
                pressed={isPressed(`button${n}`)}
                waiting={mappingButton === n}
                confirmed={confirmedButton?.num === n ? confirmedButton : null}
                onClick={(e) => handleMapBtn(n, e)}
              />
            ))}
          </div>

          {/* START / SELECT */}
          <div className="chuck-utility-row">
            <UtilButton label="SEL" pinLabel={getPin('coin')} />
            <UtilButton label="START" pinLabel={getPin('start')} />
          </div>
        </div>
      </div>
    </div>
  );
});
PlayerCard.displayName = 'PlayerCard';

// ── Main Panel Component ─────────────────────────────────────────────────────
export default function ControllerChuckPanel() {
  const { currentUser } = useProfileContext();

  // ── State ──────────────────────────────────────────────────────────────────
  const [mapping, setMapping] = useState({});
  const [hasPending, setHasPending] = useState(false);
  const [loading, setLoading] = useState(true);
  const [submitting, setSubmitting] = useState(false);

  // Board / device scan
  const [board, setBoard] = useState(null);
  const [scanLoading, setScanLoading] = useState(false);

  // AI chat
  const [messages, setMessages] = useState([
    { id: 'welcome', role: 'chuck', content: CHUCK_GREET }
  ]);
  const [aiLoading, setAiLoading] = useState(false);
  const [voiceEnabled, setVoiceEnabled] = useState(false);
  const [isListening, setIsListening] = useState(false);

  // Input detection
  const [detectionMode, setDetectionMode] = useState(false);
  const [pressedKeys, setPressedKeys] = useState(new Set());
  const { latestInput } = useInputDetection(detectionMode);

  // Player mode: '2p' or '4p'
  const [playerMode, setPlayerMode] = useState('4p');

  // Chat drawer
  const [chatOpen, setChatOpen] = useState(false);

  // Focus mode: which player card is active for mapping (null = all equal)
  const [activePlayer, setActivePlayer] = useState(null);
  const [returningPlayer, setReturningPlayer] = useState(null); // plays exit animation
  // FLIP origin: where the focused card came from (for direction-aware animation)
  const [focusOrigin, setFocusOrigin] = useState(null);
  const mainRef = useRef(null);

  // FLIP focus handler — computes delta from card pos to panel center
  const handleFocus = useCallback((playerId, rect) => {
    if (!playerId || !rect) {
      // Dismiss: hand off to return animation — keep focusOrigin until animation ends
      setReturningPlayer(prev => prev ?? activePlayer);
      setActivePlayer(null);
      return;
    }
    // Cancel any in-flight return animation
    setReturningPlayer(null);
    setFocusOrigin(null);

    const mainEl = mainRef.current;
    if (mainEl) {
      const mainRect = mainEl.getBoundingClientRect();
      setFocusOrigin({
        dx: (rect.left + rect.width / 2) - (mainRect.left + mainRect.width / 2),
        dy: (rect.top + rect.height / 2) - (mainRect.top + mainRect.height / 2),
        w: rect.width,
      });
    }
    setActivePlayer(playerId);
  }, [activePlayer]);

  // Called by PlayerCard when its return-to-grid animation ends
  const handleReturnEnd = useCallback(() => {
    setReturningPlayer(null);
    setFocusOrigin(null);
  }, []);

  // Logo image — auto-loads from /gg-logo.png, falls back to text badge
  const [logoLoaded, setLogoLoaded] = useState(true);
  const logoPath = '/gg-logo.png';

  // Pending changes flash
  const [flashMsg, setFlashMsg] = useState(null);

  const msgIdRef = useRef(0);
  const nextId = () => `msg-${++msgIdRef.current}`;

  // Scroll to top on mount — prevents stale scroll offset from previous panel
  // causing the 4P layout to appear clipped without a full page refresh
  useEffect(() => {
    window.scrollTo(0, 0);
    document.documentElement.style.overflow = 'hidden';
    return () => { document.documentElement.style.overflow = ''; };
  }, []);

  // ── Load mapping ────────────────────────────────────────────────────────────
  useEffect(() => {
    const load = async () => {
      setLoading(true);
      try {
        const res = await fetch(`${API_BASE}/mapping`);
        if (res.ok) {
          const data = await res.json();
          setMapping(data.mapping || data || {});
          flash('Mappings loaded.', 'success');
        }
      } catch (err) {
        console.error('[Chuck] mapping load error:', err);
        flash('Could not load mappings.', 'error');
      } finally {
        setLoading(false);
      }
    };
    load();
  }, []);

  // ── Scan connected encoder board ────────────────────────────────────────────
  const scanDevices = useCallback(async () => {
    setScanLoading(true);
    try {
      const res = await fetch(`${HARDWARE_API}/arcade/boards/detect`);
      if (res.ok) {
        const data = await res.json();
        setBoard({
          name: data.name || data.board_name || 'Unknown Board',
          vid: data.vid || '—',
          pid: data.pid || '—',
          detected: data.detected ?? true,
          status: data.detected ? 'ready' : 'offline',
        });
      } else {
        setBoard((prev) => ({ ...prev, status: 'offline' }));
      }
    } catch (err) {
      console.error('[Chuck] device scan error:', err);
      setBoard((prev) => ({ ...prev, status: 'offline' }));
    } finally {
      setScanLoading(false);
    }
  }, []);

  // Run scan on mount
  useEffect(() => { scanDevices(); }, [scanDevices]);

  // ── Input detection — highlight pressed button ─────────────────────────────
  useEffect(() => {
    if (!latestInput?.control_key) return;
    const key = latestInput.control_key;
    setPressedKeys((prev) => new Set([...prev, key]));
    const t = setTimeout(() => {
      setPressedKeys((prev) => {
        const next = new Set(prev);
        next.delete(key);
        return next;
      });
    }, 600);
    return () => clearTimeout(t);
  }, [latestInput]);

  // ── Flash message ───────────────────────────────────────────────────────────
  const flash = useCallback((msg, type = 'info') => {
    setFlashMsg({ msg, type });
    setTimeout(() => setFlashMsg(null), 3000);
  }, []);

  // ── AI Chat ─────────────────────────────────────────────────────────────────
  const addMsg = useCallback((role, content) => {
    setMessages((prev) => [...prev, { id: nextId(), role, content }]);
  }, []);

  const handleSend = useCallback(async (text) => {
    addMsg('user', text);
    setAiLoading(true);
    try {
      const ctx = {
        mapping,
        has_pending: hasPending,
        board_name: board?.name || 'Unknown',
        board_detected: board?.detected ?? false,
      };
      const result = await controllerAIChat(text, ctx, { panel: 'controller-chuck' });
      const reply =
        result?.message?.content ||
        result?.reply ||
        result?.response ||
        "Yo! Ask me anything about your arcade controller setup.";
      addMsg('chuck', reply);
      if (voiceEnabled) {
        try { await speak(reply, { voice_id: CHUCK_VOICE_ID }); } catch { /* noop */ }
      }
      await logChatHistory({ panel: 'controller-chuck', role: 'assistant', content: reply });
    } catch (err) {
      console.error('[Chuck] AI error:', err);
      addMsg('chuck', "Sorry pal, hit a snag. Try again?");
    } finally {
      setAiLoading(false);
    }
  }, [addMsg, mapping, hasPending, board, voiceEnabled]);

  // ── Preview / Apply / Reset ─────────────────────────────────────────────────
  const handlePreview = useCallback(async () => {
    try {
      const res = await fetch(`${API_BASE}/preview`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ mapping }),
      });
      const data = await res.json();
      flash(`Preview: ${data.summary || 'Changes ready.'}`, 'info');
    } catch { flash('Preview failed.', 'error'); }
  }, [mapping, flash]);

  const handleApply = useCallback(async () => {
    setSubmitting(true);
    try {
      const res = await fetch(`${API_BASE}/apply`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ mapping }),
      });
      if (res.ok) {
        setHasPending(false);
        flash('Boom! Mappings applied.', 'success');
        addMsg('chuck', "Boom! Mappings applied. Backed up the old one just in case.");
      } else {
        flash('Apply failed. Check backend.', 'error');
      }
    } catch { flash('Apply failed.', 'error'); }
    finally { setSubmitting(false); }
  }, [mapping, flash, addMsg]);

  const handleReset = useCallback(async () => {
    if (!window.confirm("You sure? This'll restore factory defaults.")) return;
    try {
      const res = await fetch(`${API_BASE}/reset`, { method: 'POST' });
      if (res.ok) {
        const data = await res.json();
        setMapping(data.mapping || {});
        setHasPending(false);
        flash('Reset to factory defaults.', 'success');
        addMsg('chuck', "Done! Back to factory defaults. Fresh start, pal.");
      }
    } catch { flash('Reset failed.', 'error'); }
  }, [flash, addMsg]);

  // ── Render ──────────────────────────────────────────────────────────────────
  const boardStatus = scanLoading ? 'scanning' : board?.detected ? 'ready' : 'offline';
  const boardName = board?.name || (scanLoading ? 'Scanning...' : 'No device');

  // Active player set based on mode
  const activePlayers4P = playerMode === '4p' ? PLAYERS_4P : null;
  const activePlayers2P = playerMode === '2p'
    ? PLAYERS_2P
    : PLAYERS_4P.filter((p) => p.id === 'p1' || p.id === 'p2');
  const topRowPlayers = playerMode === '4p'
    ? PLAYERS_4P.filter((p) => p.id === 'p3' || p.id === 'p4')
    : null;

  if (loading) {
    return (
      <div className="chuck-loading">
        <div className="chuck-spinner" />
        <span>Loading Chuck's Workshop...</span>
      </div>
    );
  }

  return (
    <div className="chuck-shell" data-mode={playerMode}>
      {/* ── Header ── */}
      <header className="chuck-header">
        <div className="chuck-header-left">
          <div
            className={`chuck-status-dot ${boardStatus !== 'ready' ? 'offline' : ''}`}
            title={boardStatus}
          />
          <div>
            <h1 className="chuck-title">CONTROLLER CHUCK</h1>
            <p className="chuck-subtitle">
              Arcade Encoder Board Mapping&nbsp;•&nbsp;{currentUser || 'Guest'}
            </p>
          </div>
        </div>

        {/* 2P / 4P Mode Switcher */}
        <div className="chuck-mode-switcher" title="Switch between 2-player and 4-player mode">
          <button
            className={`chuck-mode-btn ${playerMode === '2p' ? 'active' : ''}`}
            onClick={() => setPlayerMode('2p')}
          >
            2P
          </button>
          <button
            className={`chuck-mode-btn ${playerMode === '4p' ? 'active' : ''}`}
            onClick={() => setPlayerMode('4p')}
          >
            4P
          </button>
        </div>

        <div className="chuck-board-pill">
          <span className="chuck-board-pill-name">{boardName}</span>
          <span className={`chuck-board-pill-status ${boardStatus}`}>
            {boardStatus.toUpperCase()}
          </span>
          {board?.vid && board?.pid && (
            <span style={{ color: 'var(--chuck-text-dim)', fontSize: '8px' }}>
              {board.vid} | {board.pid}
            </span>
          )}
        </div>
      </header>

      {/* ── Body ── */}
      <div className="chuck-body">
        {/* ── Horizontal layout: main grid + AI sidebar ── */}
        <div className="chuck-layout">

          {/* Main grid — two rows, each has 2 player cards */}
          <main ref={mainRef} className="chuck-main" data-mode={playerMode}>
            <FlameSVG />

            {/* ── Top Strip: Logo + Board Status + Quick Actions ── */}
            <div className="chuck-top-strip">
              {/* Logo */}
              <div className="chuck-top-strip-logo">
                {logoLoaded ? (
                  <img
                    src={logoPath}
                    alt="G&G Arcade"
                    onError={() => setLogoLoaded(false)}
                  />
                ) : (
                  <span className="chuck-logo-text">GG</span>
                )}
              </div>

              {/* Board status */}
              <div className="chuck-top-strip-status">
                <span className={`chuck-top-strip-dot ${boardStatus}`} />
                <span className="chuck-top-strip-board">{boardName}</span>
                <span className={`chuck-top-strip-state ${boardStatus}`}>
                  {boardStatus.toUpperCase()}
                </span>
              </div>

              {/* Quick actions */}
              <div className="chuck-top-strip-actions">
                <button
                  className="chuck-strip-btn"
                  onClick={scanDevices}
                  disabled={scanLoading}
                  title="Scan for connected encoder boards"
                >
                  {scanLoading ? '⏳' : '🔍'} SCAN
                </button>
                <button
                  className={`chuck-strip-btn detect ${detectionMode ? 'active' : ''}`}
                  onClick={() => setDetectionMode(v => !v)}
                  title="Toggle live input detection mode"
                >
                  <span className={`chuck-strip-detect-dot ${detectionMode ? 'on' : ''}`} />
                  DETECT
                </button>
                <button
                  className={`chuck-strip-btn ${chatOpen ? 'active' : ''}`}
                  onClick={() => setChatOpen(v => !v)}
                  title="Chat with Chuck"
                >
                  💬 CHUCK
                </button>
                <button
                  className="chuck-strip-btn preview"
                  onClick={handlePreview}
                  disabled={!hasPending}
                  title="Preview pending changes"
                >
                  PREVIEW
                </button>
                <button
                  className="chuck-strip-btn apply"
                  onClick={handleApply}
                  disabled={!hasPending || submitting}
                  title="Apply mapping changes"
                >
                  {submitting ? 'APPLYING...' : 'APPLY'}
                </button>
                <button
                  className="chuck-strip-btn reset"
                  onClick={handleReset}
                  title="Factory reset mappings"
                >
                  RESET
                </button>
              </div>
            </div>

            {/* Top row — only in 4P mode: P3 | P4 (back players) */}
            {playerMode === '4p' && (
              <div className="chuck-player-row">
                {PLAYERS_4P.filter((p) => p.id === 'p3' || p.id === 'p4').map((p) => (
                  <PlayerCard
                    key={p.id}
                    player={p}
                    mapping={mapping}
                    pressedKeys={pressedKeys}
                    playerMode={playerMode}
                    activePlayer={activePlayer}
                    focusOrigin={activePlayer === p.id || returningPlayer === p.id ? focusOrigin : null}
                    isReturning={returningPlayer === p.id}
                    onReturnEnd={handleReturnEnd}
                    onFocus={handleFocus}
                    latestInput={latestInput}
                  />
                ))}
              </div>
            )}

            {/* Center logo zone — sits between P3/P4 and P1/P2 */}
            <div className="chuck-center-logo">
              <div className="chuck-logo-badge">
                {logoLoaded ? (
                  <img
                    src={logoPath}
                    alt="G&amp;G Arcade"
                    onError={() => setLogoLoaded(false)}
                    style={{ filter: 'drop-shadow(0 0 6px rgba(0,255,65,0.4))' }}
                  />
                ) : (
                  <>
                    <span className="chuck-logo-text">GG</span>
                    <span className="chuck-logo-sub">ARCADE</span>
                  </>
                )}
              </div>
            </div>

            {/* Bottom row — always visible: P1 | P2 (front players) */}
            <div className="chuck-player-row">
              {(playerMode === '4p' ? PLAYERS_4P : PLAYERS_2P)
                .filter((p) => p.id === 'p1' || p.id === 'p2')
                .map((p) => (
                  <PlayerCard
                    key={p.id}
                    player={p}
                    mapping={mapping}
                    pressedKeys={pressedKeys}
                    playerMode={playerMode}
                    activePlayer={activePlayer}
                    focusOrigin={activePlayer === p.id || returningPlayer === p.id ? focusOrigin : null}
                    isReturning={returningPlayer === p.id}
                    onReturnEnd={handleReturnEnd}
                    onFocus={handleFocus}
                    latestInput={latestInput}
                  />
                ))}
            </div>
          </main>

          {/* ── Chuck AI Sidebar (Slide-out Drawer) ── */}
          <div
            className={`chuck-sidebar-backdrop ${chatOpen ? 'chuck-sidebar-backdrop--visible' : ''}`}
            onClick={() => setChatOpen(false)}
          />
          <div className={`chuck-drawer ${chatOpen ? 'chuck-drawer--open' : ''}`}>
            <button
              type="button"
              className="chuck-drawer__close"
              onClick={() => setChatOpen(false)}
              aria-label="Close sidebar"
            >
              ✕
            </button>
            <EngineeringBaySidebar
              persona={CHUCK_PERSONA}
              contextAssembler={chuckContextAssembler}
            />
          </div>

        </div>{/* end chuck-layout */}


      </div >
    </div>
  );
}

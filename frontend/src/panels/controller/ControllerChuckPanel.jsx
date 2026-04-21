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
import { useInputDetection } from '../../hooks/useInputDetection';
import { useProfileContext } from '../../context/ProfileContext';
import { getGatewayWsUrl } from '../../services/gateway';
import { buildStandardHeaders, resolveDeviceId } from '../../utils/identity';
import { EngineeringBaySidebar } from '../_kit/EngineeringBaySidebar';
import { chuckContextAssembler } from './chuckContextAssembler';
import { chuckChips } from './chuckChips';
import CabinetControlStatus from './CabinetControlStatus';
import {
  fetchBaseline,
  fetchCascadeStatus,
  requestCascade,
} from './apiHelpers';
import { refreshControllerDevices } from '../../services/deviceClient';
import './controller-chuck.css';
import './chuck-layout.css';
import './chuck-sidebar.css';
import '../_kit/EngineeringBaySidebar.css';


// ── Constants ───────────────────────────────────────────────────────────────
const API_BASE = '/api/local/controller';
const HARDWARE_API = '/api/local/hardware';
const CHUCK_VOICE_ID = 'vDchjyOZZytffNeZXfZK';

/** Chuck persona config for EngineeringBaySidebar */
const CHUCK_PERSONA = {
  agentName: 'Chuck',
  title: 'CONTROLLER CHUCK',
  subtitle: 'Arcade Encoder Board Mapping',
  chatEndpoint: '/api/local/chuck/chat',
  diagnosisMode: true,
  diagnosisPrompt: 'CHUCK DIAG - what needs fixing?',
  chatPrompt: 'Ask Chuck about controller mappings, GPIO, or arcade setup.',
  quickChips: [
    'Scan encoder board',
    'Fix button mapping',
    'Controller not detected',
  ],
  id: 'chuck',
  name: 'CHUCK',
  icon: '⚙️',
  icon2: '🕹️',
  accentColor: '#22c55e',
  accentGlow: 'rgba(34,197,94,0.35)',
  scannerLabel: 'ANALYZING...',
  voiceProfile: 'chuck',
  voiceId: CHUCK_VOICE_ID,
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

const resolveChuckDeviceId = () => resolveDeviceId();

const chuckHeaders = (scope = 'state', json = false) => buildStandardHeaders({
  panel: 'controller-chuck',
  scope,
  extraHeaders: json ? { 'Content-Type': 'application/json' } : {},
});

function inferControlType(controlKey) {
  if (controlKey?.includes('.button') || controlKey?.endsWith('.coin') || controlKey?.endsWith('.start')) {
    return 'button';
  }
  if (controlKey?.includes('.up') || controlKey?.includes('.down') || controlKey?.includes('.left') || controlKey?.includes('.right')) {
    return 'joystick';
  }
  return 'button';
}

function extractErrorMessage(error, fallback) {
  if (!error) return fallback;
  if (typeof error === 'string') return error;
  if (error?.message) return error.message;
  if (typeof error?.detail === 'string') return error.detail;
  if (typeof error?.detail?.message === 'string') return error.detail.message;
  return fallback;
}

function normalizeBoardStatus(board) {
  if (!board) return 'offline';
  const status = String(board.status || '').toLowerCase();
  if (status === 'ready' || status === 'connected' || board.detected) {
    return 'ready';
  }
  if (status === 'error') {
    return 'error';
  }
  if (status === 'scanning') {
    return 'scanning';
  }
  return 'offline';
}

function normalizeDeviceScanPayload(payload) {
  return {
    status: payload?.status || 'unknown',
    controllers: Array.isArray(payload?.controllers) ? payload.controllers : [],
    hints: Array.isArray(payload?.hints) ? payload.hints : [],
    errors: Array.isArray(payload?.errors) ? payload.errors : [],
  };
}

function formatControlLabel(controlKey) {
  if (!controlKey) return 'No control captured';
  return controlKey
    .replace(/\./g, ' ')
    .replace(/\bbutton(\d+)\b/gi, 'Button $1')
    .replace(/\bcoin\b/gi, 'Coin')
    .replace(/\bstart\b/gi, 'Start')
    .replace(/\bup\b/gi, 'Up')
    .replace(/\bdown\b/gi, 'Down')
    .replace(/\bleft\b/gi, 'Left')
    .replace(/\bright\b/gi, 'Right')
    .replace(/\bp(\d)\b/gi, 'P$1')
    .replace(/\s+/g, ' ')
    .trim();
}

// ── Sub-components ───────────────────────────────────────────────────────────

/** 8-way joystick graphic with ↑↓←→ mapping overlay */
const DIRS = ['up', 'down', 'left', 'right'];
const DIR_PATHS = {
  up: 'M18,5 L25,17 H11 Z',
  down: 'M18,31 L25,19 H11 Z',
  left: 'M5,18 L17,11 V25 Z',
  right: 'M31,18 L19,11 V25 Z',
};

const JoystickGraphic = memo(({ onDirClick, mappingDir, confirmedDir, pressedDir }) => (
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
              + (pressedDir === dir ? ' pressed' : '')
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
const UtilButton = memo(({ label, pinLabel, pressed, waiting, confirmed, onClick }) => (
  <div
    className="chuck-util-btn"
    style={{ position: 'relative' }}
    onClick={onClick}
    role="button"
    tabIndex={0}
    onKeyDown={(e) => {
      if (e.key === 'Enter' || e.key === ' ') {
        e.preventDefault();
        onClick?.(e);
      }
    }}
  >
    <div className={`chuck-util-btn-face chuck-btn-circle-face${pressed ? ' pressed' : ''}${waiting ? ' waiting' : ''}${confirmed ? ' confirmed' : ''}`}>{label}</div>
    <span className="chuck-util-label">{pinLabel || '—'}</span>
    {confirmed && (
      <div className="chuck-mapped-badge">✓ GPIO {confirmed.pin}</div>
    )}
  </div>
));
UtilButton.displayName = 'UtilButton';

/** One player card (joystick + button grid + utilities) */
const PlayerCard = memo(({ player, mapping, pressedKeys, playerMode, activePlayer, focusOrigin, isReturning, onReturnEnd, onFocus, latestInput, onMapped, setDetectionMode }) => {
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
    const entry = mapping?.[`${id}.${controlKey}`]
      || (controlKey === 'select' ? mapping?.[`${id}.coin`] : null);
    return entry?.pin != null ? String(entry.pin) : null;
  }, [id, mapping]);

  const isPressed = useCallback((controlKey) => {
    return (pressedKeys?.has(`${id}.${controlKey}`)
      || (controlKey === 'select' && pressedKeys?.has(`${id}.coin`))) ?? false;
  }, [id, pressedKeys]);

  // Directional mapping state — null means idle
  const [mappingDir, setMappingDir] = useState(null);
  // Button mapping state — which button number is waiting for cabinet input
  const [mappingButton, setMappingButton] = useState(null);
  // Utility mapping state — which utility control is waiting for cabinet input
  const [mappingUtility, setMappingUtility] = useState(null);

  // Confirmation state — set briefly after a physical press is received
  const [confirmedButton, setConfirmedButton] = useState(null); // { num, pin }
  const [confirmedDir, setConfirmedDir] = useState(null); // { dir, pin }
  const [confirmedUtility, setConfirmedUtility] = useState(null); // { key, pin }

  // ── Listen for incoming hardware signal ──────────────────────────
  // When this card is in a waiting state and latestInput arrives,
  // fire the confirmation animation and clear the waiting state.
  useEffect(() => {
    if (!latestInput || (mappingButton === null && mappingDir === null && mappingUtility === null)) return;

    const pin = latestInput.pin ?? latestInput.key ?? '?';

    if (mappingButton !== null) {
      setConfirmedButton({ num: mappingButton, pin });
      onMapped?.(`${id}.button${mappingButton}`, pin);
      setMappingButton(null);
      setDetectionMode(false);
      const t = setTimeout(() => setConfirmedButton(null), 1800);
      return () => clearTimeout(t);
    }
    if (mappingDir !== null) {
      setConfirmedDir({ dir: mappingDir, pin });
      onMapped?.(`${id}.${mappingDir}`, pin);
      setMappingDir(null);
      setDetectionMode(false);
      const t = setTimeout(() => setConfirmedDir(null), 1800);
      return () => clearTimeout(t);
    }
    if (mappingUtility !== null) {
      setConfirmedUtility({ key: mappingUtility, pin });
      onMapped?.(`${id}.${mappingUtility}`, pin);
      setMappingUtility(null);
      setDetectionMode(false);
      const t = setTimeout(() => setConfirmedUtility(null), 1800);
      return () => clearTimeout(t);
    }
  }, [id, latestInput, mappingButton, mappingDir, mappingUtility, onMapped]);

  const handleDirClick = useCallback((dir) => {
    setMappingDir((prev) => {
      const next = prev === dir ? null : dir;
      setDetectionMode(next !== null);
      return next;
    });
    setMappingButton(null);
    setMappingUtility(null);
    setConfirmedButton(null);
    setConfirmedUtility(null);
    onFocus?.(id, cardRef.current?.getBoundingClientRect());
  }, [id, onFocus]);

  const handleMapBtn = useCallback((num, e) => {
    e.stopPropagation();
    setMappingButton((prev) => {
      const next = prev === num ? null : num;
      setDetectionMode(next !== null);
      return next;
    });
    setMappingDir(null);
    setMappingUtility(null);
    setConfirmedDir(null);
    setConfirmedUtility(null);
    onFocus?.(id, cardRef.current?.getBoundingClientRect());
  }, [id, onFocus]);

  const handleMapUtility = useCallback((controlKey, e) => {
    e.stopPropagation();
    setMappingUtility((prev) => {
      const next = prev === controlKey ? null : controlKey;
      setDetectionMode(next !== null);
      return next;
    });
    setMappingButton(null);
    setMappingDir(null);
    setConfirmedButton(null);
    setConfirmedDir(null);
    setConfirmedUtility(null);
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
        if (mappingDir || mappingButton || mappingUtility) {
          setMappingDir(null);
          setMappingButton(null);
          setMappingUtility(null);
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
          pressedDir={DIRS.find((dir) => isPressed(dir)) ?? null}
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
            <UtilButton
              label="SEL"
              pinLabel={getPin('select')}
              pressed={isPressed('select')}
              waiting={mappingUtility === 'select'}
              confirmed={confirmedUtility?.key === 'select' ? confirmedUtility : null}
              onClick={(e) => handleMapUtility('select', e)}
            />
            <UtilButton
              label="START"
              pinLabel={getPin('start')}
              pressed={isPressed('start')}
              waiting={mappingUtility === 'start'}
              confirmed={confirmedUtility?.key === 'start' ? confirmedUtility : null}
              onClick={(e) => handleMapUtility('start', e)}
            />
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
  const deviceId = resolveChuckDeviceId();
  const handoffProcessedRef = useRef(null);

  // ── State ──────────────────────────────────────────────────────────────────
  const [mapping, setMapping] = useState({});
  const [pendingMappings, setPendingMappings] = useState({});
  const [hasPending, setHasPending] = useState(false);
  const [loading, setLoading] = useState(true);
  const [submitting, setSubmitting] = useState(false);

  // Board / device scan
  const [board, setBoard] = useState(null);
  const [scanLoading, setScanLoading] = useState(false);
  const [deviceScan, setDeviceScan] = useState({ status: 'idle', controllers: [], hints: [], errors: [] });
  const [mappingMeta, setMappingMeta] = useState({
    status: 'unknown',
    message: '',
    filePath: 'config/mappings/controls.json',
    factoryDefaultsAvailable: false,
    seedSource: null,
  });

  // Input detection
  const [detectionMode, setDetectionMode] = useState(false);
  const [pressedKeys, setPressedKeys] = useState(new Set());
  const {
    latestInput,
    isActive: detectionActive,
    error: detectionError,
  } = useInputDetection(detectionMode);

  // Player mode: '2p' or '4p'
  const [playerMode, setPlayerMode] = useState('4p');

  // Chat drawer
  const [chatOpen, setChatOpen] = useState(false);
  const [initialChatMessages, setInitialChatMessages] = useState([]);
  // Diagnostics panel — collapsed by default so the controller stage is the hero


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
    if (playerId === activePlayer) {
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

  useEffect(() => {
    const url = new URL(window.location.href);
    const handoffParam = url.searchParams.get('context');
    const noHandoff = url.searchParams.has('nohandoff');
    let handoffContext = '';

    try {
      handoffContext = decodeURIComponent(handoffParam || '').trim();
    } catch {
      handoffContext = (handoffParam || '').trim();
    }

    const shouldHandoff = Boolean(handoffContext) && !noHandoff;
    if (!shouldHandoff || handoffContext === handoffProcessedRef.current) {
      return;
    }

    handoffProcessedRef.current = handoffContext;
    setInitialChatMessages([
      {
        id: 'chuck-handoff-user',
        role: 'user',
        content: `Dewey handoff context: ${handoffContext}`,
        timestamp: new Date().toISOString(),
      },
      {
        id: 'chuck-handoff-assistant',
        role: 'assistant',
        content: `I see Dewey sent you here for: "${handoffContext}"\n\nI'm Chuck. I can help with arcade controls, encoder wiring, and pin mapping. Tell me what you want to fix.`,
        timestamp: new Date().toISOString(),
      },
    ]);
    setChatOpen(true);

    url.searchParams.delete('context');
    const nextSearch = url.searchParams.toString();
    window.history.replaceState({}, '', `${url.pathname}${nextSearch ? `?${nextSearch}` : ''}${url.hash}`);
  }, []);

  // Logo image — auto-loads from /gg-logo.png, falls back to text badge
  const [logoLoaded, setLogoLoaded] = useState(true);
  const logoPath = '/gg-logo.png';

  // Pending changes flash
  const [flashMsg, setFlashMsg] = useState(null);
  const [hardwareState, setHardwareState] = useState(null);
  const [hardwareReconnecting, setHardwareReconnecting] = useState(false);
  const [hardwareError, setHardwareError] = useState(null);
  const [previewState, setPreviewState] = useState(null);
  const [baselineState, setBaselineState] = useState(null);
  const [cascadeState, setCascadeState] = useState(null);
  const [cascadeSubmitting, setCascadeSubmitting] = useState(false);
  const [statusRefreshKey, setStatusRefreshKey] = useState(0);
  const bumpStatusRefresh = useCallback(() => setStatusRefreshKey((n) => n + 1), []);
  const statusHeaders = useMemo(() => chuckHeaders('state'), []);


  // Scroll to top on mount — prevents stale scroll offset from previous panel
  // causing the 4P layout to appear clipped without a full page refresh
  useEffect(() => {
    window.scrollTo(0, 0);
    document.documentElement.style.overflow = 'hidden';
    return () => { document.documentElement.style.overflow = ''; };
  }, []);

  // ── Load mapping ────────────────────────────────────────────────────────────
  const loadMapping = useCallback(async ({ showFlash = true } = {}) => {
    setLoading(true);
    try {
      const res = await fetch(`${API_BASE}/mapping`, {
        headers: chuckHeaders('state'),
      });
      if (!res.ok) {
        throw new Error(`Mapping load failed (${res.status})`);
      }
      const data = await res.json();
      const mappingStatus = data?.status || 'success';
      const factoryDefaultsAvailable = Boolean(data?.factory_defaults_available);
      setMappingMeta({
        status: mappingStatus,
        message: data?.message || '',
        filePath: data?.file_path || 'config/mappings/controls.json',
        factoryDefaultsAvailable,
        seedSource: data?.seed_source || null,
      });
      setMapping(data?.mapping?.mappings || data?.mappings || {});
      setPendingMappings({});
      setHasPending(false);
      setPreviewState(null);
      // TRUTH-LANE: Do NOT seed board state from saved mapping data.
      // saved-mapping board identity (data?.mapping?.board || data?.board) tells us
      // what controls.json is configured as — not what is live on the wire.
      // Board state is owned exclusively by scanDevices() via the canonical
      // hardware lane. loadMapping is mapping-dictionary state only.
      if (showFlash) {
        setFlashMsg({
          msg: mappingStatus === 'missing'
            ? (
              factoryDefaultsAvailable
                ? 'No saved mapping yet. Chuck will start from factory defaults until you save controls.json.'
                : (data?.message || 'No saved mapping yet.')
            )
            : 'Mappings loaded.',
          type: mappingStatus === 'missing' ? 'info' : 'success',
        });
        setTimeout(() => setFlashMsg(null), 3000);
      }
    } catch (err) {
      console.error('[Chuck] mapping load error:', err);
      setMappingMeta((prev) => ({
        ...prev,
        status: 'error',
        message: extractErrorMessage(err, 'Could not load mappings.'),
      }));
      setFlashMsg({ msg: 'Could not load mappings.', type: 'error' });
      setTimeout(() => setFlashMsg(null), 3000);
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    loadMapping();
  }, [loadMapping]);

  const refreshControllerState = useCallback(async () => {
    const [baselineResult, cascadeResult] = await Promise.allSettled([
      fetchBaseline(),
      fetchCascadeStatus(),
    ]);

    if (baselineResult.status === 'fulfilled') {
      setBaselineState(baselineResult.value);
    }
    if (cascadeResult.status === 'fulfilled') {
      setCascadeState(cascadeResult.value);
    }
    bumpStatusRefresh();
  }, [bumpStatusRefresh]);

  useEffect(() => {
    refreshControllerState();
  }, [refreshControllerState]);

  // ── Scan connected encoder board ────────────────────────────────────────────
  const scanDevices = useCallback(async () => {
    setScanLoading(true);
    try {
      // Force a backend hot-plug refresh BEFORE re-fetching board status so a
      // physically reconnected board can actually appear in Chuck's canonical
      // board lane. Failure here must not block the rest of the scan — the
      // refresh route is best-effort and older backends may not expose it.
      try {
        await refreshControllerDevices();
      } catch (refreshErr) {
        console.warn('[Chuck] controller refresh failed (continuing):', refreshErr);
      }
      const [boardRes, deviceRes] = await Promise.all([
        fetch(`${HARDWARE_API}/arcade/boards`, {
          headers: chuckHeaders('state'),
        }),
        fetch(`${API_BASE}/devices`, {
          headers: chuckHeaders('state'),
        }),
      ]);
      const boardData = await boardRes.json().catch(() => ({}));
      const deviceData = await deviceRes.json().catch(() => ({}));
      setDeviceScan(
        deviceRes.ok
          ? normalizeDeviceScanPayload(deviceData)
          : {
            status: 'error',
            controllers: [],
            hints: [],
            errors: [{ message: extractErrorMessage(deviceData, `Device scan failed (${deviceRes.status})`) }],
          }
      );
      const boards = Array.isArray(boardData?.boards) ? boardData.boards : [];
      if (!boardRes.ok) {
        throw new Error(extractErrorMessage(boardData, `Board scan failed (${boardRes.status})`));
      }
      if (boards.length > 0) {
        const boardNames = boards.map((entry) => entry.name || entry.board_name || 'Unknown Board');
        const primaryBoard = boards[0] || {};
        setBoard({
          ...primaryBoard,
          name: boardNames.join(', '),
          vid: boards.length === 1 ? (primaryBoard.vid || '—') : `${boards.length} boards`,
          pid: boards.length === 1 ? (primaryBoard.pid || '—') : 'detected',
          detected: true,
          status: normalizeBoardStatus(primaryBoard),
        });
        setHardwareError(null);
      } else {
        setBoard({
          name: 'No encoder boards detected.',
          vid: '—',
          pid: '—',
          detected: false,
          status: 'offline',
        });
      }
    } catch (err) {
      console.error('[Chuck] device scan error:', err);
      setBoard({
        name: 'No encoder boards detected.',
        vid: '—',
        pid: '—',
        detected: false,
        status: 'offline',
      });
      setHardwareError(extractErrorMessage(err, 'Board scan failed.'));
    } finally {
      setScanLoading(false);
      bumpStatusRefresh();
    }
  }, [bumpStatusRefresh]);

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

  useEffect(() => {
    const params = new URLSearchParams({
      device: deviceId,
      panel: 'controller-chuck',
      corr_id: `controller-chuck-${Date.now()}`,
    });
    const ws = new WebSocket(
      getGatewayWsUrl(`/api/local/hardware/ws/encoder-events?${params.toString()}`)
    );

    ws.onopen = () => {
      setHardwareReconnecting(false);
      setHardwareError(null);
    };

    ws.onmessage = (event) => {
      try {
        const payload = JSON.parse(event.data);
        if (payload.event === 'HARDWARE_STATE_UPDATE') {
          setHardwareState(payload.data);
          setHardwareReconnecting(false);
          setHardwareError(null);
          return;
        }
        if (payload.event === 'HARDWARE_HEARTBEAT') {
          setHardwareReconnecting(false);
          return;
        }
        if (payload.event === 'HARDWARE_ERROR') {
          console.warn('Chuck hardware error:', payload.message);
          setHardwareError(payload.message || 'Hardware feed reported an error.');
          setHardwareReconnecting(false);
          return;
        }
        if (payload.type === 'gateway_error') {
          setHardwareError(payload.message || 'Gateway could not proxy the hardware feed.');
          setHardwareReconnecting(true);
          return;
        }
        if (payload.type === 'gateway_notice' && payload.status === 'proxy_closed') {
          setHardwareReconnecting(true);
        }
      } catch (e) {
        console.error('Chuck WS parse error:', e);
      }
    };

    ws.onclose = () => setHardwareReconnecting(true);
    ws.onerror = () => {
      setHardwareReconnecting(true);
      setHardwareError('Live hardware feed dropped. Trying to reconnect.');
    };

    return () => {
      ws.close();
    };
  }, [deviceId]);

  // ── Flash message ───────────────────────────────────────────────────────────
  const flash = useCallback((msg, type = 'info') => {
    setFlashMsg({ msg, type });
    setTimeout(() => setFlashMsg(null), 3000);
  }, []);

  // ── AI Chat ─────────────────────────────────────────────────────────────────
  // ── Preview / Apply / Reset ─────────────────────────────────────────────────
  const handleMappedControl = useCallback((controlKey, pin) => {
    const normalizedPin = Number(pin);
    if (!controlKey || Number.isNaN(normalizedPin)) {
      return;
    }

    setMapping((prev) => ({
      ...prev,
      [controlKey]: {
        ...(prev[controlKey] || {}),
        pin: normalizedPin,
        type: prev[controlKey]?.type || inferControlType(controlKey),
      },
    }));

    setPendingMappings((prev) => ({
      ...prev,
      [controlKey]: {
        ...(mapping[controlKey] || prev[controlKey] || {}),
        pin: normalizedPin,
        type: mapping[controlKey]?.type || prev[controlKey]?.type || inferControlType(controlKey),
      },
    }));
    setHasPending(true);
    setPreviewState(null);
  }, [mapping]);

  const handlePreview = useCallback(async () => {
    if (!hasPending) {
      flash('No pending mapping changes to preview.', 'info');
      return;
    }
    try {
      const res = await fetch(`${API_BASE}/mapping/preview`, {
        method: 'POST',
        headers: chuckHeaders('state', true),
        body: JSON.stringify({ mappings: pendingMappings }),
      });
      const data = await res.json().catch(() => ({}));
      if (!res.ok) {
        throw new Error(extractErrorMessage(data, `Preview failed (${res.status})`));
      }
      setPreviewState(data);
      const changeCount = Array.isArray(data?.cascade_preview?.changed_controls)
        ? data.cascade_preview.changed_controls.length
        : Object.keys(pendingMappings).length;
      const errorCount = data?.validation?.errors?.length || 0;
      const warningCount = data?.validation?.warnings?.length || 0;
      if (errorCount > 0) {
        flash(`Preview blocked: ${errorCount} validation issue(s) found.`, 'error');
        return;
      }
      flash(
        `Preview ready: ${changeCount} control change(s)${warningCount ? `, ${warningCount} warning(s)` : ''}.`,
        'info'
      );
    } catch (err) {
      flash(extractErrorMessage(err, 'Preview failed.'), 'error');
    }
  }, [flash, hasPending, pendingMappings]);

  const handleApply = useCallback(async () => {
    setSubmitting(true);
    try {
      const res = await fetch(`${API_BASE}/mapping/apply`, {
        method: 'POST',
        headers: chuckHeaders('config', true),
        body: JSON.stringify({ mappings: pendingMappings }),
      });
      const data = await res.json().catch(() => ({}));
      if (res.ok) {
        setMapping(data?.mapping?.mappings || data?.mapping || mapping);
        setPendingMappings({});
        setHasPending(false);
        setPreviewState(null);
        setMappingMeta({
          status: 'success',
          message: '',
          filePath: data?.target_file || 'config/mappings/controls.json',
          factoryDefaultsAvailable: false,
          seedSource: data?.seed_source || null,
        });
        await refreshControllerState();
        const cascadeCallout = data?.cascade_callout ? ` ${data.cascade_callout}` : '';
        flash(
          `Mappings applied to controls.json.${cascadeCallout}`,
          data?.cascade_prompt ? 'info' : 'success'
        );
      } else {
        flash(extractErrorMessage(data, `Apply failed (${res.status}).`), 'error');
      }
    } catch (err) {
      flash(extractErrorMessage(err, 'Apply failed.'), 'error');
    }
    finally { setSubmitting(false); }
  }, [flash, mapping, pendingMappings, refreshControllerState]);

  const handleRestoreSaved = useCallback(async () => {
    await loadMapping({ showFlash: false });
    flash('Restored the last saved mapping from controls.json.', 'info');
  }, [flash, loadMapping]);

  const handleReset = useCallback(async () => {
    if (!window.confirm('Restore controller mappings from factory-default.json and overwrite current saved mappings?')) return;
    try {
      const res = await fetch(`${API_BASE}/mapping/reset`, {
        method: 'POST',
        headers: chuckHeaders('config'),
      });
      const data = await res.json().catch(() => ({}));
      if (res.ok) {
        setMapping(data?.mapping?.mappings || data?.mappings || {});
        setPendingMappings({});
        setHasPending(false);
        setPreviewState(null);
        setMappingMeta({
          status: 'success',
          message: data?.message || '',
          filePath: data?.target_file || 'config/mappings/controls.json',
          factoryDefaultsAvailable: true,
          seedSource: data?.restored_from || 'config/mappings/factory-default.json',
        });
        await refreshControllerState();
        flash(data?.message || 'Mappings reset to factory defaults.', 'success');
      } else {
        flash(extractErrorMessage(data, `Factory reset failed (${res.status}).`), 'error');
      }
    } catch (err) {
      flash(extractErrorMessage(err, 'Factory reset failed.'), 'error');
    }
  }, [flash, refreshControllerState]);

  const handleCascadeApply = useCallback(async () => {
    setCascadeSubmitting(true);
    try {
      const response = await requestCascade({
        metadata: {
          source: 'controller-chuck',
          requested_from: 'panel',
        },
      });
      await refreshControllerState();
      flash(
        response?.job?.job_id
          ? `Cascade queued. Job ${response.job.job_id} is now syncing controller changes.`
          : 'Cascade queued.',
        'success'
      );
    } catch (err) {
      flash(extractErrorMessage(err, 'Cascade apply failed.'), 'error');
    } finally {
      setCascadeSubmitting(false);
    }
  }, [flash, refreshControllerState]);

  // ── Render ──────────────────────────────────────────────────────────────────
  const detectedArcadeBoard = useMemo(() => {
    const controllers = Array.isArray(deviceScan.controllers) ? deviceScan.controllers : [];
    return controllers.find((entry) => entry?.type === 'arcade_board' && entry?.detected !== false) || null;
  }, [deviceScan]);
  const liveBoard = useMemo(() => {
    // Priority: WS live state > canonical scan result (board?.detected=true) > USB scan result
    // Do NOT fall back to bare `board` when board.detected is false — that would be stale
    // saved-mapping identity masquerading as a live board.
    if (hardwareState?.primary_board) return hardwareState.primary_board;
    if (board?.detected) return board;
    if (detectedArcadeBoard) return detectedArcadeBoard;
    return null;  // No live board confirmed. Return null, not the stale board object.
  }, [board, detectedArcadeBoard, hardwareState]);
  const boardStatus = scanLoading
    ? 'scanning'
    : hardwareReconnecting
      ? 'scanning'
      : normalizeBoardStatus(liveBoard);
  const boardName = liveBoard?.name || board?.name || (scanLoading ? 'Scanning...' : 'No device');
  // TRUTH-LANE: Distinguish "no encoder board found" from a genuine signal-loss
  // so the header pill accurately reflects hardware state, not a panel-offline message.
  const boardStatusLabel = (() => {
    if (boardStatus === 'scanning') return 'SCANNING';
    if (boardStatus === 'ready') return 'READY';
    if (boardStatus === 'error') return 'ERROR';
    // boardStatus is 'offline' — "not detected" vs "detected but lost signal"
    const notDetected = liveBoard ? liveBoard.detected === false : true;
    return notDetected ? 'NO BOARD' : 'NO SIGNAL';
  })();
  const pendingCount = Object.keys(pendingMappings).length;
  const latestInputLabel = detectionError
    ? 'Detection unavailable'
    : latestInput?.control_key
      ? `${formatControlLabel(latestInput.control_key)} • GPIO ${latestInput.pin ?? '?'}`
      : detectionMode
        ? (detectionActive ? 'Listening for live input…' : 'Starting live listener…')
        : 'Detection idle';
  const cascadeJob = cascadeState?.job;
  const cascadeHistoryCount = Array.isArray(cascadeState?.history) ? cascadeState.history.length : 0;
  const previewWarnings = previewState?.validation?.warnings || [];
  const previewErrors = previewState?.validation?.errors || [];
  const previewChangedControls = previewState?.cascade_preview?.changed_controls || [];
  const emulatorStates = baselineState?.emulators ? Object.entries(baselineState.emulators) : [];
  const detectedControllers = Array.isArray(deviceScan.controllers) ? deviceScan.controllers : [];
  const arcadeDevices = detectedControllers.filter((entry) => entry.type === 'arcade_board');
  const nonArcadeDevices = detectedControllers.filter((entry) => entry.type !== 'arcade_board');
  const deviceInventoryLabel = detectedControllers.length
    ? `${arcadeDevices.length} arcade board(s), ${nonArcadeDevices.length} other device(s)`
    : 'No devices reported';
  const deviceInventoryHelp = deviceScan.errors?.[0]?.message
    || deviceScan.hints?.[0]
    || (
      detectedControllers.length
        ? detectedControllers
          .slice(0, 3)
          .map((entry) => `${entry.name || 'Unknown device'} (${entry.status || 'unknown'})`)
          .join(' • ')
        : 'Scan to list encoder boards, configured hardware, and any secondary controllers.'
    );
  const mappingDictionaryLabel = mappingMeta.status === 'missing'
    ? 'No saved controls.json yet'
    : mappingMeta.filePath;
  const mappingDictionaryHelp = mappingMeta.message
    || (
      mappingMeta.status === 'missing' && mappingMeta.factoryDefaultsAvailable
        ? 'Preview and apply will start from factory-default.json until the first save.'
        : 'Chuck is using the saved mapping dictionary.'
    );

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
            title={boardStatusLabel.toLowerCase()}
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

        {/* ── Header action bar — all controls surface here, one bar to rule them ── */}
        <div className="chuck-header-actions">
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
            title="Input Learn: arm the encoder listener to watch for the next physical button press."
          >
            <span className={`chuck-strip-detect-dot ${detectionMode ? 'on' : ''}`} />
            {detectionMode ? 'LEARNING…' : 'INPUT LEARN'}
          </button>
          <button
            className={`chuck-strip-btn ${chatOpen ? 'active' : ''}`}
            onClick={() => setChatOpen(v => !v)}
            title="Chat with Chuck"
          >
            💬 CHUCK
          </button>
          <button
            className="chuck-strip-btn"
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
            className="chuck-strip-btn"
            onClick={handleRestoreSaved}
            disabled={!hasPending || submitting}
            title="Discard pending edits and reload the saved mapping"
          >
            RESTORE
          </button>
          <button
            className="chuck-strip-btn reset"
            onClick={handleReset}
            title="Restore factory-default.json into controls.json"
          >
            FACTORY
          </button>
        </div>
      </header>

      {/* ── Body ── */}
      <div className="chuck-body">
        {/* Cabinet Control Status — single coherent truth surface */}
        <CabinetControlStatus
          headers={statusHeaders}
          refreshKey={statusRefreshKey}
        />
        {/* ── Horizontal layout: main grid + AI sidebar ── */}
        <div className="chuck-layout">

          {/* Main grid — two rows, each has 2 player cards */}
          <main ref={mainRef} className="chuck-main" data-mode={playerMode}>
            <FlameSVG />

            {flashMsg && (
              <div className={`chuck-flash-banner ${flashMsg.type || 'info'}`}>
                {flashMsg.msg}
              </div>
            )}


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
                    onMapped={handleMappedControl}
                    setDetectionMode={setDetectionMode}
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
                    onMapped={handleMappedControl}
                    setDetectionMode={setDetectionMode}
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
              initialMessages={initialChatMessages}
            />
          </div>

        </div>{/* end chuck-layout */}




      </div >
    </div>
  );
}


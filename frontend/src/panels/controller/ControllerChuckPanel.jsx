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
import './controller-chuck.css';

// ── Constants ───────────────────────────────────────────────────────────────
const API_BASE = '/api/local/controller';
const HARDWARE_API = '/api/local/hardware';
const CHUCK_VOICE_ID = 'f5HLTX707KIM4SzJYzSz';

const CHUCK_GREET = "Yo! Chuck here. Let's get this cabinet wired up right.";

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

/** 8-way joystick SVG/CSS graphic */
const JoystickGraphic = memo(() => (
  <div className="chuck-joystick-wrap">
    <div className="chuck-joystick">
      <div className="chuck-joystick-diag" />
      <div className="chuck-joystick-inner" />
    </div>
    <span className="chuck-joystick-label">8-WAY</span>
  </div>
));
JoystickGraphic.displayName = 'JoystickGraphic';

/** Single arcade button circle */
const ArcadeButton = memo(({ num, pinLabel, pressed, onClick }) => (
  <div
    className="chuck-btn-circle"
    data-btn={String(num)}
    onClick={onClick}
    title={`Button ${num}${pinLabel ? ` — Pin ${pinLabel}` : ''}`}
  >
    <div className={`chuck-btn-circle-face ${pressed ? 'pressed' : ''}`}>
      {num}
    </div>
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
const PlayerCard = memo(({ player, mapping, pressedKeys, onButtonClick, playerMode }) => {
  const { id, label, cls, layout } = player;

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

  return (
    <div className={`chuck-player-card ${cls}${playerMode === '2p' ? ' mode-2p' : ''}`}>
      <div className="chuck-player-header">
        <span className="chuck-player-badge">{label}</span>
        <span className="chuck-player-status">GPIO BANK {cls.toUpperCase()}</span>
      </div>

      <div className="chuck-controller-layout">
        <JoystickGraphic />

        <div className="chuck-button-area">
          {/* Top row */}
          <div className="chuck-button-row">
            {layout.topRow.map((n) => (
              <ArcadeButton
                key={n}
                num={n}
                pinLabel={getPin(`button${n}`)}
                pressed={isPressed(`button${n}`)}
                onClick={() => handleBtn(n)}
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
                onClick={() => handleBtn(n)}
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

/** Chuck AI chat sidebar (embedded, always visible) */
const ChuckSidebar = memo(({
  messages, onSend, isLoading, boardName, boardStatus, onScan, scanLoading,
  voiceEnabled, isListening, onVoiceToggle,
}) => {
  const [input, setInput] = useState('');
  const messagesEndRef = useRef(null);

  useEffect(() => {
    messagesEndRef.current?.scrollIntoView({ behavior: 'smooth' });
  }, [messages]);

  const handleSend = useCallback(() => {
    const text = input.trim();
    if (!text || isLoading) return;
    setInput('');
    onSend(text);
  }, [input, isLoading, onSend]);

  const handleKey = useCallback((e) => {
    if (e.key === 'Enter') handleSend();
  }, [handleSend]);

  const statusClass =
    boardStatus === 'ready' ? 'ready' :
      boardStatus === 'scanning' ? 'scanning' : 'offline';

  return (
    <aside className="chuck-sidebar">
      <div className="chuck-sidebar-header">
        <img src="/chuck-avatar.jpeg" alt="Chuck" className="chuck-sidebar-avatar" />
        <div>
          <div className="chuck-sidebar-title">CHUCK AI</div>
          <div className="chuck-sidebar-status">• ONLINE</div>
        </div>
      </div>

      <div className="chuck-chat-messages">
        {messages.map((m) => (
          <div key={m.id} className={`chuck-chat-msg ${m.role}`}>
            {m.content}
          </div>
        ))}
        {isLoading && (
          <div className="chuck-chat-msg chuck">Thinkin'...</div>
        )}
        <div ref={messagesEndRef} />
      </div>

      <div className="chuck-chat-input-row">
        <input
          className="chuck-chat-input"
          placeholder="Ask Chuck anything..."
          value={input}
          onChange={(e) => setInput(e.target.value)}
          onKeyDown={handleKey}
          disabled={isLoading}
        />
        <button className="chuck-chat-send" onClick={handleSend} disabled={isLoading} title="Send">
          ▶
        </button>
      </div>

      <div className="chuck-device-info">
        <div className="chuck-device-row">
          <div>
            <div className="chuck-device-label">DEVICE TYPE</div>
            <div className="chuck-device-name">{boardName || 'Unknown'}</div>
          </div>
          <span className={`chuck-device-status-pill ${statusClass}`}>
            {boardStatus === 'ready' ? 'READY' :
              boardStatus === 'scanning' ? 'SCANNING' : 'OFFLINE'}
          </span>
        </div>
        <button
          className="chuck-scan-btn"
          onClick={onScan}
          disabled={scanLoading}
        >
          {scanLoading ? 'SCANNING...' : '🔍 SCAN DEVICES'}
        </button>
      </div>
    </aside>
  );
});
ChuckSidebar.displayName = 'ChuckSidebar';

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
    <div className="chuck-shell">
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
        {/* Main grid — two rows, each has 2 player cards */}
        <main className="chuck-main" data-mode={playerMode}>
          <FlameSVG />

          {/* Top row — only in 4P mode: P3 | P4 (back players) */}
          {playerMode === '4p' && (
            <div className="chuck-player-row">
              {PLAYERS_4P.filter((p) => p.id === 'p3' || p.id === 'p4').map((p) => (
                <PlayerCard
                  key={p.id}
                  player={p}
                  mapping={mapping}
                  pressedKeys={pressedKeys}
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
                />
              ))}
          </div>
        </main>

        {/* Right sidebar — Chuck AI + device scan */}
        <ChuckSidebar
          messages={messages}
          onSend={handleSend}
          isLoading={aiLoading}
          boardName={boardName}
          boardStatus={boardStatus}
          onScan={scanDevices}
          scanLoading={scanLoading}
          voiceEnabled={voiceEnabled}
          isListening={isListening}
          onVoiceToggle={() => setVoiceEnabled((v) => !v)}
        />
      </div>

      {/* ── Action Bar ── */}
      <footer className="chuck-action-bar">
        <label className={`chuck-detection-toggle ${detectionMode ? 'active' : ''}`}>
          <input
            type="checkbox"
            checked={detectionMode}
            onChange={(e) => setDetectionMode(e.target.checked)}
          />
          Input Detection Mode
        </label>

        {hasPending && (
          <span className="chuck-pending-badge">⚡ PENDING CHANGES</span>
        )}

        {flashMsg && (
          <span style={{
            fontSize: '10px',
            color: flashMsg.type === 'success' ? 'var(--chuck-green)' :
              flashMsg.type === 'error' ? 'var(--chuck-red)' : 'var(--chuck-cyan)'
          }}>
            {flashMsg.msg}
          </span>
        )}

        <div style={{ marginLeft: 'auto', display: 'flex', gap: '8px' }}>
          <button
            className="chuck-action-btn preview"
            onClick={handlePreview}
            disabled={!hasPending}
          >
            PREVIEW CHANGES
          </button>
          <button
            className="chuck-action-btn apply"
            onClick={handleApply}
            disabled={!hasPending || submitting}
          >
            {submitting ? 'APPLYING...' : 'APPLY MAPPING'}
          </button>
          <button className="chuck-action-btn reset" onClick={handleReset}>
            FACTORY RESET
          </button>
        </div>
      </footer>
    </div>
  );
}

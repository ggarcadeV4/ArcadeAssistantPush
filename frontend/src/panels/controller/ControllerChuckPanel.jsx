import React, { useState, useEffect, useCallback, useMemo, useRef, memo } from 'react';
import { controllerAIChat } from '../../services/controllerAI';
import { logChatHistory } from '../../services/supabaseClient';
import { useControllerEvents } from '../../hooks/useControllerEvents';
import { useInputDetection } from '../../hooks/useInputDetection';
import { speak, stopSpeaking } from '../../services/ttsClient';
import { useProfileContext } from '../../context/ProfileContext';
import {
  fetchBaseline,
  fetchCascadeStatus,
  getCascadePollInterval,
  getCascadePreference,
  requestCascade,
  setCascadePreference,
} from './apiHelpers';
import { normalizeProfileList } from './utils/profileUtils';
import './controller-chuck.css';

// API base URLs - use relative paths to route through gateway
const API_BASE = '/api/local/controller';
const HARDWARE_API = '/api/local/hardware';

// Chuck's Brooklyn personality responses
const CHUCK_RESPONSES = {
  welcome: "Yo! Chuck here. I'm your go-to guy for wirin' up these arcade boards. Let's get this cabinet hummin'!",
  loadSuccess: "Alright, got your mappings loaded. Lookin' good!",
  loadError: "Ey, somethin' ain't right. Can't load the mappings. Check the backend?",
  previewReady: "Here's whatcha got. Take a look before we wire it up.",
  applySuccess: "Boom! Mappings applied. Backed up the old one just in case.",
  applyError: "Whoa, hold up. Got some errors here. Fix 'em before we continue.",
  resetConfirm: "You sure? This'll restore Greg's factory defaults. Can't undo this easily.",
  resetSuccess: "Done! Back to factory defaults. Fresh start, pal.",
  pinConflict: "Hey! Ya got two controls fightin' for the same pin. That ain't gonna work."
};

const STATUS_LABELS = {
  completed: 'Completed',
  failed: 'Failed',
  running: 'In Progress',
  queued: 'Queued',
  blocked: 'Pending Integration',
  skipped: 'Skipped',
  unknown: 'Unknown',
};

const STATUS_CLASS_MAP = {
  completed: 'status-success',
  failed: 'status-error',
  running: 'status-warning',
  queued: 'status-warning',
  blocked: 'status-warning',
  skipped: 'status-neutral',
  degraded: 'status-warning',
  healthy: 'status-success',
};

const CHUCK_VOICE_ID = 'f5HLTX707KIM4SzJYzSz';  // Chuck's Brooklyn voice

const MicIcon = ({ active = false }) => (
  <svg
    viewBox="0 0 16 16"
    width="16"
    height="16"
    aria-hidden="true"
    focusable="false"
    className={`chuck-mic-icon ${active ? 'is-active' : ''}`}
  >
    <path
      d="M6 3.5a2 2 0 1 1 4 0v3a2 2 0 1 1-4 0z"
      fill="none"
      stroke="currentColor"
      strokeWidth="1.4"
      strokeLinecap="round"
    />
    <path
      d="M4.5 7.5a3.5 3.5 0 0 0 7 0"
      fill="none"
      stroke="currentColor"
      strokeWidth="1.2"
      strokeLinecap="round"
    />
    <path
      d="M8 11.5v3"
      stroke="currentColor"
      strokeWidth="1.2"
      strokeLinecap="round"
    />
    <path
      d="M5.5 14.5h5"
      stroke="currentColor"
      strokeWidth="1.1"
      strokeLinecap="round"
    />
  </svg>
);

const formatTimestamp = (value) => {
  if (!value) return null;
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return null;
  return date.toLocaleString();
};

const StatusPill = memo(({ label, status, message, lastSynced, onClick }) => {
  const statusKey = (status || 'unknown').toLowerCase();
  const className = `cascade-status-pill ${STATUS_CLASS_MAP[statusKey] || 'status-neutral'} ${onClick ? 'is-clickable' : ''
    }`;
  const resolvedLabel = STATUS_LABELS[statusKey] || status || 'Unknown';
  const tooltip = message ? `${label}: ${message}` : resolvedLabel;
  const lastSyncedLabel = formatTimestamp(lastSynced);

  const handleClick = useCallback(() => {
    if (onClick) {
      onClick({ label, status, message, lastSynced });
    }
  }, [onClick, label, status, message, lastSynced]);

  const PillTag = onClick ? 'button' : 'div';

  const interactiveProps = onClick
    ? { type: 'button', onClick: handleClick }
    : {};

  return (
    <div className={`cascade-status-item ${statusKey === 'failed' ? 'status-item-failed' : ''}`}>
      <div className="cascade-status-label">{label}</div>
      <PillTag
        className={className}
        title={tooltip}
        {...interactiveProps}
      >
        {resolvedLabel}
      </PillTag>
      {message && <div className="cascade-status-note">{message}</div>}
      {lastSyncedLabel && (
        <div className="cascade-status-meta" title={`Last synced ${lastSyncedLabel}`}>
          Last synced {lastSyncedLabel}
        </div>
      )}
    </div>
  );
});
StatusPill.displayName = 'StatusPill';

const CascadeStatusCard = memo(({ baseline, cascade, onRetry, onRetryFailed, loading, error }) => {
  const [expanded, setExpanded] = useState(false);
  const [detail, setDetail] = useState(null);

  const updatedAt = baseline?.updated_at ? new Date(baseline.updated_at).toLocaleString() : '??"';
  const cascadeStatus = cascade?.status || 'unknown';
  const currentJob = cascade?.job;
  const ledStatus = baseline?.led?.status || 'unknown';
  const ledMessage = baseline?.led?.message || null;

  const emulatorStatusItems = useMemo(() => {
    if (!baseline?.emulators) return [];
    return Object.entries(baseline.emulators).map(([key, value]) => ({
      key,
      status: value?.status || 'unknown',
      message: value?.message || null,
      last_synced: value?.last_synced || null,
    }));
  }, [baseline]);

  const failedEmulators = useMemo(
    () => emulatorStatusItems.filter((item) => item.status === 'failed'),
    [emulatorStatusItems]
  );

  const MAX_VISIBLE = 6;
  const hasMore = emulatorStatusItems.length > MAX_VISIBLE;
  const visibleItems = expanded ? emulatorStatusItems : emulatorStatusItems.slice(0, MAX_VISIBLE);

  const toggleExpanded = useCallback(() => {
    setExpanded((prev) => !prev);
  }, []);

  const handleRetryFailed = useCallback(() => {
    if (!onRetryFailed || failedEmulators.length === 0) return;
    onRetryFailed(failedEmulators);
  }, [failedEmulators, onRetryFailed]);

  const handleStatusDetail = useCallback((item) => {
    if (!item?.message) {
      setDetail(null);
      return;
    }
    setDetail({
      label: item.label,
      status: item.status,
      message: item.message,
      lastSynced: item.lastSynced,
    });
  }, []);

  const clearDetail = useCallback(() => setDetail(null), []);

  return (
    <div className="cascade-status-card">
      <div className="cascade-status-header">
        <div>
          <div className="cascade-status-title">Cascade Status</div>
          <div className="cascade-status-subtitle">Baseline updated: {updatedAt}</div>
        </div>
        <div className="cascade-status-actions">
          {failedEmulators.length > 0 && (
            <button
              className="cascade-status-retry-failed"
              onClick={handleRetryFailed}
              disabled={loading}
            >
              Retry Failed ({failedEmulators.length})
            </button>
          )}
          <button
            className="cascade-status-retry"
            onClick={onRetry}
            disabled={loading}
          >
            {loading ? 'Retrying...' : 'Retry Cascade'}
          </button>
        </div>
      </div>

      {error && <div className="cascade-status-error">{error}</div>}

      <div className="cascade-status-grid">
        <StatusPill
          label="Cascade"
          status={cascadeStatus}
          message={currentJob?.message}
          onClick={currentJob?.message ? handleStatusDetail : undefined}
        />
        <StatusPill
          label="LED Blinky"
          status={ledStatus}
          message={ledMessage}
          onClick={ledMessage ? handleStatusDetail : undefined}
        />
      </div>

      <div className={`cascade-status-grid cascade-status-emulators ${expanded ? 'expanded' : ''}`}>
        {visibleItems.length === 0 ? (
          <div className="cascade-status-empty">
            No emulator cascade jobs discovered yet.
          </div>
        ) : (
          visibleItems.map((item) => (
            <StatusPill
              key={item.key}
              label={item.key.toUpperCase()}
              status={item.status}
              message={item.message}
              lastSynced={item.last_synced}
              onClick={item.message ? handleStatusDetail : undefined}
            />
          ))
        )}
      </div>

      {hasMore && (
        <button
          className="cascade-status-toggle"
          onClick={toggleExpanded}
        >
          {expanded
            ? 'Show Less'
            : `Show ${emulatorStatusItems.length - MAX_VISIBLE} More`}
        </button>
      )}

      {detail?.message && (
        <div className="cascade-status-detail">
          <div className="cascade-status-detail-header">
            <div>
              <div className="cascade-status-detail-label">{detail.label}</div>
              {detail.lastSynced && (
                <div className="cascade-status-detail-meta">
                  Last synced {formatTimestamp(detail.lastSynced)}
                </div>
              )}
            </div>
            <button className="cascade-status-detail-close" onClick={clearDetail}>
              Close
            </button>
          </div>
          <div className="cascade-status-detail-message">{detail.message}</div>
        </div>
      )}
    </div>
  );
});
CascadeStatusCard.displayName = 'CascadeStatusCard';

const InputDetectionPanel = memo(({ enabled, active, latestInput, error, flash, onOpenDiagnostics }) => {
  const timestampLabel = latestInput?.timestamp
    ? new Date(latestInput.timestamp * 1000).toLocaleTimeString()
    : null;

  const rows = useMemo(() => {
    if (!latestInput) return [];
    return [
      { label: 'Control', value: latestInput.control_key },
      { label: 'Pin', value: latestInput.pin },
      { label: 'Player', value: latestInput.player ? `P${latestInput.player}` : null },
      { label: 'Type', value: latestInput.control_type },
      { label: 'Keycode', value: latestInput.keycode },
    ].filter((row) => row.value !== null && row.value !== undefined && row.value !== '');
  }, [latestInput]);

  return (
    <div className={`input-detection-card ${active ? 'active' : ''} ${flash ? 'flash' : ''}`}>
      <div className="input-detection-header">
        <div>
          <div className="input-detection-title">Input Detection</div>
          <div className="input-detection-status">
            {active ? 'Listening for encoder input...' : 'Idle'}
            {timestampLabel && (
              <span className="input-detection-status-time">Last: {timestampLabel}</span>
            )}
          </div>
        </div>
        <div className="input-detection-actions">
          <span className={`input-detection-pill ${enabled ? 'enabled' : 'disabled'}`}>
            {enabled ? 'Detection Mode On' : 'Detection Mode Off'}
          </span>
          {onOpenDiagnostics && (
            <button
              type="button"
              className="chuck-btn chuck-btn-secondary input-detection-diagnostics-btn"
              onClick={onOpenDiagnostics}
            >
              Open Diagnostics
            </button>
          )}
        </div>
      </div>

      {error && <div className="input-detection-error">{error}</div>}

      {rows.length > 0 ? (
        <div className="input-detection-grid">
          {rows.map((row) => (
            <div className="input-detection-row" key={row.label}>
              <span className="label">{row.label}</span>
              <span className="value">{row.value}</span>
            </div>
          ))}
        </div>
      ) : (
        <div className="input-detection-placeholder">
          Enable detection mode, then press any control on the encoder to preview its mapping.
        </div>
      )}
    </div>
  );
});
InputDetectionPanel.displayName = 'InputDetectionPanel';

const DeviceStatusCard = memo(({ devices = [], error, hints = [], loading, lastScan, onScan }) => {
  const boardDevices = useMemo(
    () => devices.filter((device) => device.type === 'arcade_board'),
    [devices]
  );
  const otherDevices = useMemo(
    () => devices.filter((device) => device.type !== 'arcade_board'),
    [devices]
  );
  const lastScanLabel = lastScan ? new Date(lastScan).toLocaleTimeString() : 'Never';
  const hasDevices = devices.length > 0;

  return (
    <div className="device-status-card">
      <div className="device-status-header">
        <div>
          <div className="device-status-title">Device Scan</div>
          <div className="device-status-meta">Last scan: {lastScanLabel}</div>
        </div>
        <button
          type="button"
          className="chuck-btn chuck-btn-secondary device-status-scan-btn"
          onClick={onScan}
          disabled={loading}
        >
          {loading ? 'Scanning...' : 'Scan Devices'}
        </button>
      </div>

      {error && <div className="device-status-error">{error}</div>}

      {!hasDevices && !error && (
        <div className="device-status-empty">
          No devices detected yet. Plug in your encoder and run Scan Devices.
        </div>
      )}

      {boardDevices.length > 0 && (
        <div className="device-status-section">
          <div className="device-status-section-title">Encoder Boards</div>
          {boardDevices.map((device, index) => (
            <div className="device-status-row" key={`${device.vid}-${device.pid}-${index}`}>
              <div>
                <div className="device-status-name">{device.name || 'Unknown Board'}</div>
                <div className="device-status-detail">
                  VID: {device.vid || 'n/a'} | PID: {device.pid || 'n/a'}
                </div>
              </div>
              <span
                className={`device-status-pill ${device.detected ? 'status-success' : 'status-warning'
                  }`}
              >
                {device.status || (device.detected ? 'Detected' : 'Unknown')}
              </span>
            </div>
          ))}
        </div>
      )}

      {otherDevices.length > 0 && (
        <div className="device-status-section">
          <div className="device-status-section-title">Other Devices</div>
          {otherDevices.map((device, index) => (
            <div className="device-status-row" key={`${device.vendor_id}-${device.product_id}-${index}`}>
              <div>
                <div className="device-status-name">{device.name || 'Unknown Device'}</div>
                <div className="device-status-detail">
                  Type: {device.device_class || 'controller'}{' '}
                  {device.vendor_id && device.product_id && (
                    <>| VID: {device.vendor_id} PID: {device.product_id}</>
                  )}
                </div>
              </div>
              <span
                className={`device-status-pill ${device.profile_exists ? 'status-success' : 'status-warning'
                  }`}
              >
                {device.profile_exists ? 'Configured' : 'Needs Setup'}
              </span>
            </div>
          ))}
        </div>
      )}

      {hints.length > 0 && (
        <div className="device-status-hints">
          <div className="device-status-section-title">Hints</div>
          <ul>
            {hints.map((hint, index) => (
              <li key={`hint-${index}`}>{hint}</li>
            ))}
          </ul>
        </div>
      )}
    </div>
  );
});
DeviceStatusCard.displayName = 'DeviceStatusCard';

const CascadePreviewSummary = memo(({ cascadePreview }) => {
  if (!cascadePreview) return null;

  const changedControls = Array.isArray(cascadePreview.changed_controls)
    ? cascadePreview.changed_controls
    : [];

  const needsCascade = cascadePreview.needs_cascade;
  const currentJob = cascadePreview.baseline?.current_job;

  return (
    <div className="cascade-preview-card">
      <div className="cascade-preview-header">
        <span className="cascade-preview-title">Cascade Summary</span>
        <span className={`cascade-preview-pill ${needsCascade ? 'pill-required' : 'pill-ok'}`}>
          {needsCascade ? 'Cascade Recommended' : 'No Cascade Needed'}
        </span>
      </div>

      {needsCascade && changedControls.length > 0 && (
        <div className="cascade-preview-section">
          <div className="cascade-preview-section-title">Changed Controls</div>
          <ul>
            {changedControls.map(control => (
              <li key={control}>{control}</li>
            ))}
          </ul>
        </div>
      )}

      {currentJob && (
        <div className="cascade-preview-section">
          <div className="cascade-preview-section-title">Current Cascade Job</div>
          <div className="cascade-preview-job">
            <div>Status: {currentJob.status || 'unknown'}</div>
            {currentJob.message && <div>Message: {currentJob.message}</div>}
          </div>
        </div>
      )}
    </div>
  );
});
CascadePreviewSummary.displayName = 'CascadePreviewSummary';

// Memoized Player Section Component
const PlayerSection = memo(({ player, controls, onPinClick, highlightedKey, isActive }) => {
  const playerNum = player.charAt(1);

  const buttonCount = useMemo(() =>
    controls.filter(c =>
      c.type === 'button' &&
      !c.key.includes('coin') &&
      !c.key.includes('start')
    ).length,
    [controls]
  );

  const handlePinClick = useCallback((control) => {
    onPinClick && onPinClick(control);
  }, [onPinClick]);

  return (
    <div className={`chuck-player-section ${isActive ? 'active' : ''}`} id={`player-section-${player}`}>
      <div className="chuck-player-header">
        <span className="chuck-player-badge">P{playerNum}</span>
        <span className="chuck-button-count">{buttonCount} Buttons</span>
      </div>

      <div className="chuck-pin-grid">
        {controls.map(control => {
          const controlId = `control-${control.key.replace(/\./g, '-')}`;
          return (
            <div
              key={control.key}
              id={controlId}
              className={`chuck-pin-item ${highlightedKey === control.key ? 'highlighted' : ''}`}
              onClick={() => handlePinClick(control)}
              title={`${control.label} - Pin ${control.pin}`}
            >
              <div className="chuck-pin-number">Pin {control.pin}</div>
              <div className="chuck-pin-label">{control.label}</div>
              <div className={`chuck-pin-type chuck-pin-type-${control.type}`}>
                {control.type}
              </div>
            </div>
          );
        })}
      </div>
    </div>
  );
});
PlayerSection.displayName = 'PlayerSection';

// Memoized PinMappingGrid Component
const PinMappingGrid = memo(({ mappings, onPinClick, highlightedKey, activePlayer }) => {
  // Group mappings by player with memoization
  const playerGroups = useMemo(() => {
    const groups = { p1: [], p2: [], p3: [], p4: [] };

    Object.entries(mappings || {}).forEach(([key, data]) => {
      const match = key.match(/^(p[1-4])\./);
      if (match) {
        groups[match[1]].push({ key, ...data });
      }
    });

    return groups;
  }, [mappings]);

  return (
    <div className="chuck-mapping-grid">
      <PlayerSection
        player="p1"
        controls={playerGroups.p1}
        onPinClick={onPinClick}
        highlightedKey={highlightedKey}
        isActive={activePlayer === 'p1'}
      />
      <PlayerSection
        player="p2"
        controls={playerGroups.p2}
        onPinClick={onPinClick}
        highlightedKey={highlightedKey}
        isActive={activePlayer === 'p2'}
      />
      <PlayerSection
        player="p3"
        controls={playerGroups.p3}
        onPinClick={onPinClick}
        highlightedKey={highlightedKey}
        isActive={activePlayer === 'p3'}
      />
      <PlayerSection
        player="p4"
        controls={playerGroups.p4}
        onPinClick={onPinClick}
        highlightedKey={highlightedKey}
        isActive={activePlayer === 'p4'}
      />
    </div>
  );
});
PinMappingGrid.displayName = 'PinMappingGrid';

// Memoized BoardStatus Component with optimized API calls
const BoardStatus = memo(({ board, onBoardChange }) => {
  const [supportedBoards, setSupportedBoards] = useState([]);
  const [showBoardSelector, setShowBoardSelector] = useState(false);
  const [hints, setHints] = useState([]);
  const detected = board?.detected || false;

  // Use ref to track if we've already loaded boards
  const boardsLoadedRef = useRef(false);

  // Fetch supported boards only once
  useEffect(() => {
    if (boardsLoadedRef.current) return;

    const loadSupportedBoards = async () => {
      try {
        const response = await fetch(`${HARDWARE_API}/arcade/boards/supported`);
        if (response.ok) {
          const data = await response.json();
          setSupportedBoards(data.boards || []);
          boardsLoadedRef.current = true;
        }
      } catch (error) {
        console.error('Failed to load supported boards:', error);
      }
    };

    loadSupportedBoards();
  }, []);

  // Optimized hints loading with early exit
  useEffect(() => {
    if (detected || !board?.vid || !board?.pid) {
      setHints([]);
      return;
    }

    const loadHints = async () => {
      try {
        const response = await fetch(`${HARDWARE_API}/troubleshooting?board_type=keyboard_encoder`);
        if (response.ok) {
          const data = await response.json();
          setHints(data.hints?.slice(0, 3) || []);
        }
      } catch (error) {
        console.error('Failed to load hints:', error);
      }
    };

    loadHints();
  }, [detected, board?.vid, board?.pid]);

  const handleBoardSelect = useCallback((selectedBoard) => {
    if (onBoardChange) {
      onBoardChange({
        vid: selectedBoard.vid,
        pid: selectedBoard.pid,
        name: selectedBoard.name,
        vendor: selectedBoard.vendor,
        modes: selectedBoard.modes,
        board_type: selectedBoard.board_type
          || (selectedBoard.vendor?.toLowerCase().includes('pacto') ? 'pactotech' : undefined),
      });
    }
    setShowBoardSelector(false);
  }, [onBoardChange]);

  const toggleBoardSelector = useCallback(() => {
    setShowBoardSelector(prev => !prev);
  }, []);

  const closeBoardSelector = useCallback(() => {
    setShowBoardSelector(false);
  }, []);

  return (
    <div className={`chuck-board-status ${detected ? 'detected' : 'not-detected'}`}>
      <div className="chuck-board-icon">{detected ? '🔌' : '⚠️'}</div>
      <div className="chuck-board-info">
        <div className="chuck-board-header-row">
          <div className="chuck-board-name">{board?.name || 'Unknown Board'}</div>
          <button
            className="chuck-board-select-btn"
            onClick={toggleBoardSelector}
            title="Select a different board"
          >
            ⚙️
          </button>
        </div>

        {board?.vendor && (
          <div className="chuck-board-vendor">{board.vendor}</div>
        )}

        <div className="chuck-board-vid-pid">
          VID: {board?.vid || 'N/A'} | PID: {board?.pid || 'N/A'}
        </div>

        {board?.manufacturer_string && (
          <div className="chuck-board-manufacturer">
            {board.manufacturer_string}
            {board.product_string && ` - ${board.product_string}`}
          </div>
        )}

        {board?.board_type === 'pactotech' && (
          <div className="chuck-board-note">
            Optimized Pacto Tech encoder detected. 9-panel inputs are fully mapped.
          </div>
        )}

        <div className="chuck-board-modes">
          {board?.modes?.interlock && <span className="chuck-mode-badge">Interlock</span>}
          {board?.modes?.turbo && <span className="chuck-mode-badge">Turbo</span>}
          {board?.modes?.six_button && <span className="chuck-mode-badge">6-Button</span>}
          {board?.modes?.nine_panel && <span className="chuck-mode-badge">9-Panel</span>}
          {board?.modes?.macro && <span className="chuck-mode-badge">Macro</span>}
        </div>

        {board?.detection_error && (
          <div className="chuck-detection-error">
            ⚠️ {board.detection_error}
          </div>
        )}
      </div>

      <div className={`chuck-board-status-indicator ${detected ? 'online' : 'offline'}`}>
        {detected ? 'Connected' : 'Not Detected'}
      </div>

      {/* Board Selector Dropdown */}
      {showBoardSelector && (
        <div className="chuck-board-selector">
          <div className="chuck-board-selector-header">
            Select Arcade Board
            <button
              className="chuck-board-selector-close"
              onClick={closeBoardSelector}
            >
              ×
            </button>
          </div>
          <div className="chuck-board-selector-list">
            {supportedBoards.map(b => (
              <div
                key={b.vid_pid}
                className={`chuck-board-option ${b.vid === board?.vid && b.pid === board?.pid ? 'selected' : ''}`}
                onClick={() => handleBoardSelect(b)}
              >
                <div className="chuck-board-option-name">{b.name}</div>
                <div className="chuck-board-option-vendor">{b.vendor}</div>
                <div className="chuck-board-option-vid-pid">{b.vid_pid}</div>
              </div>
            ))}
          </div>
        </div>
      )}

      {/* Troubleshooting Hints */}
      {!detected && hints.length > 0 && (
        <div className="chuck-troubleshooting-hints">
          <div className="chuck-hints-header">Connection Troubleshooting:</div>
          <ul className="chuck-hints-list">
            {hints.map((hint, i) => (
              <li key={i}>{hint}</li>
            ))}
          </ul>
        </div>
      )}
    </div>
  );
});
BoardStatus.displayName = 'BoardStatus';

// Memoized DiffViewer Component
const DiffViewer = memo(({ diff, show }) => {
  if (!show || !diff) return null;

  return (
    <div className="chuck-diff-viewer">
      <div className="chuck-diff-header">Changes Preview</div>
      <pre className="chuck-diff-content">{diff}</pre>
    </div>
  );
});
DiffViewer.displayName = 'DiffViewer';

// Memoized MAMEConfigModal Component
const MAMEConfigModal = memo(({ show, preview, onApply, onCancel }) => {
  if (!show || !preview) return null;

  const { xml_content, validation, summary } = preview;
  const isValid = validation?.valid || false;

  const handleOverlayClick = useCallback((e) => {
    onCancel();
  }, [onCancel]);

  const handleModalClick = useCallback((e) => {
    e.stopPropagation();
  }, []);

  return (
    <div className="chuck-mame-modal-overlay" onClick={handleOverlayClick}>
      <div className="chuck-mame-modal" onClick={handleModalClick}>
        <div className="chuck-mame-modal-header">
          <h3>MAME Config Preview</h3>
          <button
            className="chuck-mame-modal-close"
            onClick={onCancel}
            title="Close preview"
          >
            ×
          </button>
        </div>

        <div className="chuck-mame-modal-body">
          {/* Summary Stats */}
          <div className="chuck-mame-summary">
            <div className="chuck-mame-summary-item">
              <span className="chuck-mame-summary-label">Ports:</span>
              <span className="chuck-mame-summary-value">{summary?.port_count || 0}</span>
            </div>
            <div className="chuck-mame-summary-item">
              <span className="chuck-mame-summary-label">Players:</span>
              <span className="chuck-mame-summary-value">{summary?.player_count || 0}</span>
            </div>
            <div className="chuck-mame-summary-item">
              <span className="chuck-mame-summary-label">Status:</span>
              <span className={`chuck-mame-summary-value ${isValid ? 'valid' : 'invalid'}`}>
                {isValid ? '✓ Valid' : '⚠ Invalid'}
              </span>
            </div>
          </div>

          {/* Players List */}
          {summary?.players && summary.players.length > 0 && (
            <div className="chuck-mame-players">
              <div className="chuck-mame-players-label">Configured Players:</div>
              <div className="chuck-mame-players-list">
                {summary.players.map(player => (
                  <span key={player} className="chuck-mame-player-badge">{player}</span>
                ))}
              </div>
            </div>
          )}

          {/* Validation Errors */}
          {!isValid && validation?.errors && validation.errors.length > 0 && (
            <div className="chuck-mame-errors">
              <div className="chuck-mame-errors-header">Validation Errors:</div>
              <ul className="chuck-mame-errors-list">
                {validation.errors.map((error, i) => (
                  <li key={i}>{error}</li>
                ))}
              </ul>
            </div>
          )}

          {/* XML Preview */}
          <div className="chuck-mame-xml-preview">
            <div className="chuck-mame-xml-header">Generated XML:</div>
            <pre className="chuck-mame-xml-content">{xml_content}</pre>
          </div>
        </div>

        <div className="chuck-mame-modal-footer">
          <button
            className="chuck-btn chuck-btn-reset"
            onClick={onCancel}
          >
            Cancel
          </button>
          <button
            className="chuck-btn chuck-btn-apply"
            onClick={onApply}
            disabled={!isValid}
          >
            Apply Config
          </button>
        </div>
      </div>
    </div>
  );
});
MAMEConfigModal.displayName = 'MAMEConfigModal';

// Memoized PinEditModal Component
const PinEditModal = memo(({ show, control, onSave, onCancel, existingPins, onApplyImmediately }) => {
  const [pinNumber, setPinNumber] = useState(control?.pin || '');
  const [error, setError] = useState('');
  const [autoDetected, setAutoDetected] = useState(false);
  const [applyImmediately, setApplyImmediately] = useState(true); // Default to immediate save

  // Enable input detection when modal is open
  const { latestInput, isActive: detectionActive } = useInputDetection(show);

  useEffect(() => {
    if (control) {
      setPinNumber(control.pin);
      setError('');
      setAutoDetected(false);
    }
  }, [control]);

  // Auto-fill pin number when input is detected
  useEffect(() => {
    if (latestInput && latestInput.pin && show) {
      setPinNumber(latestInput.pin);
      setAutoDetected(true);
      setError(''); // Clear any errors
    }
  }, [latestInput, show]);

  const handleSave = useCallback(() => {
    const pin = parseInt(pinNumber);

    // Validation
    if (isNaN(pin) || pin < 1 || pin > 32) {
      setError('Pin must be between 1 and 32');
      return;
    }

    // Check for conflicts (excluding current control)
    if (existingPins && existingPins.some(p => p.pin === pin && p.key !== control?.key)) {
      setError(`Pin ${pin} is already assigned to another control`);
      return;
    }

    // If immediate apply is enabled, trigger full save workflow
    if (applyImmediately && onApplyImmediately) {
      onApplyImmediately(control.key, pin);
    } else {
      // Otherwise just add to pending changes
      onSave(control.key, pin);
    }
  }, [pinNumber, existingPins, control, onSave, applyImmediately, onApplyImmediately]);

  const handleKeyPress = useCallback((e) => {
    if (e.key === 'Enter') handleSave();
  }, [handleSave]);

  const handlePinChange = useCallback((e) => {
    setPinNumber(e.target.value);
    setError('');
  }, []);

  const handleOverlayClick = useCallback(() => {
    onCancel();
  }, [onCancel]);

  const handleModalClick = useCallback((e) => {
    e.stopPropagation();
  }, []);

  if (!show || !control) return null;

  return (
    <div className="chuck-pin-edit-overlay" onClick={handleOverlayClick}>
      <div className="chuck-pin-edit-modal" onClick={handleModalClick}>
        <div className="chuck-pin-edit-header">
          <h3>Edit Pin Assignment</h3>
          <button className="chuck-pin-edit-close" onClick={onCancel}>×</button>
        </div>

        <div className="chuck-pin-edit-body">
          <div className="chuck-pin-edit-info">
            <strong>{control.label}</strong>
            <span className="chuck-pin-edit-type">{control.type}</span>
          </div>

          {detectionActive && (
            <div className="chuck-pin-edit-hint">
              {autoDetected ? (
                <span style={{ color: '#c8ff00' }}>✓ Detected! Pin {pinNumber}</span>
              ) : (
                <span style={{ color: '#00e5ff' }}>🎮 Press the button on your control panel...</span>
              )}
            </div>
          )}

          <div className="chuck-pin-edit-field">
            <label htmlFor="pin-input">Pin Number (1-32):</label>
            <input
              id="pin-input"
              type="number"
              min="1"
              max="32"
              value={pinNumber}
              onChange={handlePinChange}
              onKeyPress={handleKeyPress}
              autoFocus
            />
          </div>

          {error && (
            <div className="chuck-pin-edit-error">⚠️ {error}</div>
          )}

          <div className="chuck-pin-edit-option">
            <label>
              <input
                type="checkbox"
                checked={applyImmediately}
                onChange={(e) => setApplyImmediately(e.target.checked)}
              />
              <span>Save immediately to file (recommended)</span>
            </label>
            {!applyImmediately && (
              <div className="chuck-pin-edit-note">
                Changes will be pending. Click "Preview" then "Apply" to save.
              </div>
            )}
          </div>
        </div>

        <div className="chuck-pin-edit-footer">
          <button className="chuck-btn chuck-btn-reset" onClick={onCancel}>
            Cancel
          </button>
          <button className="chuck-btn chuck-btn-apply" onClick={handleSave}>
            {applyImmediately ? 'Save & Apply' : 'Save to Pending'}
          </button>
        </div>
      </div>
    </div>
  );
});
PinEditModal.displayName = 'PinEditModal';

// Memoized CascadePromptModal Component
const CascadePromptModal = memo(({
  show,
  summary,
  rememberChoice,
  onRememberChange,
  onCascade,
  onSkip,
}) => {
  const handleOverlayClick = useCallback(() => {
    onSkip();
  }, [onSkip]);

  const handleModalClick = useCallback((e) => {
    e.stopPropagation();
  }, []);

  if (!show) return null;

  const changedControls = Array.isArray(summary?.changed_controls) ? summary.changed_controls : [];
  const needsCascade = summary?.needs_cascade ?? true;

  return (
    <div className="chuck-cascade-modal-overlay" onClick={handleOverlayClick}>
      <div className="chuck-cascade-modal" onClick={handleModalClick}>
        <h3>Cascade Controller Updates?</h3>
        <p>
          {needsCascade
            ? 'Applying the cascade will sync LED Blinky and emulator configs with your latest mapping.'
            : 'No downstream changes detected, but you can run the cascade if you want to refresh statuses.'}
        </p>

        {changedControls.length > 0 && (
          <div className="chuck-cascade-change-list">
            <div className="chuck-cascade-change-title">Changed Controls</div>
            <ul>
              {changedControls.map(control => (
                <li key={control}>{control}</li>
              ))}
            </ul>
          </div>
        )}

        <label className="chuck-cascade-remember">
          <input
            type="checkbox"
            checked={rememberChoice}
            onChange={(e) => onRememberChange(e.target.checked)}
          />
          Remember my choice
        </label>

        <div className="chuck-cascade-modal-actions">
          <button className="chuck-btn chuck-btn-secondary" onClick={onSkip}>
            Skip for Now
          </button>
          <button className="chuck-btn chuck-btn-primary" onClick={onCascade}>
            Cascade Now
          </button>
        </div>
      </div>
    </div>
  );
});
CascadePromptModal.displayName = 'CascadePromptModal';

const DiagnosticsModal = memo(({
  show,
  mapping,
  latestInput,
  highlightedKey,
  detectionActive,
  activePlayer,
  onClose
}) => {
  const details = useMemo(() => {
    if (!latestInput) return [];
    return [
      { label: 'Control', value: latestInput.control_key },
      { label: 'Pin', value: latestInput.pin },
      { label: 'Player', value: latestInput.player ? `P${latestInput.player}` : null },
      { label: 'Type', value: latestInput.control_type },
      { label: 'Keycode', value: latestInput.keycode }
    ].filter((item) => item.value !== null && item.value !== undefined && item.value !== '');
  }, [latestInput]);

  const handleOverlayClick = useCallback(() => {
    onClose?.();
  }, [onClose]);

  const handleModalClick = useCallback((event) => {
    event.stopPropagation();
  }, []);

  if (!show) return null;

  return (
    <div className="chuck-diagnostics-overlay" onClick={handleOverlayClick}>
      <div className="chuck-diagnostics-modal" onClick={handleModalClick}>
        <div className="chuck-diagnostics-header">
          <div>
            <h3>Diagnostics</h3>
            <div className="chuck-diagnostics-subtitle">
              {detectionActive ? 'Listening for live input' : 'Enable detection to monitor hardware'}
            </div>
          </div>
          <button type="button" className="chuck-diagnostics-close" onClick={onClose}>
            A-
          </button>
        </div>

        <div className="chuck-diagnostics-body">
          <div className="chuck-diagnostics-info">
            <div className={`input-detection-pill ${detectionActive ? 'enabled' : 'disabled'}`}>
              {detectionActive ? 'Detection Active' : 'Detection Idle'}
            </div>
            {details.length > 0 ? (
              <div className="chuck-diagnostics-grid-info">
                {details.map((detail) => (
                  <div key={detail.label} className="chuck-diagnostics-row">
                    <span className="label">{detail.label}</span>
                    <span className="value">{detail.value}</span>
                  </div>
                ))}
              </div>
            ) : (
              <div className="chuck-diagnostics-placeholder">
                Press a control on your encoder to see live diagnostics.
              </div>
            )}
          </div>

          <div className="chuck-diagnostics-map">
            {mapping ? (
              <PinMappingGrid
                mappings={mapping}
                onPinClick={() => { }}
                highlightedKey={highlightedKey}
                activePlayer={activePlayer}
              />
            ) : (
              <div className="chuck-diagnostics-placeholder">
                Load a mapping to visualize the cabinet layout.
              </div>
            )}
          </div>
        </div>
      </div>
    </div>
  );
});
DiagnosticsModal.displayName = 'DiagnosticsModal';
// Memoized DeviceDetectionModal Component
const DeviceDetectionModal = memo(({ show, devices, onMirror, onCancel, isLoading }) => {
  const handleOverlayClick = useCallback(() => {
    onCancel();
  }, [onCancel]);

  const handleModalClick = useCallback((e) => {
    e.stopPropagation();
  }, []);

  if (!show) return null;

  return (
    <div className="chuck-device-modal-overlay" onClick={handleOverlayClick}>
      <div className="chuck-device-modal" onClick={handleModalClick}>
        <div className="chuck-device-modal-header">
          <h3>Auto-Detected Controllers</h3>
          <button
            className="chuck-device-modal-close"
            onClick={onCancel}
            title="Close"
          >
            ×
          </button>
        </div>

        <div className="chuck-device-modal-body">
          {!devices || devices.length === 0 ? (
            <div className="chuck-device-empty">
              <div className="chuck-device-empty-icon">🎮</div>
              <div className="chuck-device-empty-text">
                No controllers detected. Make sure they're plugged in and try again.
              </div>
            </div>
          ) : (
            <div className="chuck-device-list">
              {devices.map((device, index) => (
                <div
                  key={`${device.vendor_id}-${device.product_id}-${index}`}
                  className={`chuck-device-card ${device.profile_exists ? 'configured' : 'unconfigured'}`}
                >
                  <div className="chuck-device-info">
                    <div className="chuck-device-name">{device.name || 'Unknown Device'}</div>
                    {device.manufacturer && (
                      <div className="chuck-device-manufacturer">{device.manufacturer}</div>
                    )}
                    <div className="chuck-device-ids">
                      VID: {device.vendor_id || 'N/A'} | PID: {device.product_id || 'N/A'}
                    </div>
                    <div className="chuck-device-class">
                      Type: {device.device_class || 'Unknown'}
                    </div>
                  </div>

                  <div className="chuck-device-actions">
                    {device.profile_exists ? (
                      <div className="chuck-device-status-badge">Mirrored ✓</div>
                    ) : (
                      <button
                        className="chuck-btn chuck-btn-mirror"
                        onClick={() => onMirror(device)}
                        disabled={isLoading}
                      >
                        Create Profile
                      </button>
                    )}
                  </div>
                </div>
              ))}
            </div>
          )}
        </div>

        <div className="chuck-device-modal-footer">
          <div className="chuck-device-summary">
            Found {devices?.length || 0} device{devices?.length !== 1 ? 's' : ''}
            {devices?.length > 0 && ` (${devices.filter(d => !d.profile_exists).length} need setup)`}
          </div>
          <button
            className="chuck-btn chuck-btn-reset"
            onClick={onCancel}
          >
            Close
          </button>
        </div>
      </div>
    </div>
  );
});
DeviceDetectionModal.displayName = 'DeviceDetectionModal';

// Memoized ChuckChat Component
const ChuckChat = memo(({
  messages,
  onMicClick,
  isListening,
  speechSupported,
  onToggleSpeech,
  voiceEnabled
}) => {
  const [collapsed, setCollapsed] = useState(false);

  const toggleCollapse = useCallback(() => {
    setCollapsed((prev) => !prev);
  }, []);

  return (
    <div className={`chuck-chat-box ${collapsed ? 'collapsed' : ''}`}>
      <div className="chuck-chat-header">
        <div>
          <div className="chuck-chat-title">Chuck AI Assistant</div>
          <div className="chuck-chat-subtitle">Arcade wiring, emulators & diagnostics</div>
        </div>
        <div className="chuck-chat-actions">
          <button
            type="button"
            className={`chuck-chat-mic ${isListening ? 'is-listening' : ''}`}
            title={speechSupported ? (isListening ? 'Listening... click to stop' : 'Start voice input') : 'Voice input not supported in this browser'}
            onClick={speechSupported ? onMicClick : undefined}
            disabled={!speechSupported}
          >
            <MicIcon active={isListening} />
          </button>
          <button
            type="button"
            className={`chuck-chat-voice ${voiceEnabled ? 'is-enabled' : 'is-muted'}`}
            onClick={onToggleSpeech}
            title={voiceEnabled ? 'Mute Chuck\'s responses' : 'Unmute Chuck'}
          >
            {voiceEnabled ? '🔊' : '🔇'}
          </button>
          <button
            type="button"
            className="chuck-chat-close"
            onClick={toggleCollapse}
            title={collapsed ? 'Expand chat' : 'Collapse chat'}
          >
            ×
          </button>
        </div>
      </div>

      <div className="chuck-chat-body">
        <div className="chuck-avatar-section">
          <img
            src="/chuck-avatar.jpeg"
            alt="Chuck"
            className="chuck-avatar"
          />
          <div className="chuck-name">Chuck</div>
        </div>
        <div className="chuck-messages">
          {messages.map((msg, i) => (
            <div key={i} className={`chuck-message chuck-message-${msg.type}`}>
              {msg.text}
            </div>
          ))}
        </div>
      </div>
    </div>
  );
});
ChuckChat.displayName = 'ChuckChat';

// Memoized ChatInput Component
const ChatInput = memo(({ onSendMessage, isLoading }) => {
  const [input, setInput] = useState('');
  const inputRef = useRef(null);

  const handleSend = useCallback(() => {
    if (input.trim() && !isLoading) {
      onSendMessage(input);
      setInput('');
    }
  }, [input, isLoading, onSendMessage]);

  const handleKeyPress = useCallback((e) => {
    if (e.key === 'Enter' && !e.shiftKey) {
      e.preventDefault();
      handleSend();
    }
  }, [handleSend]);

  useEffect(() => {
    if (inputRef.current) {
      inputRef.current.style.height = 'auto';
      inputRef.current.style.height = Math.min(inputRef.current.scrollHeight, 120) + 'px';
    }
  }, [input]);

  return (
    <div className="chuck-chat-input-container">
      <textarea
        ref={inputRef}
        className="chuck-chat-input"
        placeholder="Ask Chuck anything..."
        value={input}
        onChange={(e) => setInput(e.target.value)}
        onKeyPress={handleKeyPress}
        disabled={isLoading}
        rows="1"
      />
      <button
        className="chuck-chat-send-btn"
        onClick={handleSend}
        disabled={!input.trim() || isLoading}
        title="Send message (Enter)"
      >
        {isLoading ? '...' : 'Send'}
      </button>
    </div>
  );
});
ChatInput.displayName = 'ChatInput';

// Feature flag for controller auto-configuration
// Note: This is a build-time fallback. The component also checks runtime status via /api/controllers/autoconfig/status
const AUTOCONFIG_BUILD_ENABLED = import.meta.env.VITE_CONTROLLER_AUTOCONFIG_ENABLED === 'true';

// Main Component with optimizations
export default function ControllerChuckPanel() {
  // Version check - to verify latest code is loaded
  console.log('[Chuck Panel] Component loaded - Version: 2025-11-18 with voice fixes');
  console.log('[Chuck Panel] Voice ID configured:', CHUCK_VOICE_ID);

  // Profile context for per-user mappings (Phase 1: display only)
  const { profile: sharedProfile } = useProfileContext();
  const currentUser = (sharedProfile?.displayName || 'Guest').trim() || 'Guest';

  // AI integration
  const [aiLoading, setAiLoading] = useState(false);
  const [chatOpen, setChatOpen] = useState(false);

  const [mapping, setMapping] = useState(null);
  const [pendingChanges, setPendingChanges] = useState({});
  const [board, setBoard] = useState(null);
  const [loading, setLoading] = useState(true);
  const [preview, setPreview] = useState(null);
  const [showDiff, setShowDiff] = useState(false);
  const [mamePreview, setMamePreview] = useState(null);
  const [showMameModal, setShowMameModal] = useState(false);
  const [editingControl, setEditingControl] = useState(null);
  const [showPinEditModal, setShowPinEditModal] = useState(false);
  const [currentPlayer, setCurrentPlayer] = useState(1);
  const [showKeyboardHelp, setShowKeyboardHelp] = useState(false);
  const [showDeviceModal, setShowDeviceModal] = useState(false);
  const [detectedDevices, setDetectedDevices] = useState([]);
  const [detectLoading, setDetectLoading] = useState(false);
  const [deviceScanLoading, setDeviceScanLoading] = useState(false);
  const [lastDeviceScan, setLastDeviceScan] = useState(null);
  const [showDiagnosticsModal, setShowDiagnosticsModal] = useState(false);
  const [voicePlaybackEnabled, setVoicePlaybackEnabled] = useState(true);
  const [isListening, setIsListening] = useState(false);
  const [speechSupported, setSpeechSupported] = useState(false);
  const [messages, setMessages] = useState([
    { type: 'assistant', text: CHUCK_RESPONSES.welcome }
  ]);

  // Stop any ongoing TTS when this panel unmounts
  useEffect(() => () => { try { stopSpeaking() } catch { } }, []);
  const [isRecording, setIsRecording] = useState(false);
  const mediaRecorderRef = useRef(null);
  const audioChunksRef = useRef([]);

  const handoffProcessedRef = useRef(null); // Track last processed handoff context
  const sessionIdRef = useRef(crypto.randomUUID()); // Persistent session ID for chat history
  const [consoleControllers, setConsoleControllers] = useState([]);
  const [consoleHints, setConsoleHints] = useState([]);
  const [consoleError, setConsoleError] = useState('');
  const [cascadeBaseline, setCascadeBaseline] = useState(null);
  const [cascadeStatus, setCascadeStatus] = useState(null);
  const [cascadeError, setCascadeError] = useState('');
  const [cascadeLoading, setCascadeLoading] = useState(false);
  const [showCascadePrompt, setShowCascadePrompt] = useState(false);
  const [rememberCascadeChoice, setRememberCascadeChoice] = useState(false);
  const [pendingCascadeSummary, setPendingCascadeSummary] = useState(null);
  const [cascadePreference, setCascadePreferenceState] = useState(() => getCascadePreference());
  const [detectionMode, setDetectionMode] = useState(false);
  const { latestInput, isActive: detectionActive, error: detectionError } = useInputDetection(detectionMode);
  const [detectionFlash, setDetectionFlash] = useState(false);
  const [highlightedControl, setHighlightedControl] = useState(null);
  const [detectionToast, setDetectionToast] = useState(null);
  const { latestEvent: controllerEvent } = useControllerEvents(false); // Disabled - SSE endpoint not implemented
  const lastControllerEventRef = useRef(null);
  const hasPendingChanges = useMemo(
    () => Object.keys(pendingChanges || {}).length > 0,
    [pendingChanges]
  );

  // Runtime autoconfig status (fetched from backend)
  const [autoconfigStatus, setAutoconfigStatus] = useState({ enabled: AUTOCONFIG_BUILD_ENABLED, checked: false });

  useEffect(() => {
    // Fetch runtime autoconfig status on mount
    const checkAutoconfigStatus = async () => {
      try {
        const resp = await fetch('/api/controllers/autoconfig/status', {
          headers: { 'x-device-id': window.AA_DEVICE_ID || 'CAB-0001' }
        });
        if (resp.ok) {
          const data = await resp.json();
          setAutoconfigStatus({ enabled: data.enabled === true, checked: true, reason: data.reason });
        }
      } catch (err) {
        // If status endpoint fails, fall back to build-time flag
        console.debug('[Chuck] Autoconfig status check failed:', err);
      }
    };
    checkAutoconfigStatus();
  }, []);

  // Compute effective autoconfig enabled state
  const AUTOCONFIG_ENABLED = autoconfigStatus.checked ? autoconfigStatus.enabled : AUTOCONFIG_BUILD_ENABLED;

  // Use refs for stable references in keyboard shortcuts
  const previewRef = useRef(preview);
  const handleResetRef = useRef(null);
  const handleTestPreviewRef = useRef(null);
  const handleTestApplyRef = useRef(null);

  // Update refs when values change
  useEffect(() => {
    previewRef.current = preview;
  }, [preview]);

  const highlightTimeoutRef = useRef(null);
  const toastTimeoutRef = useRef(null);
  const recognitionRef = useRef(null);

  useEffect(() => {
    if (!latestInput?.control_key) return;

    setDetectionFlash(true);
    if (highlightTimeoutRef.current) clearTimeout(highlightTimeoutRef.current);
    if (toastTimeoutRef.current) clearTimeout(toastTimeoutRef.current);

    const controlKey = latestInput.control_key;
    setHighlightedControl(controlKey);
    setDetectionToast(`Detected: ${controlKey.toUpperCase()} | Pin ${latestInput.pin || 'n/a'}`);

    loadMapping({ silent: true });

    const elementId = `control-${controlKey.replace(/\./g, '-')}`;
    const element = document.getElementById(elementId);
    if (element) {
      element.scrollIntoView({ behavior: 'smooth', block: 'center' });
    }

    const flashTimer = setTimeout(() => setDetectionFlash(false), 800);
    highlightTimeoutRef.current = setTimeout(() => setHighlightedControl(null), 2200);
    toastTimeoutRef.current = setTimeout(() => setDetectionToast(null), 3000);

    return () => {
      clearTimeout(flashTimer);
    };
  }, [latestInput]);  // loadMapping is stable (useCallback), no need in deps

  useEffect(() => {
    return () => {
      if (highlightTimeoutRef.current) clearTimeout(highlightTimeoutRef.current);
      if (toastTimeoutRef.current) clearTimeout(toastTimeoutRef.current);
    };
  }, []);

  useEffect(() => {
    if (!detectionMode) {
      setDetectionToast(null);
      setHighlightedControl(null);
    }
  }, [detectionMode]);

  useEffect(() => {
    setCascadePreference(cascadePreference);
  }, [cascadePreference]);

  const addMessage = useCallback((text, type = 'assistant') => {
    setMessages(prev => [...prev, { type, text }]);
  }, []);

  useEffect(() => {
    if (typeof window === 'undefined') return;
    setSpeechSupported(Boolean(window.SpeechRecognition || window.webkitSpeechRecognition));
  }, []);

  // Ref to access latest handleSendChatMessage (fixes hoisting error)
  const handleSendChatMessageRef = useRef(null);

  useEffect(() => {
    if (!speechSupported || typeof window === 'undefined') return;
    const RecognitionCtor = window.SpeechRecognition || window.webkitSpeechRecognition;
    if (!RecognitionCtor) return;
    const recognition = new RecognitionCtor();
    recognition.continuous = false;
    recognition.interimResults = false;
    recognition.lang = 'en-US';
    recognition.maxAlternatives = 1;
    recognitionRef.current = recognition;

    recognition.onstart = () => setIsListening(true);
    recognition.onend = () => setIsListening(false);
    recognition.onerror = (event) => {
      console.error('Voice capture error:', event);
      setIsListening(false);
      if (event?.error && event.error !== 'aborted') {
        addMessage('Voice capture error: ' + event.error, 'error');
      }
    };
    recognition.onresult = (event) => {
      try {
        const transcript = event?.results?.[0]?.[0]?.transcript;
        if (transcript && handleSendChatMessageRef.current) {
          handleSendChatMessageRef.current(transcript);
        }
      } catch (err) {
        console.error('Voice capture parsing failed:', err);
      }
    };

    return () => {
      try {
        recognition.stop();
      } catch { }
      if (recognitionRef.current === recognition) {
        recognitionRef.current = null;
      }
    };
  }, [speechSupported, addMessage]);

  useEffect(() => {
    if (showDiagnosticsModal && !detectionMode) {
      setDetectionMode(true);
      addMessage('Input detection enabled for diagnostics.', 'info');
    }
  }, [showDiagnosticsModal, detectionMode, addMessage]);

  const refreshCascadeInfo = useCallback(async () => {
    try {
      const [status, baseline] = await Promise.all([
        fetchCascadeStatus(),
        fetchBaseline(),
      ]);
      setCascadeStatus(status);
      setCascadeBaseline(baseline);
      setCascadeError('');
    } catch (error) {
      console.error('Cascade status error:', error);
      setCascadeError(error.message);
    }
  }, []);

  // Cascade polling useEffect (dedicated to cascade status updates)
  useEffect(() => {
    refreshCascadeInfo();
    const interval = window.setInterval(
      refreshCascadeInfo,
      getCascadePollInterval()
    );

    return () => window.clearInterval(interval);
  }, [refreshCascadeInfo]);

  const detectConsoleControllers = useCallback(async () => {
    setDeviceScanLoading(true);
    try {
      setConsoleError('');
      setConsoleHints([]);
      setConsoleControllers([]);

      const res = await fetch('/api/local/controller/devices', {
        headers: {
          'x-scope': 'state',
          'x-panel': 'controller-chuck',
          'x-device-id': 'controller_chuck'
        }
      });
      const data = await res.json().catch(() => ({}));

      if (res.ok) {
        const controllers = Array.isArray(data.controllers) ? data.controllers : [];
        setConsoleControllers(controllers);
        setConsoleHints(Array.isArray(data.hints) ? data.hints.filter(Boolean) : []);

        const status = data?.status || data?.overall_status;
        if (status === 'empty') {
          setConsoleError('No handheld controllers detected. Connect one and try Scan Devices.');
        } else if (status === 'partial') {
          const errMessage = Array.isArray(data.errors) && data.errors.length > 0
            ? data.errors[0]?.message || 'Controller detection partially succeeded.'
            : 'Controller detection partially succeeded.';
          setConsoleError(errMessage);
        } else {
          setConsoleError('');
        }
      } else {
        let msg = 'Controller detection failed.';
        const detail = data?.detail;
        if (typeof detail === 'string') msg = detail;
        else if (detail && typeof detail === 'object' && detail.message) msg = detail.message;

        try {
          const h = await fetch('/api/local/controller/health', {
            headers: {
              'x-scope': 'state',
              'x-panel': 'controller-chuck',
              'x-device-id': 'controller_chuck'
            }
          });
          if (h.ok) {
            const hv = await h.json();
            if (hv.usb_backend === 'backend_unavailable') {
              msg = 'USB backend unavailable. Run backend on Windows (start-gui.bat), or on WSL install libusb and attach device with usbipd.';
            } else if (hv.permissions === 'permission_denied' || hv.usb_backend === 'permission_denied') {
              msg = 'USB permission denied. Run as Administrator (Windows) or use sudo/add user to plugdev (Linux).';
            }
          }
        } catch (_e) {
          // ignore health lookup failures
        }

        setConsoleHints(Array.isArray(data?.hints) ? data.hints.filter(Boolean) : []);
        setConsoleError(msg);
      }
    } catch (e) {
      setConsoleError(e?.message || 'Controller detection failed.');
      setConsoleHints([]);
    } finally {
      setDeviceScanLoading(false);
      setLastDeviceScan(Date.now());
    }
  }, []);

  useEffect(() => {
    detectConsoleControllers();
  }, [detectConsoleControllers]);

  const handleVoiceToggle = useCallback(() => {
    setVoicePlaybackEnabled((prev) => !prev);
  }, []);

  useEffect(() => {
    const sectionId = `player-section-p${currentPlayer}`;
    const section = document.getElementById(sectionId);
    if (section) {
      section.scrollIntoView({ behavior: 'smooth', block: 'nearest' });
    }
  }, [currentPlayer]);

  const triggerCascade = useCallback(async (source = 'manual', summary = null, options = {}) => {
    const {
      skipEmulators = [],
      skipLed = false,
      baseline: baselineOverride,
    } = options || {};
    setCascadeLoading(true);
    try {
      await requestCascade({
        metadata: {
          source,
          panel: 'controller-chuck',
          changed_controls: Array.isArray(summary?.changed_controls) ? summary.changed_controls : undefined,
        },
        skipEmulators,
        skipLed,
        baseline: baselineOverride,
      });
      addMessage('Cascade job queued. Check the status card for updates.', 'assistant');
      await refreshCascadeInfo();
      setShowCascadePrompt(false);
      setPendingCascadeSummary(null);
    } catch (error) {
      console.error('Cascade request error:', error);
      addMessage('Cascade request failed: ' + error.message, 'error');
      setCascadeError(error.message);
    } finally {
      setCascadeLoading(false);
      setRememberCascadeChoice(false);
    }
  }, [addMessage, refreshCascadeInfo]);

  const handleCascadePromptCascade = useCallback(() => {
    if (rememberCascadeChoice) {
      setCascadePreferenceState('auto');
    }
    triggerCascade('prompt', pendingCascadeSummary);
  }, [rememberCascadeChoice, triggerCascade, pendingCascadeSummary]);

  const handleCascadePromptSkip = useCallback(() => {
    if (rememberCascadeChoice) {
      setCascadePreferenceState('manual');
    }
    setShowCascadePrompt(false);
    setPendingCascadeSummary(null);
    setRememberCascadeChoice(false);
    addMessage('Cascade skipped. Run it later from the status card if needed.', 'warning');
  }, [rememberCascadeChoice, addMessage]);

  const handleRetryFailedCascade = useCallback((failedEmulators = []) => {
    if (!Array.isArray(failedEmulators) || failedEmulators.length === 0) {
      addMessage('No failed emulator jobs to retry.', 'warning');
      return;
    }

    const availableEmulators = Object.keys(cascadeBaseline?.emulators || {});
    if (availableEmulators.length === 0) {
      addMessage('No emulator targets discovered for cascade.', 'warning');
      return;
    }

    const failedKeys = (failedEmulators.map((item) => item.key || item.label) || []).filter(Boolean);
    const skipEmulators = availableEmulators.filter((name) => !failedKeys.includes(name));
    triggerCascade('retry-failed', pendingCascadeSummary, { skipEmulators });
  }, [addMessage, cascadeBaseline, pendingCascadeSummary, triggerCascade]);

  const handleChatIntent = useCallback((text) => {
    const normalized = text.toLowerCase();
    let handled = false;

    if (normalized.includes('scan devices') || normalized.includes('scan for devices')) {
      detectConsoleControllers();
      addMessage("Running Scan Devices so we know what's plugged in.", 'assistant');
      handled = true;
    }

    if (normalized.includes('open diagnostics') || normalized.includes('run diagnostics')) {
      setShowDiagnosticsModal(true);
      addMessage('Diagnostics panel opened. Flip some switches and watch the highlights.', 'assistant');
      handled = true;
    }

    const playerMatch = normalized.match(/player\s*(\d)/);
    if (playerMatch) {
      const requested = parseInt(playerMatch[1], 10);
      if (!Number.isNaN(requested) && requested >= 1 && requested <= 4) {
        setCurrentPlayer(requested);
        addMessage(`Jumping to Player ${requested}. Scroll down to see their wiring.`, 'assistant');
        handled = true;
      }
    }

    if (
      normalized.includes('factory reset') ||
      normalized.includes('restore defaults') ||
      normalized.includes('restore default')
    ) {
      handleResetRef.current?.();
      handled = true;
    }

    return handled;
  }, [detectConsoleControllers, addMessage, setShowDiagnosticsModal, setCurrentPlayer]);

  // Handle sending chat messages to Chuck AI
  const handleSendChatMessage = useCallback(async (text) => {
    const trimmed = text?.trim();
    if (!trimmed) return;

    addMessage(trimmed, 'user');
    handleChatIntent(trimmed);
    setAiLoading(true);

    try {
      const panelState = {
        persona: 'chuck',
        board,
        mapping,
        consoleControllers,
        consoleHints,
        consoleError,
        detectedControllers: consoleControllers
      };

      const response = await controllerAIChat(trimmed, panelState, {
        panel: 'controller-chuck',
        deviceId: 'controller_chuck',
        sessionId: 'controller_chuck'
      });

      const assistantText = response?.reply ?? "I'm hearin' ya!";
      addMessage(String(assistantText), 'assistant');
      if (voicePlaybackEnabled && assistantText) {
        speak(String(assistantText), { voice_id: CHUCK_VOICE_ID });
      }

      if (response?.context?.hints && Array.isArray(response.context.hints)) {
        const newHints = response.context.hints.filter(Boolean);
        if (newHints.length > 0) {
          setConsoleHints(prev => {
            const merged = Array.isArray(prev) ? [...prev] : [];
            newHints.forEach((hint) => {
              if (!merged.includes(hint)) merged.push(hint);
            });
            return merged;
          });
        }
      }
    } catch (error) {
      console.error('Controller AI error:', error);
      addMessage('Sorry, got an error processin\' that. Try again?', 'error');
    } finally {
      setAiLoading(false);
    }
  }, [board, mapping, consoleControllers, consoleHints, consoleError, addMessage, handleChatIntent, voicePlaybackEnabled]);

  // Update ref to latest function (fixes hoisting error)
  useEffect(() => {
    handleSendChatMessageRef.current = handleSendChatMessage;
  }, [handleSendChatMessage]);

  useEffect(() => {
    if (!controllerEvent) return;
    const eventTimestamp = controllerEvent.timestamp ?? controllerEvent.board?.detection_time;
    if (eventTimestamp && lastControllerEventRef.current === eventTimestamp) return;
    if (eventTimestamp) lastControllerEventRef.current = eventTimestamp;

    const boardInfo = controllerEvent.board || {};
    const boardLabel = boardInfo.name || [boardInfo.vid, boardInfo.pid].filter(Boolean).join(':') || 'controller';

    let assistantMessage = null;

    switch (controllerEvent.event_type) {
      case 'connected':
        assistantMessage = `Board ${boardLabel} connected. Let's get mapping.`;
        setConsoleError('');
        detectConsoleControllers();
        break;
      case 'disconnected':
        assistantMessage = `Board ${boardLabel} disconnected. Check wiring and USB, then scan again.`;
        setConsoleError('Encoder board disconnected. Check wiring and try Scan Devices.');
        break;
      case 'error':
        assistantMessage = `Board error: ${boardInfo.error || 'Unknown hardware issue.'}`;
        setConsoleError(boardInfo.error || 'Encoder board error detected.');
        break;
      case 'status':
        if (boardInfo.detected === false) {
          assistantMessage = `Board ${boardLabel} not detected yet. Power cycle and hit Scan Devices.`;
        }
        break;
      default:
        break;
    }

    if (assistantMessage) {
      addMessage(assistantMessage, 'assistant');
      setConsoleHints(prev => {
        const merged = Array.isArray(prev) ? [...prev] : [];
        if (!merged.includes(assistantMessage)) merged.push(assistantMessage);
        return merged;
      });
    }
  }, [controllerEvent, addMessage, detectConsoleControllers, setConsoleError, setConsoleHints]);

  // Convert mapping object to array for conflict checking with memoization
  const existingPins = useMemo(() => {
    if (!mapping) return [];
    const merged = { ...mapping, ...pendingChanges };
    return Object.entries(merged).map(([key, data]) => ({
      key,
      pin: data.pin,
      label: data.label
    }));
  }, [mapping, pendingChanges]);

  const loadMapping = useCallback(
    async ({ silent = false } = {}) => {
      try {
        const response = await fetch(`${API_BASE}/mapping`);
        if (!response.ok) {
          if (response.status === 404) {
            addMessage(
              "Mapping file not found. Backend might not be configured yet. Try Factory Reset first.",
              'error'
            );
          } else if (response.status >= 500) {
            addMessage("Backend server error. Check if FastAPI is running on port 8000.", 'error');
          } else {
            throw new Error('Failed to load mapping');
          }
          return null;
        }

        const data = await response.json();
        setMapping(data.mapping.mappings);
        setBoard(data.mapping.board);
        if (!silent) {
          setPendingChanges({});
          addMessage(CHUCK_RESPONSES.loadSuccess);
        }
        return data;
      } catch (error) {
        console.error('Load mapping error:', error);
        if (error.message.includes('fetch')) {
          addMessage("Can't reach the backend. Make sure it's running: npm run dev:backend", 'error');
        } else {
          addMessage(CHUCK_RESPONSES.loadError + ' ' + error.message, 'error');
        }
        return null;
      }
    },
    [addMessage, setPendingChanges]
  );

  useEffect(() => {
    let cancelled = false;
    (async () => {
      try {
        await loadMapping();
      } finally {
        if (!cancelled) {
          setLoading(false);
        }
      }
    })();
    return () => {
      cancelled = true;
    };
  }, [loadMapping]);

  // Optimized handlers with proper memoization
  const handlePreview = useCallback(async (changes) => {
    if (!changes || Object.keys(changes).length === 0) {
      setPreview(null);
      setShowDiff(false);
      return;
    }

    try {
      const response = await fetch(`${API_BASE}/mapping/preview`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ mappings: changes })
      });

      if (!response.ok) throw new Error('Preview failed');

      const data = await response.json();
      setPreview(data);
      setShowDiff(true);

      if (!data.validation.valid) {
        addMessage(CHUCK_RESPONSES.pinConflict + ' ' + data.validation.errors.join(', '), 'warning');
      } else {
        addMessage(CHUCK_RESPONSES.previewReady);
      }
    } catch (error) {
      console.error('Preview error:', error);
      addMessage('Preview failed: ' + error.message, 'error');
    }
  }, [addMessage]);

  const handleApply = useCallback(async (changes) => {
    if (!changes || Object.keys(changes).length === 0) {
      addMessage('No pending changes to apply.', 'warning');
      return;
    }

    if (previewRef.current && !previewRef.current.validation.valid) {
      addMessage(CHUCK_RESPONSES.applyError, 'error');
      return;
    }

    try {
      const response = await fetch(`${API_BASE}/mapping/apply`, {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
          'x-scope': 'config'
        },
        body: JSON.stringify({ mappings: changes })
      });

      if (!response.ok) throw new Error('Apply failed');

      const data = await response.json();
      const cascadeSummary = previewRef.current?.cascade_preview || null;
      setMapping(data.mapping.mappings);
      setPendingChanges({});
      setPreview(null);
      setShowDiff(false);

      addMessage(CHUCK_RESPONSES.applySuccess + ` Backup: ${data.backup_path}`);
      await refreshCascadeInfo();

      if (cascadeSummary) {
        setPendingCascadeSummary(cascadeSummary);
      } else {
        const changeKeys = Object.keys(changes || {});
        if (changeKeys.length > 0) {
          setPendingCascadeSummary({
            needs_cascade: true,
            changed_controls: changeKeys,
          });
        } else {
          setPendingCascadeSummary(null);
        }
      }

      if (cascadePreference === 'auto') {
        triggerCascade('auto', cascadeSummary || pendingCascadeSummary);
      } else if (cascadePreference === 'ask') {
        setRememberCascadeChoice(false);
        setShowCascadePrompt(true);
      } else {
        addMessage('Cascade not triggered (manual preference).', 'warning');
      }
    } catch (error) {
      console.error('Apply error:', error);
      addMessage('Apply failed: ' + error.message, 'error');
    }
  }, [addMessage, cascadePreference, pendingCascadeSummary, refreshCascadeInfo, triggerCascade]);

  const handleReset = useCallback(async () => {
    if (!window.confirm(CHUCK_RESPONSES.resetConfirm)) return;

    try {
      const response = await fetch(`${API_BASE}/mapping/reset`, {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
          'x-scope': 'config'
        }
      });

      if (!response.ok) throw new Error('Reset failed');

      const data = await response.json();
      setMapping(data.mapping.mappings);
      setPendingChanges({});
      setPreview(null);
      setShowDiff(false);

      addMessage(CHUCK_RESPONSES.resetSuccess);
    } catch (error) {
      console.error('Reset error:', error);
      addMessage('Reset failed: ' + error.message, 'error');
    }
  }, [addMessage]);

  // Store in refs for keyboard shortcuts
  handleResetRef.current = handleReset;

  // Pending change helpers
  const handleTestPreview = useCallback(async () => {
    if (!hasPendingChanges) {
      addMessage('No pending changes to preview.', 'warning');
      setPreview(null);
      setShowDiff(false);
      return;
    }
    await handlePreview(pendingChanges);
  }, [hasPendingChanges, handlePreview, pendingChanges, addMessage]);

  const handleTestApply = useCallback(async () => {
    if (!hasPendingChanges) {
      addMessage('No pending changes to apply.', 'warning');
      return;
    }
    await handleApply(pendingChanges);
  }, [hasPendingChanges, handleApply, pendingChanges, addMessage]);

  // Store test functions in refs
  handleTestPreviewRef.current = handleTestPreview;
  handleTestApplyRef.current = handleTestApply;

  // Pin edit handlers
  const handlePinClick = useCallback((control) => {
    setEditingControl(control);
    setShowPinEditModal(true);
    addMessage(`Editing ${control.label}...`, 'info');
  }, [addMessage]);

  const handlePinSave = useCallback(async (controlKey, newPin) => {
    try {
      const baseControl = mapping?.[controlKey] || {};
      const normalizedPin = Number(newPin);
      const updatedControl = {
        ...baseControl,
        pin: normalizedPin
      };
      const matchesOriginal = Number(baseControl?.pin) === normalizedPin;

      let updatedChanges = {};
      setPendingChanges((prev) => {
        const next = { ...prev };
        if (matchesOriginal) {
          delete next[controlKey];
        } else {
          next[controlKey] = updatedControl;
        }
        updatedChanges = next;
        return next;
      });

      if (Object.keys(updatedChanges).length === 0) {
        setPreview(null);
        setShowDiff(false);
      } else {
        await handlePreview(updatedChanges);
      }

      setShowPinEditModal(false);
      setEditingControl(null);

      if (matchesOriginal) {
        addMessage(`Pin ${normalizedPin} already matches the current mapping.`, 'info');
      } else {
        addMessage(`Pin updated to ${normalizedPin}. Review the preview, then click Apply.`, 'assistant');
      }
    } catch (error) {
      addMessage('Failed to save pin: ' + error.message, 'error');
    }
  }, [mapping, handlePreview, addMessage]);

  const handlePinEditCancel = useCallback(() => {
    setShowPinEditModal(false);
    setEditingControl(null);
  }, []);

  const handlePinApplyImmediately = useCallback(async (controlKey, newPin) => {
    try {
      const baseControl = mapping?.[controlKey] || {};
      const normalizedPin = Number(newPin);
      const updatedControl = {
        ...baseControl,
        pin: normalizedPin
      };

      // Build changes object with single control
      const changes = { [controlKey]: updatedControl };

      // Close modal first
      setShowPinEditModal(false);
      setEditingControl(null);

      addMessage(`Saving ${controlKey} to pin ${normalizedPin}...`, 'info');

      // Apply directly to backend
      const response = await fetch(`${API_BASE}/mapping/apply`, {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
          'x-scope': 'config'
        },
        body: JSON.stringify({ mappings: changes })
      });

      if (!response.ok) throw new Error('Apply failed');

      const data = await response.json();

      // Update local state with server response
      setMapping(data.mapping.mappings);
      setPendingChanges({});
      setPreview(null);
      setShowDiff(false);

      addMessage(`✓ Pin ${normalizedPin} saved to ${controlKey}! File updated.`, 'assistant');

      // Refresh cascade info
      await refreshCascadeInfo();
    } catch (error) {
      addMessage('Failed to save immediately: ' + error.message, 'error');
    }
  }, [mapping, addMessage, refreshCascadeInfo]);

  // MAME Config Handlers
  const handlePreviewMAMEConfig = useCallback(async () => {
    try {
      addMessage("Generating MAME config preview...", 'info');
      const response = await fetch(`${API_BASE}/mame-config/preview`);

      if (!response.ok) throw new Error('Failed to preview MAME config');

      const data = await response.json();
      setMamePreview(data);
      setShowMameModal(true);

      const summary = data.summary;
      addMessage(
        `MAME config ready: ${summary.port_count} ports, ${summary.player_count} players configured.`,
        'assistant'
      );
    } catch (error) {
      console.error('MAME preview error:', error);
      addMessage('MAME config preview failed: ' + error.message, 'error');
    }
  }, [addMessage]);

  const handleApplyMAMEConfig = useCallback(async () => {
    if (!mamePreview || !mamePreview.validation?.valid) {
      addMessage("Can't apply MAME config - validation failed!", 'error');
      return;
    }

    try {
      const response = await fetch(`${API_BASE}/mame-config/apply`, {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
          'x-scope': 'config'
        }
      });

      if (!response.ok) throw new Error('Failed to apply MAME config');

      const data = await response.json();
      setShowMameModal(false);
      setMamePreview(null);

      addMessage(
        `MAME config written! ${data.summary.port_count} ports for ${data.summary.player_count} players. Backup: ${data.backup_path || 'none'}`,
        'assistant'
      );
    } catch (error) {
      console.error('MAME apply error:', error);
      addMessage('MAME config apply failed: ' + error.message, 'error');
    }
  }, [mamePreview, addMessage]);

  const handleMameModalCancel = useCallback(() => {
    setShowMameModal(false);
  }, []);

  const handleBoardChange = useCallback((newBoard) => {
    setBoard(newBoard);
    addMessage(`Board changed to: ${newBoard.name}`, 'info');
  }, [addMessage]);

  const handleDetectionToggle = useCallback(() => {
    setDetectionMode((prev) => {
      const next = !prev;
      addMessage(
        next
          ? 'Input detection mode enabled. Press any encoder input to capture it.'
          : 'Input detection mode stopped.',
        'info'
      );
      return next;
    });
  }, [addMessage]);

  const toggleKeyboardHelp = useCallback(() => {
    setShowKeyboardHelp(prev => !prev);
  }, []);

  const handleKeyboardHelpClick = useCallback((e) => {
    e.stopPropagation();
  }, []);

  // Auto-detect handlers

  const handleAutoDetect = useCallback(async () => {
    setDetectLoading(true);
    try {
      const response = await fetch('/api/controllers/autoconfig/detect', {
        headers: {
          'x-scope': 'state',
          'x-panel': 'controller-chuck',
          'x-device-id': 'controller_chuck'
        }
      });
      if (!response.ok) {
        throw new Error(`Detection failed: ${response.status}`);
      }
      const data = await response.json();
      setDetectedDevices(data.devices || []);
      setShowDeviceModal(true);
      const extra = data.unconfigured_count ? ` (${data.unconfigured_count} need setup)` : '';
      addMessage(`Found ${data.count || 0} devices${extra}`, 'assistant');
    } catch (error) {
      console.error('Auto-detect error:', error);
      addMessage("Can't detect devices right now. Backend runnin'?", 'error');
    } finally {
      setDetectLoading(false);
    }
  }, [addMessage]);

  const handleMirrorDevice = useCallback(async (device) => {
    try {
      const response = await fetch('/api/controllers/autoconfig/mirror', {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
          'x-scope': 'config',
          'x-panel': 'controller-chuck',
          'x-device-id': 'controller_chuck'
        },
        body: JSON.stringify({
          profile_name: device.profile_name || device.name,
          device_class: device.device_class,
          vendor_id: device.vendor_id,
          product_id: device.product_id
        })
      });

      if (!response.ok) {
        throw new Error(`Mirror failed: ${response.status}`);
      }

      await response.json();
      addMessage(`Mirrored ${device.name} profile to emulators!`, 'assistant');
      // Refresh device list to update status
      handleAutoDetect();
    } catch (error) {
      console.error('Mirror device error:', error);
      addMessage(`Failed to mirror ${device.name}. Check the logs?`, 'error');
    }
  }, [addMessage, handleAutoDetect]);

  const handleDeviceModalCancel = useCallback(() => {
    setShowDeviceModal(false);
  }, []);

  // Keyboard shortcuts with optimized dependencies
  useEffect(() => {
    const handleKeyPress = (e) => {
      // Ignore if typing in input/textarea
      if (e.target.tagName === 'INPUT' || e.target.tagName === 'TEXTAREA') return;

      switch (e.key) {
        case '1':
        case '2':
        case '3':
        case '4':
          setCurrentPlayer(parseInt(e.key));
          addMessage(`Switched to Player ${e.key}`, 'info');
          break;
        case 'p':
        case 'P':
          handleTestPreviewRef.current?.();
          break;
        case 'a':
        case 'A':
          if (previewRef.current && previewRef.current.validation?.valid) {
            handleTestApplyRef.current?.();
          }
          break;
        case 'r':
        case 'R':
          handleResetRef.current?.();
          break;
        case '?':
          setShowKeyboardHelp(prev => !prev);
          break;
        default:
          break;
      }
    };

    window.addEventListener('keydown', handleKeyPress);
    return () => window.removeEventListener('keydown', handleKeyPress);
  }, [addMessage]); // Only depend on addMessage which is stable

  // Chat functions - wrapper to maintain TTS and logging while routing to unified messages
  const addChatMessage = useCallback((content, type = 'assistant', options = {}) => {
    // Route to the main messages state used by ChuckChat
    addMessage(content, type);

    // Optional: speak the message if requested
    if (options.speak && type === 'assistant') {
      speak(content, { voice_id: CHUCK_VOICE_ID }).catch(err => {
        console.warn('[Chuck] TTS failed:', err);
      });
    }

    // Log to Supabase
    logChatHistory({
      panel_id: 'controller-chuck',
      role: type === 'user' ? 'user' : 'assistant',
      content: content,
      session_id: sessionIdRef.current,
      metadata: { timestamp: new Date().toISOString() }
    });
  }, [addMessage]);

  // Dedicated handoff useEffect (handles Dewey → Chuck context handoff)
  useEffect(() => {
    const urlParams = new URLSearchParams(window.location.search);
    const handoffContext = urlParams.get('context');
    const hasHandoff = Boolean((handoffContext || '').trim());
    const noHandoff = urlParams.has('nohandoff');
    const shouldHandoff = hasHandoff && !noHandoff;

    console.log('[Controller Chuck] Checking for handoff context:', handoffContext);

    // Only process if we have context AND it's different from last processed context
    if (shouldHandoff && handoffContext !== handoffProcessedRef.current) {
      const welcomeMsg = `Hi! Dewey told me you said: "${handoffContext}"\n\nI'm Controller Chuck, your arcade controls specialist. I can help with button mapping, encoder setup, and cabinet wiring. What would you like me to do?`;

      console.log('[Controller Chuck] Handoff detected, adding welcome message');
      handoffProcessedRef.current = handoffContext; // Store the processed context

      // Use setTimeout to ensure component is fully mounted
      setTimeout(() => {
        addChatMessage(welcomeMsg, 'assistant', { speak: true }); // Enable voice on handoff
        console.log('[Controller Chuck] Handoff complete - message added to chat');
      }, 100);
    } else if (handoffContext) {
      console.log('[Controller Chuck] Handoff context already processed:', handoffContext);
    }

    // Check for JSON handoff from Dewey (only when arriving via Dewey URL context)
    if (shouldHandoff) (async () => {
      try {
        console.log('[ControllerChuck] Fetching handoff from /api/local/dewey/handoff/controller_chuck');
        const response = await fetch('/api/local/dewey/handoff/controller_chuck', {
          method: 'GET',
          headers: {
            'Content-Type': 'application/json',
            'x-device-id': window?.AA_DEVICE_ID ?? 'cabinet-001',
            'x-panel': 'controller-chuck',
            'x-scope': 'state'
          }
        });
        console.log('[ControllerChuck] Handoff fetch response:', response.status, response.ok);
        const text = await response.text();
        let data = null;
        if (text) {
          try {
            data = JSON.parse(text);
          } catch {
            data = text;
          }
        }
        console.log('[ControllerChuck] Handoff data received:', data);

        if (data && data.handoff) {
          const rawSummary = typeof data.handoff.summary === 'string'
            ? data.handoff.summary
            : JSON.stringify(data.handoff);
          console.log('[ControllerChuck] Extracted summary:', rawSummary);
          console.log('[ControllerChuck] Previously processed:', handoffProcessedRef.current);

          const summaryText = (rawSummary || '').trim();
          if (summaryText && summaryText !== handoffProcessedRef.current) {
            handoffProcessedRef.current = summaryText;
            const welcomeMsg = `Dewey mentioned you're having a controller issue: "${summaryText}". Let's walk through fixing it.`;
            console.log('[ControllerChuck] Injecting handoff message and opening chat');

            setTimeout(() => {
              addChatMessage(welcomeMsg, 'assistant', { speak: true });
              console.log('[ControllerChuck] Handoff message added');
            }, 100);
          } else {
            console.log('[ControllerChuck] Handoff already processed or empty, skipping');
          }
        } else {
          console.log('[ControllerChuck] No handoff data found');
        }
      } catch (err) {
        console.warn('[ControllerChuck] Handoff fetch failed:', err);
      }
    })();
  }, [addChatMessage]); // Runs once on mount (addChatMessage is stable via useCallback)


  // Define stopVoiceRecording first so it can be used in startVoiceRecording
  const stopVoiceRecording = useCallback(() => {
    console.log('[Chuck] Stopping voice recording');
    if (recognitionRef.current) {
      recognitionRef.current.stop();
      recognitionRef.current = null;
    }
    setIsRecording(false);
    setIsListening(false);
  }, []);

  const startVoiceRecording = useCallback(async () => {
    console.log('[Chuck] startVoiceRecording called');
    try {
      // Use Web Speech API for transcription
      const SpeechRecognition = window.SpeechRecognition || window.webkitSpeechRecognition;
      console.log('[Chuck] SpeechRecognition available:', !!SpeechRecognition);

      if (!SpeechRecognition) {
        addChatMessage('❌ Speech recognition not supported in this browser. Use Chrome/Edge.', 'system');
        return;
      }

      const recognition = new SpeechRecognition();
      recognition.continuous = false;  // Stop after one utterance
      recognition.interimResults = false;
      recognition.lang = 'en-US';
      recognition.maxAlternatives = 1;

      recognition.onstart = () => {
        console.log('[Chuck] Speech recognition started');
        setIsRecording(true);
        setIsListening(true);
        addChatMessage('🎤 Listening... (speak now)', 'system');
      };

      recognition.onresult = async (event) => {
        const transcript = event.results[0][0].transcript;
        console.log('[Chuck] Transcribed:', transcript);

        // Add user message to chat
        addChatMessage(transcript, 'user');
        setAiLoading(true);

        try {
          // Build panel state for AI context
          const panelState = {
            mapping: mapping,
            current_player: currentPlayer,
            has_pending_changes: hasPendingChanges,
            board_type: board?.board_type || 'unknown'
          };

          console.log('[Chuck] Sending voice transcript to AI:', transcript);

          // Call AI with the transcript
          const result = await controllerAIChat(transcript, panelState, {
            panel: 'controller-chuck'
          });

          console.log('[Chuck] AI response:', result);

          // Extract response
          const responseText = result?.message?.content || result?.reply || result?.response ||
            "Yo! I'm here to help with your arcade controller setup. Ask me anything!";

          // Add AI response to chat
          addChatMessage(responseText, 'assistant');

          // Speak the response with Chuck's voice
          if (voicePlaybackEnabled) {
            console.log('[Chuck] Speaking response with voice ID:', CHUCK_VOICE_ID);
            try {
              await speak(responseText, { voice_id: CHUCK_VOICE_ID });
              console.log('[Chuck] TTS completed successfully');
            } catch (err) {
              console.error('[Chuck] TTS failed:', err);
              addChatMessage('🔇 Voice playback unavailable.', 'system');
            }
          }

        } catch (error) {
          console.error('[Chuck] Voice chat error:', error);
          addChatMessage("Sorry pal, had trouble processing that. Try again?", 'assistant');
        } finally {
          setAiLoading(false);
        }
      };

      recognition.onerror = (event) => {
        console.error('[Chuck] Speech recognition error:', event.error);
        addChatMessage(`❌ Speech recognition error: ${event.error}`, 'system');
        setIsRecording(false);
        setIsListening(false);
      };

      recognition.onend = () => {
        console.log('[Chuck] Speech recognition ended');
        setIsRecording(false);
        setIsListening(false);
        recognitionRef.current = null;
      };

      recognitionRef.current = recognition;
      recognition.start();

    } catch (err) {
      console.error('Speech recognition error:', err);
      addChatMessage('Speech recognition failed: ' + err.message, 'system');
      setIsRecording(false);
    }
  }, [addChatMessage, mapping, currentPlayer, hasPendingChanges, board, voicePlaybackEnabled, setAiLoading]);

  // handleMicClick - used by ChuckChat component
  const handleMicClick = useCallback(() => {
    console.log('[Chuck] handleMicClick called, isRecording:', isRecording);
    if (isRecording) {
      stopVoiceRecording();
    } else {
      startVoiceRecording();
    }
  }, [isRecording, stopVoiceRecording, startVoiceRecording]);

  if (loading) {
    return (
      <div className="chuck-panel-loading">
        <div className="chuck-spinner"></div>
        <div>Loading Chuck's Workshop...</div>
      </div>
    );
  }

  return (
    <div className="chuck-panel-container">
      <div className="chuck-header">
        <div className="chuck-title-section">
          <h1 className="chuck-title">Controller Chuck</h1>
          <p className="chuck-subtitle">
            Arcade Encoder Board Mapping
            <span className="chuck-profile-indicator" title={`Current profile: ${currentUser}`}>
              {' • '}{currentUser}
            </span>
          </p>
        </div>

        <button
          className="chuck-chat-toggle-btn"
          onClick={() => setChatOpen(true)}
          title="Chat with Chuck"
          aria-label="Open chat with Chuck"
        >
          💬 Chat with Chuck
        </button>

        <BoardStatus board={board} onBoardChange={handleBoardChange} />
      </div>

      <div className="chuck-main-content">
        <div className="chuck-left-column">
          <ChuckChat
            messages={messages}
            onMicClick={handleMicClick}
            isListening={isListening}
            speechSupported={speechSupported}
            onToggleSpeech={handleVoiceToggle}
            voiceEnabled={voicePlaybackEnabled}
          />
          <ChatInput onSendMessage={handleSendChatMessage} isLoading={aiLoading} />

          {detectionToast && (
            <div className="detection-toast">
              <span className="detection-toast-dot" aria-hidden />
              {detectionToast}
            </div>
          )}

          <InputDetectionPanel
            enabled={detectionMode}
            active={detectionActive}
            latestInput={latestInput}
            error={detectionError}
            flash={detectionFlash}
            onOpenDiagnostics={() => setShowDiagnosticsModal(true)}
          />

          <DeviceStatusCard
            devices={consoleControllers}
            error={consoleError}
            hints={consoleHints}
            loading={deviceScanLoading}
            lastScan={lastDeviceScan}
            onScan={detectConsoleControllers}
          />

          <CascadeStatusCard
            baseline={cascadeBaseline}
            cascade={cascadeStatus}
            onRetry={() => triggerCascade('manual', pendingCascadeSummary)}
            onRetryFailed={handleRetryFailedCascade}
            loading={cascadeLoading}
            error={cascadeError}
          />

          <div className="chuck-actions">
            <button
              className={`chuck-btn detection-toggle-btn ${detectionMode ? 'active' : ''}`}
              onClick={handleDetectionToggle}
              type="button"
            >
              <span className="detection-toggle-indicator" aria-hidden />
              {detectionMode ? 'Stop Detection' : 'Input Detection Mode'}
            </button>
            <button
              className="chuck-btn chuck-btn-preview"
              onClick={handleTestPreview}
              disabled={!hasPendingChanges}
            >
              Preview Changes
            </button>
            <button
              className="chuck-btn chuck-btn-apply"
              onClick={handleTestApply}
              disabled={
                !hasPendingChanges ||
                !preview ||
                (preview && !preview.validation?.valid)
              }
            >
              Apply Changes
            </button>
            <button
              className="chuck-btn chuck-btn-reset"
              onClick={handleReset}
            >
              Factory Reset
            </button>
          </div>

          <div className="chuck-actions chuck-actions-mame">
            <button
              className="chuck-btn chuck-btn-mame"
              onClick={handlePreviewMAMEConfig}
              title="Generate MAME default.cfg from current mapping"
            >
              Generate MAME Config
            </button>
            {AUTOCONFIG_ENABLED && (
              <button
                className="chuck-btn chuck-btn-detect"
                onClick={handleAutoDetect}
                disabled={detectLoading}
                title="Auto-detect connected controllers"
              >
                {detectLoading ? 'Detecting...' : '🎮 Auto-Detect Devices'}
              </button>
            )}
            {!AUTOCONFIG_ENABLED && autoconfigStatus.checked && (
              <div className="chuck-autoconfig-disabled-hint" title={autoconfigStatus.reason || 'Set CONTROLLER_AUTOCONFIG_ENABLED=true in backend'}>
                <span>ℹ️ Auto-config disabled</span>
              </div>
            )}
          </div>

          <DiffViewer diff={preview?.diff} show={showDiff} />
          <CascadePreviewSummary cascadePreview={preview?.cascade_preview} />
        </div>

        <div className="chuck-right-column">
          <PinMappingGrid
            mappings={mapping}
            onPinClick={handlePinClick}
            highlightedKey={highlightedControl}
            activePlayer={`p${currentPlayer}`}
          />
        </div>
      </div>

      <CascadePromptModal
        show={showCascadePrompt}
        summary={pendingCascadeSummary}
        rememberChoice={rememberCascadeChoice}
        onRememberChange={setRememberCascadeChoice}
        onCascade={handleCascadePromptCascade}
        onSkip={handleCascadePromptSkip}
      />
      {/* Pin Edit Modal */}
      <PinEditModal
        show={showPinEditModal}
        control={editingControl}
        existingPins={existingPins}
        onSave={handlePinSave}
        onCancel={handlePinEditCancel}
        onApplyImmediately={handlePinApplyImmediately}
      />

      {/* MAME Config Modal */}
      <MAMEConfigModal
        show={showMameModal}
        preview={mamePreview}
        onApply={handleApplyMAMEConfig}
        onCancel={handleMameModalCancel}
      />

      {/* Device Detection Modal */}
      {AUTOCONFIG_ENABLED && (
        <DeviceDetectionModal
          show={showDeviceModal}
          devices={detectedDevices}
          onMirror={handleMirrorDevice}
          onCancel={handleDeviceModalCancel}
          isLoading={detectLoading}
        />
      )}

      <DiagnosticsModal
        show={showDiagnosticsModal}
        mapping={mapping}
        latestInput={latestInput}
        highlightedKey={highlightedControl}
        detectionActive={detectionActive}
        activePlayer={`p${currentPlayer}`}
        onClose={() => setShowDiagnosticsModal(false)}
      />

      {/* Keyboard Shortcuts Help */}
      {showKeyboardHelp && (
        <div className="chuck-keyboard-help" onClick={toggleKeyboardHelp}>
          <div className="chuck-keyboard-help-content" onClick={handleKeyboardHelpClick}>
            <h3>Keyboard Shortcuts</h3>
            <div className="chuck-keyboard-shortcuts">
              <div className="chuck-shortcut"><kbd>1-4</kbd>Switch to Player 1-4</div>
              <div className="chuck-shortcut"><kbd>P</kbd>Preview Changes</div>
              <div className="chuck-shortcut"><kbd>A</kbd>Apply Changes (if valid)</div>
              <div className="chuck-shortcut"><kbd>R</kbd>Factory Reset</div>
              <div className="chuck-shortcut"><kbd>?</kbd>Toggle this help</div>
            </div>
            <button className="chuck-btn" onClick={toggleKeyboardHelp}>Got it!</button>
          </div>
        </div>
      )}

      {/* Keyboard Help Button */}
      <button
        className="chuck-keyboard-help-btn"
        onClick={toggleKeyboardHelp}
        title="Show keyboard shortcuts (or press ?)"
      >
        ⌨️
      </button>

      {/* Chat Sidebar */}
      {chatOpen && (
        <div className="panel-chat-sidebar" role="dialog" aria-label="Chat with Chuck">
          <div className="chat-header">
            <img src="/chuck-avatar.jpeg" alt="Chuck" className="chat-avatar" />
            <div className="chat-info">
              <h3>Controller Chuck</h3>
              <div className="chat-status">• Ready to assist</div>
            </div>
            <button
              className="chat-close-btn"
              onClick={handleChatClose}
              aria-label="Close chat"
            >
              ×
            </button>
          </div>

          <div className="welcome-message">
            Yo! I'm Chuck, your arcade controller expert. I can help you wire up encoder boards, map pins, generate MAME configs, and troubleshoot hardware issues. What can I help ya with today?
          </div>

          <div className="chat-messages" ref={chatMessagesRef}>
            {chatMessages.map((message) => (
              <div key={message.id} className={`message ${message.type}`}>
                <div className="message-avatar">
                  {message.type === 'user' ? '👤' : '🔧'}
                </div>
                <div className="message-content">
                  {message.content}
                </div>
              </div>
            ))}
            {isProcessing && (
              <div className="message assistant">
                <div className="message-avatar">🔧</div>
                <div className="message-content">
                  Thinkin'...
                </div>
              </div>
            )}
          </div>

          <div className="chat-input-area">
            <div className="input-container">
              <button
                className={`voice-btn ${isRecording ? 'recording' : ''}`}
                onClick={toggleMic}
                aria-label="Voice input"
                title={isRecording ? 'Stop recording' : 'Start voice recording'}
              >
                {isRecording ? '🔴' : '🎤'}
              </button>
              <input
                type="text"
                className="chat-input"
                placeholder="Ask Chuck anything..."
                value={inputMessage}
                onChange={(e) => setInputMessage(e.target.value)}
                onKeyPress={(e) => e.key === 'Enter' && handleSendMessage()}
                disabled={isProcessing}
              />
              <button
                className="execute-btn"
                onClick={() => handleSendMessage()}
                disabled={isProcessing || !inputMessage.trim()}
              >
                {isProcessing ? 'PROCESSING...' : 'SEND'}
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}

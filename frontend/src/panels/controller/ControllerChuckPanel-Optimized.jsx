/**
 * @deprecated EXPERIMENTAL - Not currently in use
 *
 * This is an optimized version of ControllerChuckPanel that was never activated.
 * Active version: ControllerChuckPanel.jsx (same directory)
 *
 * This file is kept for A/B testing reference and potential future optimization work.
 * Features:
 * - Memoized sub-components (PlayerSection, PinMappingGrid, BoardStatus)
 * - Reduced re-renders via useCallback/useMemo
 * - Keyboard shortcut support
 */
import React, { useState, useEffect, useCallback, useMemo, useRef, memo } from 'react';
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

// Memoized Player Section Component
const PlayerSection = memo(({ player, controls, onPinClick }) => {
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
    <div className="chuck-player-section">
      <div className="chuck-player-header">
        <span className="chuck-player-badge">P{playerNum}</span>
        <span className="chuck-button-count">{buttonCount} Buttons</span>
      </div>

      <div className="chuck-pin-grid">
        {controls.map(control => (
          <div
            key={control.key}
            className="chuck-pin-item"
            onClick={() => handlePinClick(control)}
            title={`${control.label} - Pin ${control.pin}`}
          >
            <div className="chuck-pin-number">Pin {control.pin}</div>
            <div className="chuck-pin-label">{control.label}</div>
            <div className={`chuck-pin-type chuck-pin-type-${control.type}`}>
              {control.type}
            </div>
          </div>
        ))}
      </div>
    </div>
  );
});
PlayerSection.displayName = 'PlayerSection';

// Memoized PinMappingGrid Component
const PinMappingGrid = memo(({ mappings, onPinClick }) => {
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
      <PlayerSection player="p1" controls={playerGroups.p1} onPinClick={onPinClick} />
      <PlayerSection player="p2" controls={playerGroups.p2} onPinClick={onPinClick} />
      <PlayerSection player="p3" controls={playerGroups.p3} onPinClick={onPinClick} />
      <PlayerSection player="p4" controls={playerGroups.p4} onPinClick={onPinClick} />
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
        modes: selectedBoard.modes
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

        <div className="chuck-board-vid-pid">
          VID: {board?.vid || 'N/A'} | PID: {board?.pid || 'N/A'}
        </div>

        {board?.manufacturer_string && (
          <div className="chuck-board-manufacturer">
            {board.manufacturer_string}
            {board.product_string && ` - ${board.product_string}`}
          </div>
        )}

        <div className="chuck-board-modes">
          {board?.modes?.interlock && <span className="chuck-mode-badge">Interlock</span>}
          {board?.modes?.turbo && <span className="chuck-mode-badge">Turbo</span>}
          {board?.modes?.six_button && <span className="chuck-mode-badge">6-Button</span>}
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
const PinEditModal = memo(({ show, control, onSave, onCancel, existingPins }) => {
  const [pinNumber, setPinNumber] = useState(control?.pin || '');
  const [error, setError] = useState('');

  useEffect(() => {
    if (control) {
      setPinNumber(control.pin);
      setError('');
    }
  }, [control]);

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

    onSave(control.key, pin);
  }, [pinNumber, existingPins, control, onSave]);

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
        </div>

        <div className="chuck-pin-edit-footer">
          <button className="chuck-btn chuck-btn-reset" onClick={onCancel}>
            Cancel
          </button>
          <button className="chuck-btn chuck-btn-apply" onClick={handleSave}>
            Save
          </button>
        </div>
      </div>
    </div>
  );
});
PinEditModal.displayName = 'PinEditModal';

// Memoized ChuckChat Component
const ChuckChat = memo(({ messages }) => {
  return (
    <div className="chuck-chat-box">
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
  );
});
ChuckChat.displayName = 'ChuckChat';

// Main Component with optimizations
export default function ControllerChuckPanel() {
  const [mapping, setMapping] = useState(null);
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
  const [messages, setMessages] = useState([
    { type: 'assistant', text: CHUCK_RESPONSES.welcome }
  ]);

  // Use refs for stable references in keyboard shortcuts
  const previewRef = useRef(preview);
  const handleResetRef = useRef(null);
  const handleTestPreviewRef = useRef(null);
  const handleTestApplyRef = useRef(null);

  // Update refs when values change
  useEffect(() => {
    previewRef.current = preview;
  }, [preview]);

  const addMessage = useCallback((text, type = 'assistant') => {
    setMessages(prev => [...prev, { type, text }]);
  }, []);

  // Convert mapping object to array for conflict checking with memoization
  const existingPins = useMemo(() => {
    if (!mapping) return [];
    return Object.entries(mapping).map(([key, data]) => ({
      key,
      pin: data.pin,
      label: data.label
    }));
  }, [mapping]);

  // Load current mapping on mount with error recovery
  useEffect(() => {
    const loadMapping = async () => {
      try {
        const response = await fetch(`${API_BASE}/mapping`);

        if (!response.ok) {
          if (response.status === 404) {
            addMessage("Mapping file not found. Backend might not be configured yet. Try Factory Reset first.", 'error');
          } else if (response.status >= 500) {
            addMessage("Backend server error. Check if FastAPI is running on port 8000.", 'error');
          } else {
            throw new Error('Failed to load mapping');
          }
          return;
        }

        const data = await response.json();
        setMapping(data.mapping.mappings);
        setBoard(data.mapping.board);
        addMessage(CHUCK_RESPONSES.loadSuccess);
      } catch (error) {
        console.error('Load mapping error:', error);
        if (error.message.includes('fetch')) {
          addMessage("Can't reach the backend. Make sure it's running: npm run dev:backend", 'error');
        } else {
          addMessage(CHUCK_RESPONSES.loadError + ' ' + error.message, 'error');
        }
      } finally {
        setLoading(false);
      }
    };

    loadMapping();
  }, [addMessage]);

  // Optimized handlers with proper memoization
  const handlePreview = useCallback(async (changes) => {
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
      setMapping(data.mapping.mappings);
      setPreview(null);
      setShowDiff(false);

      addMessage(CHUCK_RESPONSES.applySuccess + ` Backup: ${data.backup_path}`);
    } catch (error) {
      console.error('Apply error:', error);
      addMessage('Apply failed: ' + error.message, 'error');
    }
  }, [addMessage]);

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

  // Test functions for demo purposes
  const handleTestPreview = useCallback(() => {
    handlePreview({
      'p1.button1': { pin: 8, type: 'button', label: 'P1 Button 1 Modified' }
    });
  }, [handlePreview]);

  const handleTestApply = useCallback(() => {
    handleApply({
      'p1.button1': { pin: 8, type: 'button', label: 'P1 Button 1 Modified' }
    });
  }, [handleApply]);

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
      // Create the change with the new pin
      const updatedControl = {
        ...mapping[controlKey],
        pin: newPin
      };

      // Trigger preview first
      await handlePreview({ [controlKey]: updatedControl });

      setShowPinEditModal(false);
      setEditingControl(null);

      addMessage(`Pin updated to ${newPin}. Review the preview, then click Apply.`, 'assistant');
    } catch (error) {
      addMessage('Failed to save pin: ' + error.message, 'error');
    }
  }, [mapping, handlePreview, addMessage]);

  const handlePinEditCancel = useCallback(() => {
    setShowPinEditModal(false);
    setEditingControl(null);
  }, []);

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

  const toggleKeyboardHelp = useCallback(() => {
    setShowKeyboardHelp(prev => !prev);
  }, []);

  const handleKeyboardHelpClick = useCallback((e) => {
    e.stopPropagation();
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
          <p className="chuck-subtitle">Arcade Encoder Board Mapping</p>
        </div>

        <BoardStatus board={board} onBoardChange={handleBoardChange} />
      </div>

      <div className="chuck-main-content">
        <div className="chuck-left-column">
          <ChuckChat messages={messages} />

          <div className="chuck-actions">
            <button
              className="chuck-btn chuck-btn-preview"
              onClick={handleTestPreview}
            >
              Preview Changes
            </button>
            <button
              className="chuck-btn chuck-btn-apply"
              onClick={handleTestApply}
              disabled={!preview || (preview && !preview.validation?.valid)}
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
          </div>

          <DiffViewer diff={preview?.diff} show={showDiff} />
        </div>

        <div className="chuck-right-column">
          <PinMappingGrid
            mappings={mapping}
            onPinClick={handlePinClick}
          />
        </div>
      </div>

      {/* Pin Edit Modal */}
      <PinEditModal
        show={showPinEditModal}
        control={editingControl}
        existingPins={existingPins}
        onSave={handlePinSave}
        onCancel={handlePinEditCancel}
      />

      {/* MAME Config Modal */}
      <MAMEConfigModal
        show={showMameModal}
        preview={mamePreview}
        onApply={handleApplyMAMEConfig}
        onCancel={handleMameModalCancel}
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
    </div>
  );
}
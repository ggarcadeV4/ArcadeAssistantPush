import React, { useState, useEffect, useCallback, useMemo, useRef } from 'react';
import { useLocation, useNavigate } from 'react-router-dom';
import { controllerAIChat } from '../../services/controllerAI';
import { useControllerEvents } from '../../hooks/useControllerEvents';
import { useLearnWizard } from '../../hooks/useLearnWizard';
import { useCaptureMode } from '../../hooks/useCaptureMode';
import { speak, stopSpeaking } from '../../services/ttsClient';
import { ClickableCabinetDisplay, getControlDisplayName } from '../../components/ClickableCabinetDisplay';
import {
  fetchDeviceSnapshot,
  classifyDevice,
  startWiringWizard,
  fetchWizardNextStep,
  captureWizardInput,
  previewWizardMapping,
  applyWizardMapping,
  fetchDiagnosticsEvent,
  // Learn Wizard functions
  startLearnWizard,
  getLearnWizardStatus,
  confirmLearnWizardCapture,
  skipLearnWizardControl,
  saveLearnWizard,
  stopLearnWizard,
  // Demo reset
  resetMappingToDefault
} from '../../services/deviceClient';
import '../../components/ControllerWizardPanel.css';

// Chuck's Brooklyn voice ID
const CHUCK_VOICE_ID = 'f5HLTX707KIM4SzJYzSz';

const PLAYER_CONTROL_ORDER = {
  1: [
    'coin',
    'start',
    'button1',
    'button2',
    'button3',
    'button4',
    'button5',
    'button6',
    'button7',
    'button8',
    'up',
    'down',
    'left',
    'right'
  ],
  2: [
    'coin',
    'start',
    'button1',
    'button2',
    'button3',
    'button4',
    'button5',
    'button6',
    'button7',
    'button8',
    'up',
    'down',
    'left',
    'right'
  ],
  3: ['coin', 'start', 'button1', 'button2', 'button3', 'button4', 'up', 'down', 'left', 'right'],
  4: ['coin', 'start', 'button1', 'button2', 'button3', 'button4', 'up', 'down', 'left', 'right']
};

const CONTROL_LABEL_MAP = {
  coin: 'COIN',
  start: 'START',
  up: 'JOY UP',
  down: 'JOY DOWN',
  left: 'JOY LEFT',
  right: 'JOY RIGHT'
};

const PLAYER_LIST = [1, 2, 3, 4];
const WIZARD_SEQUENCE = [
  'p1.up',
  'p1.down',
  'p1.left',
  'p1.right',
  'p1.button1',
  'p1.button2',
  'p1.button3',
  'p1.button4',
  'p1.button5',
  'p1.button6',
  'p1.button7',
  'p1.button8',
  'p1.start',
  'p1.coin',
  'p2.up',
  'p2.down',
  'p2.left',
  'p2.right',
  'p2.button1',
  'p2.button2',
  'p2.button3',
  'p2.button4',
  'p2.button5',
  'p2.button6',
  'p2.start',
  'p2.coin'
];

const LIVE_INPUTS = ['JOY UP', 'JOY DOWN', 'JOY LEFT', 'JOY RIGHT', 'BTN 1', 'BTN 2', 'BTN 3', 'BTN 4'];

const getControlLabel = (controlKey) => {
  if (CONTROL_LABEL_MAP[controlKey]) return CONTROL_LABEL_MAP[controlKey];
  if (controlKey.startsWith('button')) {
    const number = controlKey.replace('button', '');
    return `Button ${number}`;
  }
  return controlKey.toUpperCase();
};

const formatControlKeyLabel = (controlKey) => {
  if (!controlKey) return '';
  const [player, control] = controlKey.split('.');
  const playerLabel = player?.toUpperCase() || '';
  return `${playerLabel} ${getControlLabel(control || '')}`.trim();
};

const formatMappingValue = (mappingEntry) => {
  if (!mappingEntry) return '-';

  const pieces = [];

  // Handle pin-based mappings (encoder wiring)
  if (typeof mappingEntry.pin === 'number') {
    pieces.push(`Pin ${mappingEntry.pin}`);
  }
  // Handle keycode-based mappings (gamepad/keyboard)
  else if (mappingEntry.keycode) {
    // Format keycode nicely: "GAMEPAD_BTN_8" -> "Btn 8" or "KEY_W" -> "W"
    let keyDisplay = mappingEntry.keycode;
    if (keyDisplay.startsWith('GAMEPAD_BTN_')) {
      keyDisplay = `Btn ${keyDisplay.replace('GAMEPAD_BTN_', '')}`;
    } else if (keyDisplay.startsWith('GAMEPAD_')) {
      keyDisplay = keyDisplay.replace('GAMEPAD_', '');
    } else if (keyDisplay.startsWith('KEY_')) {
      keyDisplay = keyDisplay.replace('KEY_', '');
    }
    pieces.push(`Key: ${keyDisplay}`);
  } else {
    pieces.push('-');
  }

  // Add label if present
  if (mappingEntry.label) pieces.push(mappingEntry.label);
  // Add type/source if present
  if (mappingEntry.type) {
    pieces.push(mappingEntry.type.toUpperCase());
  } else if (mappingEntry.source) {
    pieces.push(mappingEntry.source.toUpperCase());
  }

  return pieces.filter(Boolean).join(' - ');
};

function Notification({ message, show, onHide }) {
  useEffect(() => {
    if (show && message) {
      const timer = setTimeout(onHide, 3000);
      return () => clearTimeout(timer);
    }
  }, [show, message, onHide]);

  return (
    <div className={`controller-notification ${show ? 'show' : ''}`}>
      {message}
    </div>
  );
}

function StatusCard({
  boardInfo,
  arcadeBoard,
  onScanDevices,
  scanningDevices,
  consoleError,
  consoleHints
}) {
  const detected = arcadeBoard?.detected || false;
  const boardLabel = arcadeBoard?.name || boardInfo?.name || 'Unknown encoder';
  const vidPid = [arcadeBoard?.vid || boardInfo?.vid, arcadeBoard?.pid || boardInfo?.pid]
    .filter(Boolean)
    .join(':');
  const statusText = detected ? 'Encoder board detected' : 'Encoder board not detected';

  return (
    <div className={`controller-status-card ${detected ? 'fixed' : ''}`}>
      <div className="status-info">
        <div className="status-icon">{detected ? 'OK' : '!'}</div>
        <div className="status-text">
          <h3>{statusText}</h3>
          <p>
            <strong>Detected Device:</strong>{' '}
            <span>{boardLabel}</span>
            {vidPid ? (
              <>
                {' '}
                | <strong>VID/PID:</strong> <span>{vidPid}</span>
              </>
            ) : null}
          </p>
          {arcadeBoard?.status && (
            <p>
              <strong>Status:</strong> <span>{arcadeBoard.status}</span>
            </p>
          )}
        </div>
      </div>
      <div className="controller-status-actions">
        <button
          className="controller-fix-button"
          onClick={onScanDevices}
          disabled={scanningDevices}
        >
          {scanningDevices ? 'Scanning...' : 'Scan Devices'}
        </button>
      </div>
      {consoleError && (
        <div className="controller-status-warning">
          <strong>Warning:</strong> {consoleError}
        </div>
      )}
      {consoleHints && consoleHints.length > 0 && (
        <ul className="controller-status-hints">
          {consoleHints.map((hint) => (
            <li key={hint}>{hint}</li>
          ))}
        </ul>
      )}
    </div>
  );
}
function CabinetDisplay({ currentPlayer, onPlayerSwitch, isTransitioning, highlightControl }) {
  const playerAreas = useMemo(() => [
    { num: 3, class: 'p3', buttons: 4, position: 'top-left' },
    { num: 4, class: 'p4', buttons: 4, position: 'top-right' },
    { num: 1, class: 'p1', buttons: 8, position: 'bottom-left' },
    { num: 2, class: 'p2', buttons: 8, position: 'bottom-right' }
  ], []);
  const highlightedPlayer = useMemo(() => {
    if (!highlightControl) return null;
    const [player] = highlightControl.split('.');
    const index = player?.replace('p', '');
    const parsed = parseInt(index, 10);
    return Number.isNaN(parsed) ? null : parsed;
  }, [highlightControl]);

  const handlePlayerClick = useCallback((playerNum) => {
    onPlayerSwitch(playerNum);
  }, [onPlayerSwitch]);

  return (
    <div className={`controller-cabinet-display ${isTransitioning ? 'transitioning' : ''}`}>
      <div className="controller-players-layout">
        <div className="controller-center-trackball">TRACK</div>

        {playerAreas.map(({ num, class: className, buttons, position }) => (
          <div
            key={num}
            className={`controller-player-area ${className} ${currentPlayer === num ? 'active' : ''} ${highlightedPlayer === num ? 'highlight' : ''}`}
            onClick={() => handlePlayerClick(num)}
            role="button"
            tabIndex={0}
            onKeyDown={(e) => e.key === 'Enter' && handlePlayerClick(num)}
            aria-label={`Select Player ${num}`}
          >
            <div className="controller-button-count-badge">{buttons} BTN</div>
            <div className="controller-player-label">Player {num}</div>

            <div className="controller-player-controls">
              <div className="controller-joystick">
                <div className="controller-joystick-ball"></div>
              </div>

              <div className={`controller-button-grid controller-button-grid-${buttons}`}>
                {Array.from({ length: buttons }, (_, i) => (
                  <div key={i} className="controller-action-button">
                    {buttons === 8 ? (i < 3 ? i + 1 : i === 3 ? 7 : i + 1) : i + 1}
                  </div>
                ))}
              </div>
            </div>

            <div className="controller-start-coin-buttons">
              <div className="controller-system-button">START</div>
              <div className="controller-system-button">COIN</div>
            </div>
          </div>
        ))}
      </div>
    </div>
  );
}

function MappingTable({
  currentPlayer,
  onPlayerSwitch,
  mappingData,
  pendingChanges,
  isLoading,
  errorMessage,
  onEditMapping,
  onClearPending
}) {
  const rows = useMemo(() => {
    const controls = PLAYER_CONTROL_ORDER[currentPlayer] || [];
    return controls.map((controlKey) => {
      const mappingKey = `p${currentPlayer}.${controlKey}`;
      const pending = pendingChanges?.[mappingKey];
      const mappingEntry = pending || mappingData?.[mappingKey];
      const status = pending ? 'PENDING' : mappingEntry ? 'MAPPED' : 'UNMAPPED';

      return {
        mappingKey,
        label: getControlLabel(controlKey),
        mappingValue: formatMappingValue(mappingEntry),
        status,
        pending: Boolean(pending)
      };
    });
  }, [currentPlayer, mappingData, pendingChanges]);

  return (
    <div className="controller-table-container">
      <div className="controller-table-header">
        <h3>Button Mappings</h3>
        <div className="controller-player-selector">
          {PLAYER_LIST.map((num) => (
            <button
              key={num}
              className={`controller-player-tab ${currentPlayer === num ? 'active' : ''}`}
              onClick={() => onPlayerSwitch(num)}
              aria-label={`View Player ${num} mappings`}
            >
              P{num}
            </button>
          ))}
        </div>
      </div>

      <div className="controller-scrollable-table">
        <table>
          <thead>
            <tr>
              <th>Input</th>
              <th>Mapping</th>
              <th>Status</th>
              <th>Actions</th>
            </tr>
          </thead>
          <tbody>
            {isLoading ? (
              <tr>
                <td colSpan={4} className="controller-mapping-loading">
                  Loading mapping dictionary…
                </td>
              </tr>
            ) : errorMessage ? (
              <tr>
                <td colSpan={4} className="controller-mapping-error">
                  {errorMessage}
                </td>
              </tr>
            ) : rows.length === 0 ? (
              <tr>
                <td colSpan={4} className="controller-mapping-empty">
                  No mapping data available.
                </td>
              </tr>
            ) : (
              rows.map((row) => (
                <tr key={row.mappingKey} className={row.pending ? 'pending' : ''}>
                  <td>
                    <span className="controller-input-label">{row.label}</span>
                  </td>
                  <td>
                    <span className="controller-mapping-value">{row.mappingValue}</span>
                  </td>
                  <td>
                    <span className={`controller-status-badge ${row.status.toLowerCase()}`}>
                      {row.status}
                    </span>
                  </td>
                  <td className="controller-mapping-actions">
                    <button
                      className="controller-table-action"
                      onClick={() => onEditMapping(row.mappingKey, row.label)}
                    >
                      Edit
                    </button>
                    {row.pending && (
                      <button
                        className="controller-table-action secondary"
                        onClick={() => onClearPending(row.mappingKey)}
                        title="Remove pending change"
                      >
                        Undo
                      </button>
                    )}
                  </td>
                </tr>
              ))
            )}
          </tbody>
        </table>
      </div>
    </div>
  );
}

function ChatSidebar({ isCollapsed, onToggle, messages, onSendMessage, inputValue, setInputValue }) {
  const [isRecording, setIsRecording] = useState(false);
  const [isProcessing, setIsProcessing] = useState(false);
  const recognitionRef = useRef(null);

  const handleSend = useCallback(() => {
    if (inputValue.trim()) {
      onSendMessage(inputValue.trim());
      setInputValue('');
    }
  }, [inputValue, onSendMessage, setInputValue]);

  const handleKeyDown = useCallback((e) => {
    if (e.key === 'Enter' && !e.shiftKey) {
      e.preventDefault();
      handleSend();
    }
  }, [handleSend]);

  const startVoiceRecording = useCallback(async () => {
    console.log('[Chuck] startVoiceRecording called');

    // STOP any currently playing TTS audio
    try {
      stopSpeaking();
      console.log('[Chuck] Stopped any playing TTS audio');
    } catch (err) {
      console.error('[Chuck] Could not stop TTS:', err);
    }

    try {
      const SpeechRecognition = window.SpeechRecognition || window.webkitSpeechRecognition;
      console.log('[Chuck] SpeechRecognition available:', !!SpeechRecognition);

      if (!SpeechRecognition) {
        onSendMessage('[System] ❌ Speech recognition not supported in this browser. Use Chrome/Edge.');
        return;
      }

      const recognition = new SpeechRecognition();
      recognition.continuous = false;
      recognition.interimResults = false;
      recognition.lang = 'en-US';
      recognition.maxAlternatives = 1;

      recognition.onstart = () => {
        console.log('[Chuck] Speech recognition started');
        setIsRecording(true);

        // Auto-stop after 5 seconds of recording (safety timeout)
        const autoStopTimer = setTimeout(() => {
          console.log('[Chuck] Auto-stopping after 5 seconds');
          if (recognitionRef.current) {
            recognitionRef.current.stop();
          }
        }, 5000);

        // Store timer so we can clear it if user stops manually
        recognitionRef.autoStopTimer = autoStopTimer;
      };

      recognition.onresult = async (event) => {
        // Only process if this is the FINAL result
        const result = event.results[event.results.length - 1];
        if (!result.isFinal) {
          console.log('[Chuck] Interim result, skipping:', result[0].transcript);
          return;
        }

        const transcript = result[0].transcript;
        console.log('[Chuck] FINAL Transcribed:', transcript);

        // Set the transcript in the input field and send it
        setInputValue(transcript);
        setIsProcessing(true);

        try {
          // Send the transcribed message
          await onSendMessage(transcript);
        } catch (error) {
          console.error('[Chuck] Voice chat error:', error);
        } finally {
          setIsProcessing(false);
        }
      };

      recognition.onerror = (event) => {
        console.error('[Chuck] Speech recognition error:', event.error);
        setIsRecording(false);
      };

      recognition.onend = () => {
        console.log('[Chuck] Speech recognition ended');
        setIsRecording(false);

        // Clear the auto-stop timer
        if (recognitionRef.autoStopTimer) {
          clearTimeout(recognitionRef.autoStopTimer);
          recognitionRef.autoStopTimer = null;
        }

        recognitionRef.current = null;
      };

      recognitionRef.current = recognition;
      recognition.start();

    } catch (err) {
      console.error('[Chuck] Speech recognition error:', err);
      setIsRecording(false);
    }
  }, [onSendMessage, setInputValue]);

  const stopVoiceRecording = useCallback(() => {
    console.log('[Chuck] stopVoiceRecording called');
    if (recognitionRef.current) {
      recognitionRef.current.stop();
    }
    setIsRecording(false);
  }, []);

  const toggleMic = useCallback(() => {
    console.log('[Chuck] Toggle mic clicked, isRecording:', isRecording);
    if (isRecording) {
      stopVoiceRecording();
    } else {
      startVoiceRecording();
    }
  }, [isRecording, startVoiceRecording, stopVoiceRecording]);

  return (
    <div className={`controller-chat-sidebar ${isCollapsed ? 'collapsed' : ''}`}>
      <div className="controller-chat-header">
        <img
          src="/chuck-avatar.jpeg"
          alt="Chuck"
          style={{
            width: '48px',
            height: '48px',
            borderRadius: '50%',
            border: '2px solid rgba(0, 229, 255, 0.4)',
            boxShadow: '0 0 12px rgba(200, 255, 0, 0.4)',
            objectFit: 'cover'
          }}
        />
        <h4>Chuck AI Assistant</h4>
      </div>

      <div className="controller-chat-history">
        {messages.map((message, index) => (
          <div
            key={index}
            className={`controller-message ${message.type === 'assistant' ? 'chuck-message' : 'user-message'}`}
            dangerouslySetInnerHTML={{ __html: message.content }}
          />
        ))}
      </div>

      <div className="controller-chat-input-area">
        <input
          type="text"
          className="controller-chat-input"
          placeholder="Type your message..."
          value={inputValue}
          onChange={(e) => setInputValue(e.target.value)}
          onKeyDown={handleKeyDown}
        />
        <button
          className={`controller-icon-button ${isRecording ? 'recording' : ''}`}
          data-tooltip={isRecording ? "Stop recording" : "Voice input"}
          aria-label="Voice input"
          onClick={toggleMic}
          disabled={isProcessing}
        >
          {isRecording ? '🔴' : '🎤'}
        </button>
        <button
          className="controller-icon-button"
          data-tooltip="Send message"
          onClick={handleSend}
          aria-label="Send message"
        >
          ➤
        </button>
      </div>
    </div>
  );
}

export default function ControllerPanel() {
  const location = useLocation();
  const navigate = useNavigate();
  const params = new URLSearchParams(location.search);
  // Minimal by default; diagnostics shown inline when requested.
  const showDiagnostics = params.get('diag') === '1' || params.get('mode') === 'full';
  const [currentPlayer, setCurrentPlayer] = useState(1);
  const [isTransitioning, setIsTransitioning] = useState(false);
  const [chatCollapsed, setChatCollapsed] = useState(false);
  const [notification, setNotification] = useState({ show: false, message: '' });
  const [liveInput, setLiveInput] = useState('---');
  const [chatMessages, setChatMessages] = useState([
    {
      type: 'assistant',
      content: "Hi! I'm Chuck, your Controller Expert. I can help with mapping and troubleshooting."
    }
  ]);
  const [chatInput, setChatInput] = useState('');

  const [mappingData, setMappingData] = useState({});
  const [boardInfo, setBoardInfo] = useState(null);
  const [mappingLoading, setMappingLoading] = useState(true);
  const [mappingError, setMappingError] = useState('');
  const [pendingChanges, setPendingChanges] = useState({});
  const [previewResult, setPreviewResult] = useState(null);
  const [previewError, setPreviewError] = useState('');
  const [previewLoading, setPreviewLoading] = useState(false);
  const [applyLoading, setApplyLoading] = useState(false);
  const [resettingMapping, setResettingMapping] = useState(false);
  const [devices, setDevices] = useState([]);
  const [devicePollingError, setDevicePollingError] = useState('');
  const [devicePolling, setDevicePolling] = useState(false);
  const [pendingDevice, setPendingDevice] = useState(null);
  const [classifyingDeviceId, setClassifyingDeviceId] = useState(null);
  const seenUnknownDevicesRef = useRef(new Set());
  const [wizardActive, setWizardActive] = useState(false);
  const [wizardStep, setWizardStep] = useState(null);
  const [wizardCaptures, setWizardCaptures] = useState({});
  const [wizardPreview, setWizardPreview] = useState(null);
  const [wizardStatus, setWizardStatus] = useState('');
  const [wizardRunning, setWizardRunning] = useState(false);
  const [wizardError, setWizardError] = useState('');
  const [wizardTestRunning, setWizardTestRunning] = useState(false);

  // Handheld (console) controller detection state
  const [consoleDetecting, setConsoleDetecting] = useState(false);
  const [consoleError, setConsoleError] = useState('');
  const [consoleControllers, setConsoleControllers] = useState([]);
  const [consoleHints, setConsoleHints] = useState([]);
  const { latestEvent: controllerEvent } = useControllerEvents(true);
  const learnWizard = useLearnWizard({ voiceEnabled: true });
  const captureMode = useCaptureMode();
  const [encoderMode, setEncoderMode] = useState('keyboard');
  const [playerCount, setPlayerCount] = useState(4);  // 2, 3, or 4 player cabinet
  const lastControllerEventRef = useRef(null);
  const handoffProcessedRef = useRef(null);
  const arcadeBoard = useMemo(
    () => consoleControllers.find((device) => device.type === 'arcade_board'),
    [consoleControllers]
  );
  const pendingCount = useMemo(() => Object.keys(pendingChanges).length, [pendingChanges]);

  useEffect(() => {
    setPreviewResult(null);
    setPreviewError('');
  }, [pendingChanges]);

  const loadMapping = useCallback(
    async ({ silent = false } = {}) => {
      try {
        if (!silent) setMappingLoading(true);
        setMappingError('');
        const res = await fetch('/api/local/controller/mapping');
        if (!res.ok) {
          throw new Error('Failed to load mapping dictionary');
        }
        const data = await res.json();
        setMappingData(data?.mapping?.mappings || {});
        setBoardInfo(data?.mapping?.board || null);
        if (!silent) {
          setPendingChanges({});
        }
      } catch (error) {
        console.error('Failed to load mapping:', error);
        setMappingError(error?.message || 'Failed to load mapping dictionary');
      } finally {
        setMappingLoading(false);
      }
    },
    []
  );

  useEffect(() => {
    loadMapping();
  }, [loadMapping]);

  const loadDevices = useCallback(async () => {
    try {
      setDevicePolling(true);
      setDevicePollingError('');
      const snapshot = await fetchDeviceSnapshot();
      const rawList = Array.isArray(snapshot?.devices) ? snapshot.devices : [];

      // Deduplicate devices by VID:PID (each physical device may have multiple HID interfaces)
      const vidPidMap = new Map();
      rawList.forEach((device) => {
        const key = `${device.vid || ''}:${device.pid || ''}`;
        // Keep the first occurrence, or prefer one with a product name
        if (!vidPidMap.has(key) || (device.product && !vidPidMap.get(key).product)) {
          vidPidMap.set(key, device);
        }
      });
      const list = Array.from(vidPidMap.values());

      setDevices(list);
      const unknown = list.find((device) => !device.is_known);
      setPendingDevice(unknown || null);

      // Track new unknown devices by VID:PID instead of device_id to avoid duplicates
      const newUnknownDevices = [];
      list.forEach((device) => {
        const vidPidKey = `${device.vid || ''}:${device.pid || ''}`;
        if (!device.is_known && vidPidKey !== ':' && !seenUnknownDevicesRef.current.has(vidPidKey)) {
          seenUnknownDevicesRef.current.add(vidPidKey);
          newUnknownDevices.push(device);
        }
      });

      // Add ONE summary message for all new unknown devices instead of spamming
      if (newUnknownDevices.length > 0) {
        const deviceSummary = newUnknownDevices.length === 1
          ? `a new input device (${newUnknownDevices[0].vid || 'unknown'}:${newUnknownDevices[0].pid || 'unknown'})`
          : `${newUnknownDevices.length} new input devices`;
        setChatMessages((prev) => [
          ...prev,
          {
            type: 'assistant',
            content: `I see ${deviceSummary}. Should this be your encoder board, a handheld controller, or ignored?`
          }
        ]);
      }
    } catch (error) {
      setDevicePollingError(error?.message || 'Failed to load devices');
    } finally {
      setDevicePolling(false);
    }
  }, [setChatMessages]);

  useEffect(() => {
    loadDevices();
    const interval = setInterval(loadDevices, 10000);
    return () => clearInterval(interval);
  }, [loadDevices]);

  const detectConsoleControllers = useCallback(async () => {
    try {
      setConsoleDetecting(true);
      setConsoleError('');
      setConsoleHints([]);
      setConsoleControllers([]);

      // Use relative path so Vite proxy forwards to backend
      const res = await fetch('/api/local/controller/devices');
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

        // Try health for actionable hint
        try {
          const h = await fetch('/api/local/controller/health');
          if (h.ok) {
            const hv = await h.json();
            if (hv.usb_backend === 'backend_unavailable') {
              msg = 'USB backend unavailable. Run backend on Windows (start-gui.bat), or on WSL install libusb and attach device with usbipd.';
            } else if (hv.permissions === 'permission_denied') {
              msg = 'USB permission denied. Run as Administrator (Windows) or use sudo/add user to plugdev (Linux).';
            }
          }
        } catch (_e) { /* ignore */ }

        setConsoleHints(Array.isArray(data?.hints) ? data.hints.filter(Boolean) : []);
        setConsoleError(msg);
      }
    } catch (e) {
      setConsoleError(e?.message || 'Controller detection failed.');
      setConsoleHints([]);
    } finally {
      setConsoleDetecting(false);
    }
  }, []);

  useEffect(() => {
    detectConsoleControllers();
  }, [detectConsoleControllers]);

  const showNotification = useCallback((message) => {
    setNotification({ show: true, message });
  }, []);

  const hideNotification = useCallback(() => {
    setNotification({ show: false, message: '' });
  }, []);

  const handleEditMapping = useCallback(
    (mappingKey, label) => {
      const currentEntry = pendingChanges[mappingKey] || mappingData[mappingKey] || {};
      const defaultPin = currentEntry.pin ?? '';
      const input = window.prompt(`Enter the encoder pin for ${label}`, defaultPin);
      if (input === null) return;
      const parsed = parseInt(input, 10);
      if (Number.isNaN(parsed) || parsed <= 0) {
        showNotification('Please enter a valid pin number (positive integer).');
        return;
      }

      const baseEntry =
        currentEntry.pin !== undefined
          ? currentEntry
          : mappingData[mappingKey] || { type: label.includes('JOY') ? 'joystick' : 'button' };

      const newEntry = {
        ...baseEntry,
        pin: parsed
      };

      const original = mappingData[mappingKey];
      setPendingChanges((prev) => {
        const next = { ...prev };
        if (original && original.pin === parsed) {
          delete next[mappingKey];
        } else {
          next[mappingKey] = newEntry;
        }
        return next;
      });
    },
    [pendingChanges, mappingData, showNotification]
  );

  const handleClearPending = useCallback((mappingKey) => {
    setPendingChanges((prev) => {
      if (!prev[mappingKey]) return prev;
      const next = { ...prev };
      delete next[mappingKey];
      return next;
    });
  }, []);

  const handleDeviceClassification = useCallback(
    async (device, role, source = 'ui') => {
      if (!device) return;
      const deviceId = typeof device === 'string' ? device : device.device_id;
      const target =
        typeof device === 'string' ? devices.find((item) => item.device_id === device) : device;
      const label =
        target?.classification?.label ||
        target?.hint?.product_name ||
        target?.product ||
        target?.device_id ||
        role;
      setClassifyingDeviceId(deviceId);
      try {
        await classifyDevice({
          deviceId,
          role,
          label,
          panels: role === 'arcade_encoder' ? ['controller'] : ['controller', 'console-wizard']
        });
        showNotification('Device classification saved.');
        await loadDevices();
        if (source === 'voice') {
          const summary =
            role === 'arcade_encoder'
              ? 'Marked as encoder board.'
              : role === 'handheld_gamepad'
                ? 'Classified as handheld controller.'
                : 'Ignoring that device.';
          setChatMessages((prev) => [
            ...prev,
            { type: 'assistant', content: `Got it. ${summary}` }
          ]);
        }
      } catch (error) {
        showNotification(error?.message || 'Failed to classify device.');
      } finally {
        setClassifyingDeviceId(null);
      }
    },
    [devices, loadDevices, setChatMessages, showNotification]
  );

  const switchPlayer = useCallback((playerNum) => {
    if (playerNum === currentPlayer) return;

    setIsTransitioning(true);
    setTimeout(() => {
      setCurrentPlayer(playerNum);
      setIsTransitioning(false);
    }, 200);

    showNotification(`Switched to Player ${playerNum}`);
  }, [currentPlayer, showNotification]);

  const toggleChat = useCallback(() => {
    setChatCollapsed(prev => !prev);
  }, []);

  const maybeHandleClassificationCommand = useCallback(
    async (message) => {
      if (!pendingDevice) return false;
      const normalized = message.toLowerCase();
      const commands = [
        {
          phrases: ['this is my encoder board', 'this is the encoder board'],
          role: 'arcade_encoder'
        },
        {
          phrases: ['this is a controller', 'this is my controller'],
          role: 'handheld_gamepad'
        },
        {
          phrases: ['ignore that device', 'ignore this device'],
          role: 'ignore'
        }
      ];
      const match = commands.find((cmd) => cmd.phrases.some((phrase) => normalized.includes(phrase)));
      if (!match) return false;
      await handleDeviceClassification(pendingDevice, match.role, 'voice');
      return true;
    },
    [pendingDevice, handleDeviceClassification]
  );

  const buildRequestHeaders = useCallback(
    (includeScope = false) => {
      const headers = {
        'Content-Type': 'application/json',
        'x-panel': 'controller',
        'x-device-id': 'controller_panel'
      };
      if (includeScope) headers['x-scope'] = 'config';
      return headers;
    },
    []
  );

  const handlePreviewChanges = useCallback(async () => {
    if (!pendingCount) {
      showNotification('No pending changes to preview.');
      return;
    }
    setPreviewLoading(true);
    setPreviewError('');
    try {
      const res = await fetch('/api/local/controller/mapping/preview', {
        method: 'POST',
        headers: buildRequestHeaders(false),
        body: JSON.stringify({ mappings: pendingChanges })
      });
      const data = await res.json().catch(() => ({}));
      if (!res.ok) {
        throw new Error(data?.detail || 'Preview failed');
      }
      setPreviewResult(data);
      showNotification('Preview updated.');
    } catch (error) {
      console.error('Preview failed:', error);
      setPreviewError(error?.message || 'Preview failed.');
    } finally {
      setPreviewLoading(false);
    }
  }, [pendingCount, pendingChanges, buildRequestHeaders, showNotification]);

  const handleApplyChanges = useCallback(async () => {
    if (!pendingCount) {
      showNotification('No pending changes to apply.');
      return;
    }
    setApplyLoading(true);
    try {
      const res = await fetch('/api/local/controller/mapping/apply', {
        method: 'POST',
        headers: buildRequestHeaders(true),
        body: JSON.stringify({ mappings: pendingChanges })
      });
      const data = await res.json().catch(() => ({}));
      if (!res.ok) {
        throw new Error(data?.detail || 'Apply failed');
      }
      showNotification('Controller mapping applied.');
      setPendingChanges({});
      setPreviewResult(null);
      await loadMapping({ silent: true });
      detectConsoleControllers();
    } catch (error) {
      console.error('Apply failed:', error);
      showNotification(error?.message || 'Failed to apply mapping changes.');
    } finally {
      setApplyLoading(false);
    }
  }, [pendingCount, pendingChanges, buildRequestHeaders, showNotification, loadMapping, detectConsoleControllers]);

  const handleResetMapping = useCallback(async () => {
    const confirmReset = window.confirm('Restore factory defaults? This will overwrite current mappings.');
    if (!confirmReset) return;

    setResettingMapping(true);
    try {
      const res = await fetch('/api/local/controller/mapping/reset', {
        method: 'POST',
        headers: buildRequestHeaders(true)
      });
      const data = await res.json().catch(() => ({}));
      if (!res.ok) {
        throw new Error(data?.detail || 'Reset failed');
      }
      showNotification('Factory defaults restored.');
      setPendingChanges({});
      setPreviewResult(null);
      await loadMapping({ silent: true });
      detectConsoleControllers();
    } catch (error) {
      console.error('Reset failed:', error);
      showNotification(error?.message || 'Failed to reset mappings.');
    } finally {
      setResettingMapping(false);
    }
  }, [buildRequestHeaders, showNotification, loadMapping, detectConsoleControllers]);

  // ============================================================================
  // Click-to-Map Handlers
  // ============================================================================

  /**
   * Handle clicking a control on the cabinet display
   */
  const handleControlClick = useCallback((controlKey) => {
    const existingMapping = mappingData[controlKey];

    if (existingMapping?.keycode) {
      // Control is already mapped - ask if they want to override
      const shouldOverride = window.confirm(
        `${getControlDisplayName(controlKey)} is already mapped to "${existingMapping.keycode}". Override?`
      );
      if (!shouldOverride) return;
    }

    // Start capture mode for this control
    captureMode.startCapture(controlKey);
    showNotification(`Click confirmed for ${getControlDisplayName(controlKey)}. Press the physical button now.`);
  }, [mappingData, captureMode, showNotification]);

  /**
   * Handle confirming a captured input
   */
  const handleConfirmCapture = useCallback(async () => {
    const result = captureMode.confirmCapture();
    if (!result) return;

    try {
      // Save to backend
      const res = await fetch('/api/local/controller/mapping/set', {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
          'x-scope': 'config',
          'x-panel': 'controller',
          'x-device-id': window.AA_DEVICE_ID || 'CAB-0001',
        },
        body: JSON.stringify({
          controlKey: result.controlKey,
          keycode: result.keycode,
          source: result.source,
        }),
      });

      if (!res.ok) {
        throw new Error('Failed to save mapping');
      }

      const data = await res.json();

      // Update local state
      setMappingData(prev => ({
        ...prev,
        [result.controlKey]: {
          keycode: result.keycode,
          source: result.source,
        }
      }));

      showNotification(`Mapped ${getControlDisplayName(result.controlKey)} → ${result.keycode}`);

      // Warn about duplicates
      if (data.duplicate_control) {
        showNotification(`Warning: ${result.keycode} was also assigned to ${data.duplicate_control}`);
      }

    } catch (error) {
      console.error('Failed to save mapping:', error);
      showNotification('Failed to save mapping: ' + error.message);
    }
  }, [captureMode, showNotification]);

  /**
   * Handle canceling capture mode
   */
  const handleCancelCapture = useCallback(() => {
    captureMode.cancelCapture();
    showNotification('Capture cancelled');
  }, [captureMode, showNotification]);

  /**
   * Handle encoder mode change
   */
  const handleEncoderModeChange = useCallback(async (newMode) => {
    setEncoderMode(newMode);

    try {
      await fetch('/api/local/controller/encoder-mode', {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
          'x-scope': 'config',
          'x-panel': 'controller',
        },
        body: JSON.stringify({ mode: newMode }),
      });
      showNotification(`Encoder mode set to ${newMode}`);
    } catch (error) {
      console.error('Failed to save encoder mode:', error);
    }
  }, [showNotification]);

  /**
   * Get mapping stats for display
   */
  const getMappingStats = useCallback(() => {
    const allControls = [];
    for (let p = 1; p <= 4; p++) {
      ['up', 'down', 'left', 'right', 'start', 'coin'].forEach(c => {
        allControls.push(`p${p}.${c}`);
      });
      const buttonCount = p <= 2 ? 8 : 4;
      for (let b = 1; b <= buttonCount; b++) {
        allControls.push(`p${p}.button${b}`);
      }
    }

    const mapped = allControls.filter(c => !!mappingData[c]?.keycode).length;
    return {
      total: allControls.length,
      mapped,
      unmapped: allControls.length - mapped,
      percentage: Math.round((mapped / allControls.length) * 100),
    };
  }, [mappingData]);

  const mappingStats = getMappingStats();

  const announceWizardInstruction = useCallback(
    async (message) => {
      if (!message) return;
      setChatMessages((prev) => [...prev, { type: 'assistant', content: message }]);
      try {
        await speak(message, { voice_id: CHUCK_VOICE_ID });
      } catch (err) {
        console.debug('Wizard speak failed', err);
      }
    },
    [setChatMessages]
  );

  const beginWizard = useCallback(async () => {
    try {
      const res = await startWiringWizard();
      setWizardActive(true);
      setWizardCaptures({});
      setWizardPreview(null);
      setWizardStatus('Wizard ready');
      setWizardStep(res?.next || null);
      if (res?.next) {
        await announceWizardInstruction(`Press ${formatControlKeyLabel(res.next)} now.`);
      }
    } catch (error) {
      setWizardError(error?.message || 'Failed to start wizard');
    }
  }, [announceWizardInstruction]);

  const fetchNextWizardStep = useCallback(async () => {
    const stepRes = await fetchWizardNextStep();
    setWizardStep(stepRes?.next || null);
    if (stepRes?.next) {
      announceWizardInstruction(`Press ${formatControlKeyLabel(stepRes.next)}.`);
    } else {
      announceWizardInstruction('All steps captured. Review and apply when ready.');
    }
  }, [announceWizardInstruction]);

  const handleWizardCapture = useCallback(async () => {
    if (!wizardActive || !wizardStep) {
      await beginWizard();
      return;
    }
    setWizardRunning(true);
    setWizardError('');
    try {
      const diag = await fetchDiagnosticsEvent();
      if (!diag?.event || diag.status !== 'detected') {
        await announceWizardInstruction("I didn't detect any input. Can we try again?");
        return;
      }
      const pin = diag.event.pin ?? diag.event?.data?.pin;
      if (pin === undefined || pin === null) {
        await announceWizardInstruction("I didn't detect any input. Can we try again?");
        return;
      }
      await captureWizardInput(wizardStep, pin, diag.event.control_type);
      setWizardCaptures((prev) => {
        const next = { ...prev, [wizardStep]: { pin, type: diag.event.control_type } };
        const duplicateEntry = Object.entries(prev).find(
          ([key, value]) => key !== wizardStep && value.pin === pin
        );
        if (duplicateEntry) {
          const [duplicateKey] = duplicateEntry;
          announceWizardInstruction(
            `Looks like ${formatControlKeyLabel(duplicateKey)} and ${formatControlKeyLabel(wizardStep)} are using the same pin. Want to redo ${formatControlKeyLabel(duplicateKey)}?`
          );
        }
        return next;
      });
      await announceWizardInstruction(`Got it. That's pin ${pin}.`);
      await fetchNextWizardStep();
    } catch (error) {
      await announceWizardInstruction("I didn't detect any input. Can we try again?");
      setWizardError(error?.message || 'Diagnostics failed');
    } finally {
      setWizardRunning(false);
    }
  }, [wizardActive, wizardStep, beginWizard, fetchNextWizardStep, announceWizardInstruction]);

  const handleWizardPreview = useCallback(async () => {
    try {
      const res = await previewWizardMapping();
      setWizardPreview(res);
      setWizardStatus('Preview ready');
    } catch (error) {
      setWizardError(error?.message || 'Failed to preview wizard mapping');
    }
  }, []);

  const handleWizardApply = useCallback(async () => {
    try {
      setWizardRunning(true);
      await applyWizardMapping();
      showNotification('Wiring wizard applied.');
      setWizardPreview(null);
      setWizardCaptures({});
      setWizardActive(false);
      setWizardStep(null);
      await loadMapping({ silent: true });
      await announceWizardInstruction('Wiring updated. Everything is synced.');
    } catch (error) {
      setWizardError(error?.message || 'Failed to apply wizard mapping');
    } finally {
      setWizardRunning(false);
    }
  }, [announceWizardInstruction, loadMapping, showNotification]);

  const runWizardTestScript = useCallback(async () => {
    setWizardTestRunning(true);
    try {
      await beginWizard();
      const simulatedPin = Math.floor(Math.random() * 40) + 1;
      const currentStep = wizardStep || WIZARD_SEQUENCE[0];
      await captureWizardInput(currentStep, simulatedPin, 'button');
      setWizardCaptures({ [currentStep]: { pin: simulatedPin, type: 'button' } });
      await handleWizardPreview();
      await fetchNextWizardStep();
    } finally {
      setWizardTestRunning(false);
    }
  }, [beginWizard, wizardStep, handleWizardPreview, fetchNextWizardStep]);

  const handleSendMessage = useCallback(async (message) => {
    const trimmed = message?.trim();
    if (!trimmed) return;

    setChatMessages(prev => [...prev, { type: 'user', content: trimmed }]);

    try {
      if (await maybeHandleClassificationCommand(trimmed)) {
        return;
      }
      const panelState = {
        currentPlayer,
        liveInput,
        consoleControllers,
        consoleError,
        consoleHints,
        boardInfo,
        mappingKeys: Object.keys(mappingData || {}),
        mappingError
      };

      const response = await controllerAIChat(trimmed, panelState, {
        panel: 'controller-chuck',  // Use Chuck's Brooklyn personality
        deviceId: 'controller_panel',
        sessionId: 'controller_panel'
      });

      const reply = response?.reply || '[No response]';
      setChatMessages(prev => [...prev, { type: 'assistant', content: reply }]);

      // Speak Chuck's response with his Brooklyn voice
      try {
        console.log('[Chuck] Speaking response with voice ID:', CHUCK_VOICE_ID);
        await speak(reply, { voice_id: CHUCK_VOICE_ID });
        console.log('[Chuck] TTS completed successfully');
      } catch (err) {
        console.error('[Chuck] TTS failed:', err);
      }

      if (response?.context?.hints && Array.isArray(response.context.hints)) {
        const newHints = response.context.hints.filter(Boolean);
        if (newHints.length) {
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
      console.error('Chat error:', error);
      const fallbacks = [
        "Check if your controller is in DPAD mode instead of analog for better compatibility.",
        "Try pressing all buttons one by one to verify they're registering properly.",
        "Make sure your controller driver is up to date and properly installed.",
        "For mapping issues, start with Player 1 and test each input systematically.",
        "Check the Mode switch on your board - DPAD mode often works better than analog."
      ];
      const fallbackMessage = fallbacks[Math.floor(Math.random() * fallbacks.length)];
      setChatMessages(prev => [...prev, {
        type: 'assistant',
        content: fallbackMessage
      }]);
    }
  }, [currentPlayer, liveInput, consoleControllers, consoleError, consoleHints, boardInfo, mappingData, mappingError, maybeHandleClassificationCommand]);

  useEffect(() => {
    if (!controllerEvent) return;
    const eventTimestamp = controllerEvent.timestamp ?? controllerEvent.board?.detection_time;
    if (eventTimestamp && lastControllerEventRef.current === eventTimestamp) return;
    if (eventTimestamp) lastControllerEventRef.current = eventTimestamp;

    const board = controllerEvent.board || {};
    const boardLabel = board.name || [board.vid, board.pid].filter(Boolean).join(':') || 'controller';

    let assistantMessage = null;

    switch (controllerEvent.event_type) {
      case 'connected':
        assistantMessage = `Encoder board ${boardLabel} connected. Ready for mapping.`;
        setConsoleError('');
        detectConsoleControllers();
        showNotification('Encoder board connected.');
        loadMapping({ silent: true });
        break;
      case 'disconnected':
        assistantMessage = `Encoder board ${boardLabel} disconnected. Check wiring and USB, then run Scan Devices.`;
        setConsoleError('Encoder board disconnected. Check wiring and try Scan Devices.');
        showNotification('Encoder board disconnected.');
        break;
      case 'error':
        {
          const err = board.error || 'Encoder board detection error';
          assistantMessage = `Encoder board error: ${err}`;
          setConsoleError(err);
        }
        break;
      case 'status':
        if (board.detected === false) {
          assistantMessage = `Encoder board ${boardLabel} not detected yet. Ensure USB is attached and press Scan Devices.`;
        }
        break;
      default:
        break;
    }

    if (assistantMessage) {
      setChatMessages(prev => [...prev, { type: 'assistant', content: assistantMessage }]);
      setConsoleHints(prev => {
        const merged = Array.isArray(prev) ? [...prev] : [];
        if (!merged.includes(assistantMessage)) merged.push(assistantMessage);
        return merged;
      });
    }
  }, [
    controllerEvent,
    detectConsoleControllers,
    showNotification,
    setConsoleError,
    setConsoleHints,
    setChatMessages,
    loadMapping
  ]);

  const handleControlAction = useCallback((action) => {
    showNotification(`${action} clicked!`);
  }, [showNotification]);

  // Live input simulation
  useEffect(() => {
    const interval = setInterval(() => {
      if (Math.random() < 0.4) {
        const randomInput = LIVE_INPUTS[Math.floor(Math.random() * LIVE_INPUTS.length)];
        setLiveInput(randomInput);
      }
    }, 1200);

    return () => clearInterval(interval);
  }, []);

  // Stop any ongoing TTS when this panel unmounts
  useEffect(() => () => { try { stopSpeaking() } catch { } }, []);

  // Handoff effect (handles Dewey → Interface context handoff)
  useEffect(() => {
    const urlParams = new URLSearchParams(location.search);
    const handoffContext = urlParams.get('context');
    const hasHandoff = Boolean((handoffContext || '').trim());
    const noHandoff = urlParams.has('nohandoff');
    const shouldHandoff = hasHandoff && !noHandoff;

    if (shouldHandoff && handoffContext !== handoffProcessedRef.current) {
      const welcomeMsg = `Hi! Dewey told me: "${handoffContext}"\n\nI'm Chuck, your Controller Expert. Let's diagnose this together.`;
      handoffProcessedRef.current = handoffContext;

      setChatMessages(prev => [...prev, { type: 'assistant', content: welcomeMsg }]);
      setChatCollapsed(false);
      speak(welcomeMsg, { voice_id: CHUCK_VOICE_ID }).catch(err => {
        console.warn('[ControllerPanel] TTS failed:', err);
      });
    }

    // Check for JSON handoff from Dewey (only when arriving via Dewey URL context)
    if (shouldHandoff) (async () => {
      try {
        const response = await fetch('/api/local/dewey/handoff/interface', {
          method: 'GET',
          headers: {
            'Content-Type': 'application/json',
            'x-device-id': window?.AA_DEVICE_ID ?? 'cabinet-001',
            'x-panel': 'controller',
            'x-scope': 'state'
          }
        });
        const text = await response.text();
        let data = null;
        if (text) {
          try {
            data = JSON.parse(text);
          } catch {
            data = text;
          }
        }

        if (data && data.handoff) {
          const rawSummary = typeof data.handoff.summary === 'string'
            ? data.handoff.summary
            : JSON.stringify(data.handoff);

          const summaryText = (rawSummary || '').trim();
          if (summaryText && summaryText !== handoffProcessedRef.current) {
            handoffProcessedRef.current = summaryText;
            const welcomeMsg = `Dewey briefed me: "${summaryText}". Let's get your controls working!`;

            setChatMessages(prev => [...prev, { type: 'assistant', content: welcomeMsg }]);
            setChatCollapsed(false);
            speak(welcomeMsg, { voice_id: CHUCK_VOICE_ID }).catch(err => {
              console.warn('[ControllerPanel] TTS failed:', err);
            });
          }
        }
      } catch (err) {
        console.warn('[ControllerPanel] Handoff fetch failed:', err);
      }
    })();
  }, [location.search]);

  const openDiagnostics = useCallback(() => {
    const next = new URLSearchParams(location.search);
    next.set('diag', '1');
    navigate({ pathname: location.pathname, search: next.toString() });
  }, [location.pathname, location.search, navigate]);

  const closeDiagnostics = useCallback(() => {
    const next = new URLSearchParams(location.search);
    next.delete('diag');
    navigate({ pathname: location.pathname, search: next.toString() });
  }, [location.pathname, location.search, navigate]);

  // Keyboard shortcuts
  useEffect(() => {
    const handleKeyDown = (e) => {
      if (['1', '2', '3', '4'].includes(e.key) && !e.target.matches('input, textarea')) {
        const playerNum = parseInt(e.key);
        switchPlayer(playerNum);
      }

      if ((e.key === 'd' || e.key === 'D') && !e.target.matches('input, textarea')) {
        if (showDiagnostics) closeDiagnostics(); else openDiagnostics();
      }

      if (e.key === 'Escape') {
        if (showDiagnostics) closeDiagnostics();
        else toggleChat();
      }
    };

    document.addEventListener('keydown', handleKeyDown);
    return () => document.removeEventListener('keydown', handleKeyDown);
  }, [switchPlayer, toggleChat, showDiagnostics, openDiagnostics, closeDiagnostics]);

  return (
    <div className="controller-panel-container">
      <div className="controller-main-content">
        <StatusCard
          boardInfo={boardInfo || {}}
          arcadeBoard={arcadeBoard}
          onScanDevices={detectConsoleControllers}
          scanningDevices={consoleDetecting}
          consoleError={consoleError}
          consoleHints={consoleHints}
        />


        {/* Controls header row with optional diagnostics toggle */}
        <div className="controller-controls-grid">
          <div className="controller-visualizer-container">
            {showDiagnostics && (
              <div className="controller-visualizer-header">
                <div className="controller-progress-info">Configuring Player {currentPlayer}</div>
                <div className="controller-current-instruction">Press joystick UP</div>
                <div className="controller-step-counter">Step 1 of 48</div>
              </div>
            )}
            {/* Player Count Selector and Actions */}
            <div className="cabinet-controls-bar">
              <div className="player-count-selector">
                <label>Cabinet Type:</label>
                <select
                  value={playerCount}
                  onChange={(e) => setPlayerCount(parseInt(e.target.value))}
                >
                  <option value={2}>2 Player</option>
                  <option value={3}>3 Player</option>
                  <option value={4}>4 Player</option>
                </select>
              </div>
              <div className="cabinet-actions">
                <button
                  className="btn btn-success"
                  onClick={async () => {
                    try {
                      // Filter out null entries - backend expects objects with at least 'keycode'
                      const filteredMappings = {};
                      Object.entries(pendingChanges).forEach(([key, value]) => {
                        if (value !== null && value !== undefined) {
                          filteredMappings[key] = value;
                        }
                      });

                      if (Object.keys(filteredMappings).length === 0) {
                        setStatusMessage('No mappings to save');
                        return;
                      }

                      const resp = await fetch('/api/local/controller/mapping/apply', {
                        method: 'POST',
                        headers: { 'Content-Type': 'application/json', 'x-scope': 'config' },
                        body: JSON.stringify({ mappings: filteredMappings })
                      });
                      if (resp.ok) {
                        setStatusMessage('Mappings saved successfully!');
                        setPendingChanges({});
                        loadMapping({ silent: true });
                      }
                    } catch (err) {
                      setStatusMessage('Failed to save: ' + err.message);
                    }
                  }}
                >
                  💾 Save Mappings
                </button>
                <button
                  className="btn btn-warning"
                  onClick={async () => {
                    if (window.confirm(`Clear all mappings for Player ${currentPlayer}?`)) {
                      const prefix = `p${currentPlayer}.`;
                      const cleared = {};
                      Object.keys(mappingData).forEach(key => {
                        if (key.startsWith(prefix)) {
                          cleared[key] = { keycode: null, source: 'cleared' };
                        }
                      });

                      // Save immediately to backend
                      try {
                        const resp = await fetch('/api/local/controller/mapping/apply', {
                          method: 'POST',
                          headers: { 'Content-Type': 'application/json', 'x-scope': 'config' },
                          body: JSON.stringify({ mappings: cleared })
                        });
                        if (resp.ok) {
                          setPendingChanges({});
                          setStatusMessage(`Cleared and saved Player ${currentPlayer} mappings`);
                          loadMapping({ silent: true });
                        } else {
                          setStatusMessage('Failed to save cleared mappings');
                        }
                      } catch (err) {
                        setStatusMessage('Error clearing: ' + err.message);
                      }
                    }
                  }}
                >
                  🗑️ Clear P{currentPlayer}
                </button>
              </div>
            </div>

            <ClickableCabinetDisplay
              mappings={mappingData}
              capturingControl={captureMode.capturingControl}
              lastCapturedKey={captureMode.lastCapturedKey}
              captureSource={captureMode.captureSource}
              onControlClick={handleControlClick}
              onConfirmCapture={handleConfirmCapture}
              onCancelCapture={handleCancelCapture}
              activePlayer={currentPlayer}
              playerCount={playerCount}
              highlightControl={learnWizard.isActive ? learnWizard.currentControl : wizardStep}
            />

            {showDiagnostics && (
              <div className="controller-visualizer-controls">
                <div className="controller-button-group">
                  <button
                    className="controller-control-button"
                    onClick={() => handleControlAction('Start Mapping')}
                  >
                    Start Mapping
                  </button>
                  <button
                    className="controller-control-button secondary"
                    onClick={() => handleControlAction('Reset Player')}
                  >
                    Reset Player
                  </button>
                </div>

                <div className="controller-status-area">
                  <span>Status:</span>
                  <div className="controller-status-indicator">Waiting for input...</div>
                  <span>Live Input:</span>
                  <div className="controller-live-input">{liveInput}</div>
                </div>
              </div>
            )}
          </div>

          <MappingTable
            currentPlayer={currentPlayer}
            onPlayerSwitch={switchPlayer}
            mappingData={mappingData}
            pendingChanges={pendingChanges}
            isLoading={mappingLoading}
            errorMessage={mappingError}
            onEditMapping={handleEditMapping}
            onClearPending={handleClearPending}
          />
        </div>

        <div className="controller-mapping-actions-panel">
          <div>
            <strong>Pending changes:</strong> {pendingCount || 0}
            {previewError && <span className="controller-mapping-error-text"> - {previewError}</span>}
          </div>
          <div className="controller-mapping-actions-buttons">
            <button
              className="controller-control-button"
              onClick={handlePreviewChanges}
              disabled={!pendingCount || previewLoading}
            >
              {previewLoading ? 'Previewing...' : 'Preview Changes'}
            </button>
            <button
              className="controller-control-button primary"
              onClick={handleApplyChanges}
              disabled={!pendingCount || applyLoading}
            >
              {applyLoading ? 'Applying...' : 'Apply Mapping'}
            </button>
            <button
              className="controller-control-button secondary"
              onClick={handleResetMapping}
              disabled={resettingMapping}
            >
              {resettingMapping ? 'Restoring...' : 'Factory Reset'}
            </button>
          </div>
          {previewResult && (
            <div className="controller-preview-summary">
              <div>
                <strong>Validation:</strong>{' '}
                {previewResult.validation?.valid ? 'Valid' : 'Issues detected'}
              </div>
              {!!(previewResult.validation?.errors || []).length && (
                <ul className="controller-preview-errors">
                  {previewResult.validation.errors.map((err) => (
                    <li key={err}>{err}</li>
                  ))}
                </ul>
              )}
              {!!(previewResult.validation?.warnings || []).length && (
                <ul className="controller-preview-warnings">
                  {previewResult.validation.warnings.map((warn) => (
                    <li key={warn}>{warn}</li>
                  ))}
                </ul>
              )}
              {previewResult.cascade_preview?.needs_cascade && (
                <div className="controller-preview-cascade">
                  Cascade required for {previewResult.cascade_preview.changed_controls.length} controls.
                </div>
              )}
            </div>
          )}
        </div>

        <div className="controller-device-panel">
          <div className="controller-device-header">
            <h3>Detected Input Devices</h3>
            <button
              className="controller-control-button"
              onClick={loadDevices}
              disabled={devicePolling}
            >
              {devicePolling ? 'Scanning…' : 'Refresh'}
            </button>
          </div>
          {devicePollingError && (
            <div className="controller-status-warning">{devicePollingError}</div>
          )}
          <div className="controller-device-list">
            {devices.map((device) => (
              <div
                key={device.device_id}
                className={`controller-device-card ${!device.is_known ? 'unknown' : ''}`}
              >
                <div className="controller-device-title">
                  {device.hint?.product_name || device.product || 'Unknown Device'}
                </div>
                <div className="controller-device-meta">
                  VID: {device.vid || '---'} | PID: {device.pid || '---'}
                </div>
                <div className="controller-device-meta">
                  Role:{' '}
                  {device.classification?.role
                    ? device.classification.role.replace('_', ' ')
                    : 'Unclassified'}
                </div>
                {device.hint?.notes && (
                  <div className="controller-device-hint">{device.hint.notes}</div>
                )}
                {!device.is_known && (
                  <div className="controller-device-actions">
                    <button
                      onClick={() => handleDeviceClassification(device, 'arcade_encoder')}
                      disabled={classifyingDeviceId === device.device_id}
                    >
                      Mark as Encoder
                    </button>
                    <button
                      onClick={() => handleDeviceClassification(device, 'handheld_gamepad')}
                      disabled={classifyingDeviceId === device.device_id}
                    >
                      Mark as Controller
                    </button>
                    <button
                      onClick={() => handleDeviceClassification(device, 'ignore')}
                      disabled={classifyingDeviceId === device.device_id}
                    >
                      Ignore
                    </button>
                  </div>
                )}
              </div>
            ))}
            {devices.length === 0 && (
              <div className="controller-mapping-empty">No devices detected.</div>
            )}
          </div>
        </div>

        {/* Unified Controller Mapping is now at the top */}

        {showDiagnostics ? (
          <div className="controller-control-bar">
            <button
              className="controller-neon-button"
              onClick={closeDiagnostics}
            >
              Back to Controls
            </button>
            <button
              className="controller-neon-button primary"
              onClick={() => handleControlAction('Save Profile')}
            >
              Save Profile
            </button>
            <button
              className="controller-neon-button"
              onClick={() => handleControlAction('Load Profile')}
            >
              Load Profile
            </button>
            <button
              className="controller-neon-button"
              onClick={() => handleControlAction('Export Config')}
            >
              Export Config
            </button>
          </div>
        ) : (
          <div className="controller-control-bar">
            <button
              className="controller-neon-button primary"
              onClick={openDiagnostics}
            >
              Open Diagnostics
            </button>
          </div>
        )}
      </div>

      {/* Chat sidebar always available */}
      <ChatSidebar
        isCollapsed={chatCollapsed}
        onToggle={toggleChat}
        messages={chatMessages}
        onSendMessage={handleSendMessage}
        inputValue={chatInput}
        setInputValue={setChatInput}
      />

      {/* Chat toggle */}
      <button
        className="controller-chat-toggle-btn"
        onClick={toggleChat}
        title={chatCollapsed ? 'Open Chuck Assistant' : 'Close Chuck Assistant'}
        aria-label={chatCollapsed ? 'Open Chuck Assistant' : 'Close Chuck Assistant'}
      >
        {chatCollapsed ? '💬' : '✕'}
      </button>

      <Notification
        message={notification.message}
        show={notification.show}
        onHide={hideNotification}
      />
    </div>
  );
}

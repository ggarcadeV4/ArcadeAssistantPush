/**
 * @deprecated 
 * Primary logic moved to panels/controller/ControllerChuckPanel.jsx using Gemini Engine
 *
 * This file is NOT imported by Assistants.jsx and is kept only for reference.
 * The active ControllerChuckPanel is located at: frontend/src/panels/controller/ControllerChuckPanel.jsx
 *
 * Safe to delete after 2025-02-01 if no other imports are found.
 * Check with: grep -r "components/ControllerChuckPanel" frontend/src
 */
// frontend/src/components/ControllerChuckPanel.jsx
import React, { useState, useEffect, useRef, useCallback, useMemo } from 'react';
import PanelShell from '../panels/_kit/PanelShell';
import './ControllerChuckPanel.css';

const CONTROLLER_API_BASE = '/api/local/controller';
const DEVICE_ID = window?.AA_DEVICE_ID || 'controller_chuck_legacy';
const STATE_HEADERS = {
  'x-scope': 'state',
  'x-panel': 'controller-chuck',
  'x-device-id': DEVICE_ID,
};
const CONFIG_HEADERS = {
  'Content-Type': 'application/json',
  'x-scope': 'config',
  'x-panel': 'controller-chuck',
  'x-device-id': DEVICE_ID,
};

// WebSocket Manager - extracted outside component for performance
class ControllerWebSocketManager {
  constructor() {
    this.ws = null;
    this.listeners = new Set();
    this.reconnectTimer = null;
    this.isConnecting = false;
  }

  connect() {
    this.notifyListeners({ type: 'connected' });
  }

  scheduleReconnect() {
    if (this.reconnectTimer) clearTimeout(this.reconnectTimer);
    this.reconnectTimer = setTimeout(() => this.connect(), 3000);
  }

  disconnect() {
    if (this.reconnectTimer) clearTimeout(this.reconnectTimer);
    if (this.ws) {
      this.ws.close();
      this.ws = null;
    }
  }

  send(message) {
    if (this.ws && this.ws.readyState === WebSocket.OPEN) {
      this.ws.send(JSON.stringify(message));
    }
  }

  addListener(listener) {
    this.listeners.add(listener);
  }

  removeListener(listener) {
    this.listeners.delete(listener);
  }

  notifyListeners(data) {
    this.listeners.forEach(listener => listener(data));
  }
}

const wsManager = new ControllerWebSocketManager();

// Logical button definitions
const LOGICAL_BUTTONS = [
  { id: 'up', label: 'Up', icon: '↑' },
  { id: 'down', label: 'Down', icon: '↓' },
  { id: 'left', label: 'Left', icon: '←' },
  { id: 'right', label: 'Right', icon: '→' },
  { id: 'button1', label: 'Button 1', icon: '①' },
  { id: 'button2', label: 'Button 2', icon: '②' },
  { id: 'button3', label: 'Button 3', icon: '③' },
  { id: 'button4', label: 'Button 4', icon: '④' },
  { id: 'button5', label: 'Button 5', icon: '⑤' },
  { id: 'button6', label: 'Button 6', icon: '⑥' },
  { id: 'button7', label: 'Button 7', icon: '⑦' },
  { id: 'button8', label: 'Button 8', icon: '⑧' }
];

/**
 * Controller Chuck Panel - Arcade controller configuration and testing
 * @returns {JSX.Element} Controller configuration panel
 */
function ControllerChuckPanel() {
  const [devices, setDevices] = useState([]);
  const [mappings, setMappings] = useState({});
  const [editingButton, setEditingButton] = useState(null);
  const [testActive, setTestActive] = useState(false);
  const [testResults, setTestResults] = useState({});
  const [buttonStates, setButtonStates] = useState({});
  const [stickyCounters, setStickyCounters] = useState({});
  const [latency, setLatency] = useState(0);
  const [wsConnected, setWsConnected] = useState(false);
  const [flashMessage, setFlashMessage] = useState(null);
  const [loading, setLoading] = useState(false);

  const testStartTime = useRef(null);
  const latencyTimer = useRef(null);

  /**
   * Show flash message
   * @param {string} message - Message to display
   * @param {string} type - 'success' or 'error'
   */
  const showFlash = useCallback((message, type) => {
    setFlashMessage({ message, type });
    setTimeout(() => setFlashMessage(null), 3000);
  }, []);

  // Fetch initial devices
  useEffect(() => {
    const fetchDevices = async () => {
      try {
        const response = await fetch(`${CONTROLLER_API_BASE}/devices`, {
          headers: STATE_HEADERS,
        });
        if (!response.ok) {
          throw new Error(`Device scan failed (${response.status})`);
        }
        const data = await response.json();
        const nextDevices = Array.isArray(data)
          ? data
          : Array.isArray(data?.controllers)
            ? data.controllers
            : [];
        setDevices(nextDevices);
        setWsConnected(true);
      } catch (error) {
        console.error('Failed to fetch devices:', error);
        setWsConnected(false);
        showFlash('Failed to load controllers', 'error');
      }
    };

    const fetchMapping = async () => {
      try {
        const response = await fetch(`${CONTROLLER_API_BASE}/mapping`, {
          headers: STATE_HEADERS,
        });
        if (!response.ok) {
          return;
        }
        const data = await response.json();
        const rawMappings = data?.mapping?.mappings || {};
        const nextMappings = {};
        LOGICAL_BUTTONS.forEach((button) => {
          const controlKey = `p1.${button.id}`;
          const mappingEntry = rawMappings[controlKey];
          if (mappingEntry && typeof mappingEntry.pin === 'number') {
            nextMappings[button.id] = mappingEntry.pin;
          }
        });
        setMappings(nextMappings);
      } catch (error) {
        console.error('Failed to fetch controller mapping:', error);
      }
    };

    fetchDevices();
    fetchMapping();
  }, [showFlash]);

  // WebSocket connection
  useEffect(() => {
    const handleWsMessage = (data) => {
      switch (data.type) {
        case 'connected':
          setWsConnected(true);
          break;
        case 'disconnected':
          setWsConnected(false);
          break;
        case 'controller_detected':
          setDevices(prev => [...prev, data.data]);
          showFlash('Controller connected', 'success');
          break;
        case 'controller_lost':
          setDevices(prev => prev.filter(d => d.vid !== data.data.vid || d.pid !== data.data.pid));
          showFlash('Controller disconnected', 'error');
          break;
        case 'controller_issue':
          showFlash(`Controller issue: ${data.data.message}`, 'error');
          break;
        case 'test_press_result':
          handleTestResult(data);
          break;
      }
    };

    wsManager.addListener(handleWsMessage);
    wsManager.connect();

    return () => {
      wsManager.removeListener(handleWsMessage);
    };
  }, []);

  /**
   * Handle test button press results
   * @param {Object} data - WebSocket message data
   */
  const handleTestResult = useCallback((data) => {
    const now = Date.now();
    if (testStartTime.current) {
      setLatency(now - testStartTime.current);
    }

    const buttonId = `port_${data.port}`;
    setButtonStates(prev => ({ ...prev, [buttonId]: data.state }));

    if (data.state && data.sticky) {
      setStickyCounters(prev => ({
        ...prev,
        [buttonId]: (prev[buttonId] || 0) + 1
      }));
    }
  }, []);

  /**
   * Start diagnostics test
   */
  const startTest = useCallback(() => {
    setTestActive(true);
    setTestResults({});
    setStickyCounters({});
    setButtonStates({});
    testStartTime.current = Date.now();

    // Send test start message
    wsManager.send({ type: 'start_test' });

    // Start latency timer
    latencyTimer.current = setInterval(() => {
      if (testStartTime.current) {
        setLatency(Date.now() - testStartTime.current);
      }
    }, 100);
  }, []);

  /**
   * Stop diagnostics test
   */
  const stopTest = useCallback(() => {
    setTestActive(false);
    testStartTime.current = null;

    if (latencyTimer.current) {
      clearInterval(latencyTimer.current);
      latencyTimer.current = null;
    }

    wsManager.send({ type: 'stop_test' });
    showFlash('Test completed', 'success');
  }, [showFlash]);

  /**
   * Save button mapping
   * @param {string} logical - Logical button ID
   * @param {number} port - Port number
   */
  const saveMapping = useCallback(async (logical, port) => {
    setLoading(true);
    try {
      const normalizedPort = Number.parseInt(port, 10);
      if (!Number.isFinite(normalizedPort) || normalizedPort <= 0) {
        showFlash('Invalid port number', 'error');
        return;
      }

      const isDirection = logical === 'up' || logical === 'down' || logical === 'left' || logical === 'right';
      const response = await fetch(`${CONTROLLER_API_BASE}/mapping/apply`, {
        method: 'POST',
        headers: CONFIG_HEADERS,
        body: JSON.stringify({
          mappings: {
            [`p1.${logical}`]: {
              pin: normalizedPort,
              type: isDirection ? 'joystick' : 'button'
            }
          }
        })
      });

      if (response.ok) {
        setMappings(prev => ({ ...prev, [logical]: normalizedPort }));
        showFlash('Mapping saved', 'success');
        setEditingButton(null);
      } else {
        showFlash('Failed to save mapping', 'error');
      }
    } catch (error) {
      console.error('Failed to save mapping:', error);
      showFlash('Failed to save mapping', 'error');
    } finally {
      setLoading(false);
    }
  }, [showFlash]);

  // Memoized device table rows
  const formatHex = useCallback((value) => {
    if (typeof value !== 'number') return '--';
    return `0x${value.toString(16).toUpperCase()}`;
  }, []);

  const deviceRows = useMemo(() => (
    devices.map(device => (
      <tr key={`${device.vid}_${device.pid}`}>
        <td className="device-vid">{formatHex(device.vid)}</td>
        <td className="device-pid">{formatHex(device.pid)}</td>
        <td className="device-name">{device.name || 'Unknown Device'}</td>
        <td className="device-status">
          <span className={`status-indicator ${device.status || 'connected'}`}>
            {device.status || 'Connected'}
          </span>
        </td>
      </tr>
    ))
  ), [devices, formatHex]);

  // Memoized button grid
  const buttonGrid = useMemo(() => (
    LOGICAL_BUTTONS.map(button => (
      <div key={button.id} className="mapping-button">
        <div className="button-icon">{button.icon}</div>
        <div className="button-label">{button.label}</div>
        {editingButton === button.id ? (
          <input
            type="number"
            min="1"
            max="12"
            defaultValue={mappings[button.id] || 1}
            onBlur={(e) => saveMapping(button.id, parseInt(e.target.value))}
            onKeyDown={(e) => {
              if (e.key === 'Enter') {
                saveMapping(button.id, parseInt(e.target.value));
              } else if (e.key === 'Escape') {
                setEditingButton(null);
              }
            }}
            autoFocus
            className="port-input"
          />
        ) : (
          <div
            className="port-number"
            onClick={() => setEditingButton(button.id)}
          >
            Port {mappings[button.id] || '-'}
          </div>
        )}
      </div>
    ))
  ), [mappings, editingButton, saveMapping]);

  const hasControllers = devices.length > 0;

  return (
    <PanelShell
      title="Controller Chuck"
      subtitle="Arcade controller configuration and testing"
      icon={<img src="/chuck-avatar.jpeg" alt="Chuck" className="panel-avatar" />}
      status={wsConnected ? (hasControllers ? 'online' : 'degraded') : 'offline'}
      headerActions={
        <div className="hotplug-indicator">
          <div className={`hotplug-status ${hasControllers ? 'connected' : 'disconnected'}`}>
            {hasControllers ? '🎮 Controllers Connected' : '⚠️ No Controllers'}
          </div>
        </div>
      }
    >
      <div className="controller-chuck-content">
        {flashMessage && (
          <div className={`flash-message ${flashMessage.type}`}>
            {flashMessage.message}
          </div>
        )}

        <section className="devices-section">
          <h3>Detected Controllers</h3>
          <div className="devices-table-wrapper">
            <table className="devices-table">
              <thead>
                <tr>
                  <th>VID</th>
                  <th>PID</th>
                  <th>Name</th>
                  <th>Status</th>
                </tr>
              </thead>
              <tbody>
                {deviceRows.length > 0 ? deviceRows : (
                  <tr>
                    <td colSpan="4" className="no-devices">No controllers detected</td>
                  </tr>
                )}
              </tbody>
            </table>
          </div>
        </section>

        <section className="mapping-section">
          <h3>Button Mapping</h3>
          <div className="mapping-grid">
            {buttonGrid}
          </div>
        </section>

        <section className="diagnostics-section">
          <h3>Diagnostics Tester</h3>
          <div className="test-controls">
            {!testActive ? (
              <button onClick={startTest} className="test-button start">
                Start Test
              </button>
            ) : (
              <button onClick={stopTest} className="test-button stop">
                Stop Test
              </button>
            )}
          </div>

          {testActive && (
            <div className="test-stats">
              <div className="latency-display">
                <span className="stat-label">Latency:</span>
                <span className="stat-value">{latency}ms</span>
              </div>
              <div className="sticky-counters">
                <span className="stat-label">Sticky Buttons:</span>
                {Object.entries(stickyCounters).map(([button, count]) => (
                  <span key={button} className="sticky-count">
                    {button}: {count}
                  </span>
                ))}
              </div>
              <div className="button-states">
                {Object.entries(buttonStates).map(([button, pressed]) => (
                  <div key={button} className={`state-indicator ${pressed ? 'pressed' : 'released'}`}>
                    {button}
                  </div>
                ))}
              </div>
            </div>
          )}
        </section>
      </div>
    </PanelShell>
  );
}

export default ControllerChuckPanel;
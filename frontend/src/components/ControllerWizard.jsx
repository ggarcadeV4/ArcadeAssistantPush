import React, { useState, useCallback } from 'react';
import { chat } from '../services/aiClient';

const MOCK_DEVICES = [
  { id: 1, name: 'Xbox 360 Controller', vendor: 'Microsoft', connected: true },
  { id: 2, name: 'PS4 DualShock', vendor: 'Sony', connected: true },
  { id: 3, name: 'USB Gamepad', vendor: 'Generic', connected: false },
];

const EMULATORS = [
  'RetroArch',
  'MAME',
  'Dolphin',
  'PCSX2',
  'RPCS3',
  'Cemu',
  'Yuzu',
  'PPSSPP',
];

const MAPPING_SECTIONS = [
  {
    id: 'dpad',
    label: 'D-Pad',
    icon: '⬆',
    inputs: [
      { id: 'dpad_up', label: '⬆ Up', value: 'hat0up' },
      { id: 'dpad_down', label: '⬇ Down', value: 'hat0down' },
      { id: 'dpad_left', label: '⬅ Left', value: 'hat0left' },
      { id: 'dpad_right', label: '➡ Right', value: 'hat0right' },
    ],
  },
  {
    id: 'left_stick',
    label: 'Left Stick',
    icon: '🕹',
    inputs: [
      { id: 'lstick_up', label: 'Up', value: 'axis0-' },
      { id: 'lstick_down', label: 'Down', value: 'axis0+' },
      { id: 'lstick_left', label: 'Left', value: 'axis1-' },
      { id: 'lstick_right', label: 'Right', value: 'axis1+' },
      { id: 'lstick_press', label: 'Press (L3)', value: 'btn10' },
    ],
  },
  {
    id: 'right_stick',
    label: 'Right Stick',
    icon: '🕹',
    inputs: [
      { id: 'rstick_up', label: 'Up', value: 'axis2-' },
      { id: 'rstick_down', label: 'Down', value: 'axis2+' },
      { id: 'rstick_left', label: 'Left', value: 'axis3-' },
      { id: 'rstick_right', label: 'Right', value: 'axis3+' },
      { id: 'rstick_press', label: 'Press (R3)', value: 'btn11' },
    ],
  },
  {
    id: 'face_buttons',
    label: 'Face Buttons',
    icon: '🔴',
    inputs: [
      { id: 'btn_a', label: 'A / Cross', value: 'btn0' },
      { id: 'btn_b', label: 'B / Circle', value: 'btn1' },
      { id: 'btn_x', label: 'X / Square', value: 'btn2' },
      { id: 'btn_y', label: 'Y / Triangle', value: 'btn3' },
    ],
  },
  {
    id: 'shoulders',
    label: 'Shoulder & Triggers',
    icon: '🎮',
    inputs: [
      { id: 'lb', label: 'LB / L1', value: 'btn4' },
      { id: 'rb', label: 'RB / R1', value: 'btn5' },
      { id: 'lt', label: 'LT / L2', value: 'axis4' },
      { id: 'rt', label: 'RT / R2', value: 'axis5' },
    ],
  },
  {
    id: 'misc',
    label: 'Misc Buttons',
    icon: '⚙',
    inputs: [
      { id: 'start', label: 'Start', value: 'btn9' },
      { id: 'select', label: 'Select / Back', value: 'btn8' },
      { id: 'home', label: 'Home / Guide', value: 'btn12' },
    ],
  },
];

export default function ControllerWizard() {
  const [selectedDevice, setSelectedDevice] = useState(null);
  const [selectedPlayer, setSelectedPlayer] = useState(1);
  const [selectedEmulator, setSelectedEmulator] = useState('RetroArch');
  const [expandedSections, setExpandedSections] = useState({});
  const [highlightedInput, setHighlightedInput] = useState(null);
  const [chatOpen, setChatOpen] = useState(false);
  const [chatMessages, setChatMessages] = useState([
    {
      type: 'assistant',
      content: "Hi! I'm Chuck, your controller wizard. Select a device from the left to get started, and I'll help you configure every button!",
    },
  ]);
  const [chatInput, setChatInput] = useState('');

  const toggleSection = useCallback((sectionId) => {
    setExpandedSections(prev => ({
      ...prev,
      [sectionId]: !prev[sectionId],
    }));
  }, []);

  const handleSendMessage = useCallback(async (message) => {
    setChatMessages(prev => [...prev, { type: 'user', content: message }]);

    try {
      const response = await chat({
        provider: 'claude',
        messages: [
          {
            role: 'system',
            content: 'You are Chuck, a controller configuration expert. Help users map their controller buttons to emulators. Be concise and helpful.',
          },
          { role: 'user', content: message },
        ],
        metadata: { panel: 'controller-wizard', action: 'mapping_help' },
        scope: 'state',
        deviceId: 'demo_001',
      });

      const reply = response?.message?.content || '[No response]';
      setChatMessages(prev => [...prev, { type: 'assistant', content: reply }]);
    } catch (error) {
      const fallbacks = [
        "Make sure your controller is properly connected and recognized by your system.",
        "Try testing each button individually to ensure they're registering correctly.",
        "RetroArch usually auto-detects controllers, but manual mapping gives you more control.",
        "Remember to save your profile after mapping so you can reuse it later!",
      ];
      const fallbackMessage = fallbacks[Math.floor(Math.random() * fallbacks.length)];
      setChatMessages(prev => [...prev, { type: 'assistant', content: fallbackMessage }]);
    }
  }, []);

  const deviceName = selectedDevice ? MOCK_DEVICES.find(d => d.id === selectedDevice)?.name : '';
  const headerTitle = selectedDevice
    ? `${deviceName} – ${selectedEmulator} – Player ${selectedPlayer}`
    : 'Select a device to begin';

  return (
    <div className="console-wizard-container">
      {/* Left Module: Device Selection & Configuration */}
      <div className="console-wizard-left">
        {/* Connected Devices */}
        <div className="wizard-section">
          <h2 className="wizard-section-header primary-header">Connected Devices</h2>
          <div className="device-list">
            {MOCK_DEVICES.map(device => (
              <div
                key={device.id}
                className={`device-item ${selectedDevice === device.id ? 'active' : ''} ${!device.connected ? 'disconnected' : ''}`}
                onClick={() => device.connected && setSelectedDevice(device.id)}
              >
                <div className="device-icon">🎮</div>
                <div className="device-info">
                  <div className="device-name">{device.name}</div>
                  <div className="device-vendor">{device.vendor}</div>
                </div>
                {device.connected && (
                  <div className="device-status">✓</div>
                )}
              </div>
            ))}
          </div>
        </div>

        {/* Emulator Selector */}
        <div className="wizard-section">
          <h3 className="wizard-subsection-header">Emulator</h3>
          <select
            className="wizard-select"
            value={selectedEmulator}
            onChange={(e) => setSelectedEmulator(e.target.value)}
          >
            {EMULATORS.map(emu => (
              <option key={emu} value={emu}>{emu}</option>
            ))}
          </select>
        </div>

        {/* Player Selector */}
        <div className="wizard-section">
          <h3 className="wizard-subsection-header">Player</h3>
          <div className="player-selector-grid">
            {[1, 2, 3, 4].map(num => (
              <button
                key={num}
                className={`player-btn ${selectedPlayer === num ? 'active' : ''}`}
                onClick={() => setSelectedPlayer(num)}
              >
                P{num}
              </button>
            ))}
          </div>
        </div>

        {/* Placeholder Zone */}
        {!selectedDevice && (
          <div className="wizard-placeholder">
            <div className="placeholder-icon">🎮</div>
            <div className="placeholder-text">Select a device to begin mapping</div>
          </div>
        )}

        {selectedDevice && (
          <div className="controller-silhouette">
            <svg viewBox="0 0 200 120" className="silhouette-svg">
              {/* Controller body */}
              <ellipse cx="100" cy="60" rx="80" ry="50" fill="rgba(0, 229, 255, 0.1)" stroke="#00e5ff" strokeWidth="2" />

              {/* D-Pad */}
              <g className={highlightedInput?.startsWith('dpad') ? 'highlighted' : ''}>
                <rect x="40" y="50" width="20" height="6" fill="rgba(200, 255, 0, 0.3)" stroke="#c8ff00" />
                <rect x="47" y="43" width="6" height="20" fill="rgba(200, 255, 0, 0.3)" stroke="#c8ff00" />
              </g>

              {/* Face buttons */}
              <g className={highlightedInput?.startsWith('btn_') ? 'highlighted' : ''}>
                <circle cx="150" cy="45" r="6" fill="rgba(200, 255, 0, 0.3)" stroke="#c8ff00" />
                <circle cx="165" cy="55" r="6" fill="rgba(200, 255, 0, 0.3)" stroke="#c8ff00" />
                <circle cx="150" cy="65" r="6" fill="rgba(200, 255, 0, 0.3)" stroke="#c8ff00" />
                <circle cx="135" cy="55" r="6" fill="rgba(200, 255, 0, 0.3)" stroke="#c8ff00" />
              </g>

              {/* Left stick */}
              <circle
                cx="75"
                cy="75"
                r="10"
                fill="rgba(0, 229, 255, 0.2)"
                stroke="#00e5ff"
                className={highlightedInput?.startsWith('lstick') ? 'highlighted' : ''}
              />

              {/* Right stick */}
              <circle
                cx="125"
                cy="85"
                r="10"
                fill="rgba(0, 229, 255, 0.2)"
                stroke="#00e5ff"
                className={highlightedInput?.startsWith('rstick') ? 'highlighted' : ''}
              />
            </svg>
          </div>
        )}
      </div>

      {/* Right Module: Mapping Details */}
      <div className="console-wizard-right">
        <div className="wizard-right-header">
          <h2>{headerTitle}</h2>
        </div>

        {!selectedDevice && (
          <div className="wizard-empty-state">
            <p>Select a connected device from the left panel to configure its button mappings.</p>
          </div>
        )}

        {selectedDevice && (
          <div className="mapping-sections">
            {MAPPING_SECTIONS.map(section => (
              <div key={section.id} className="mapping-section">
                <button
                  className="section-toggle"
                  onClick={() => toggleSection(section.id)}
                >
                  <span className="section-icon">{section.icon}</span>
                  <span className="section-label">{section.label}</span>
                  <span className="section-arrow">{expandedSections[section.id] ? '▼' : '▶'}</span>
                </button>

                {expandedSections[section.id] && (
                  <div className="mapping-inputs">
                    {section.inputs.map(input => (
                      <div
                        key={input.id}
                        className={`mapping-row ${highlightedInput === input.id ? 'highlighted' : ''}`}
                        onMouseEnter={() => setHighlightedInput(input.id)}
                        onMouseLeave={() => setHighlightedInput(null)}
                      >
                        <span className="input-label">{input.label}</span>
                        <span className="input-value">{input.value}</span>
                      </div>
                    ))}
                  </div>
                )}
              </div>
            ))}
          </div>
        )}

        {/* Action Buttons */}
        <div className="wizard-actions">
          <div className="action-row">
            <button className="wizard-action-btn primary">Scan Devices</button>
            <button className="wizard-action-btn">Load Profile</button>
            <button className="wizard-action-btn">Save Profile</button>
          </div>
          <div className="action-row">
            <button className="wizard-action-btn">Copy to All Players</button>
            <button className="wizard-action-btn">Validate Mapping</button>
          </div>
          <div className="action-row">
            <button className="wizard-action-btn warning">Dry Run</button>
            <button className="wizard-action-btn success">Apply Changes</button>
          </div>
          <div className="action-row">
            <button className="wizard-action-btn">Export</button>
            <button className="wizard-action-btn">Import</button>
            <button className="wizard-action-btn danger">Reset</button>
          </div>
        </div>
      </div>

      {/* Chuck AI Chat Sidebar */}
      {chatOpen && (
        <div className="wizard-chat-sidebar">
          <div className="wizard-chat-header">
            <img src="/chuck-avatar.jpeg" alt="Chuck" className="wizard-chat-avatar" />
            <h4>Chuck - Controller Expert</h4>
            <button
              className="wizard-close-btn"
              onClick={() => setChatOpen(false)}
              aria-label="Close chat"
            >
              ×
            </button>
          </div>

          <div className="wizard-chat-history">
            {chatMessages.map((message, index) => (
              <div
                key={index}
                className={`wizard-message ${message.type === 'assistant' ? 'chuck-message' : 'user-message'}`}
              >
                {message.type === 'assistant' && (
                  <img src="/chuck-avatar.jpeg" alt="Chuck" className="message-avatar" />
                )}
                <div className="message-content">{message.content}</div>
              </div>
            ))}
          </div>

          <div className="wizard-chat-input-area">
            <input
              type="text"
              className="wizard-chat-input"
              placeholder="Ask Chuck for help..."
              value={chatInput}
              onChange={(e) => setChatInput(e.target.value)}
              onKeyDown={(e) => {
                if (e.key === 'Enter' && chatInput.trim()) {
                  handleSendMessage(chatInput.trim());
                  setChatInput('');
                }
              }}
            />
            <button
              className="wizard-icon-btn"
              onClick={() => {/* TODO: Voice input */}}
              title="Voice input"
            >
              <img src="/chuck-mic.png" alt="Mic" className="mic-icon" />
            </button>
            <button
              className="wizard-send-btn"
              onClick={() => {
                if (chatInput.trim()) {
                  handleSendMessage(chatInput.trim());
                  setChatInput('');
                }
              }}
            >
              ➤
            </button>
          </div>
        </div>
      )}

      {/* Chat toggle button */}
      <button
        className="wizard-chat-toggle"
        onClick={() => setChatOpen(!chatOpen)}
        title={chatOpen ? 'Close Chuck Assistant' : 'Open Chuck Assistant'}
      >
        {chatOpen ? '✕' : '💬'}
      </button>
    </div>
  );
}
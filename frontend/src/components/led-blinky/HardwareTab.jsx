/**
 * HardwareTab.jsx
 * ─────────────────────────────────────────────────────────────
 * Extracted from LEDBlinkyPanel.jsx (L4014–4463)
 *
 * Renders the "Hardware" tab:
 *   • WebSocket connection panel (connect / disconnect)
 *   • Connection log
 *   • LED Engine diagnostics
 *   • Detected LED Devices list
 *   • Channel Test controls
 *   • Hardware Test buttons (All On / Off, Chase, Rainbow)
 *
 * All state and callbacks received via props.
 * ─────────────────────────────────────────────────────────────
 */

import React from 'react'
import ComingSoonTag from './ComingSoonTag'

const HardwareTab = ({
    // Connection
    connectionStatus,
    toggleWebSocketConnection,
    isRefreshingStatus,
    gatewaySocketUrl,
    hardwareStatus,
    // Refresh
    refreshHardwareStatus,
    // Connection log
    connectionLog,
    // Engine diagnostics
    engineDiagnostics,
    simulationMode,
    queueDepth,
    pendingCommands,
    wsConnectionCount,
    activePatternName,
    registryMessage,
    engineEvents,
    formatTimestampValue,
    // Devices
    connectedDevices,
    // Channel test
    registryDevices,
    channelTestDevice,
    setChannelTestDevice,
    channelTestChannel,
    setChannelTestChannel,
    handleChannelTest,
    isTestingChannel,
    channelTestResult,
    // Hardware test
    triggerHardwareTest,
    ComingSoonTagOverride
}) => {
    const Tag = ComingSoonTagOverride || ComingSoonTag

    return (
        <div style={{ padding: '24px', overflowY: 'auto' }}>
            <div style={{
                padding: '24px',
                background: '#000000',
                borderRadius: '12px',
                marginBottom: '20px',
                border: '1px solid #7c3aed'
            }}>
                {/* Section Title */}
                <div style={{
                    fontSize: '18px',
                    fontWeight: '700',
                    color: '#9333ea',
                    marginBottom: '20px',
                    display: 'flex',
                    alignItems: 'center',
                    gap: '10px'
                }}>
                    <span>🔧</span>
                    <span>Hardware Connection</span>
                </div>

                {/* ─── Connection Status Card ─── */}
                <div style={{
                    background: '#000000',
                    border: '1px solid #9333ea',
                    borderRadius: '12px',
                    padding: '20px',
                    marginBottom: '20px'
                }}>
                    <div style={{
                        display: 'flex',
                        alignItems: 'center',
                        justifyContent: 'space-between',
                        marginBottom: '16px'
                    }}>
                        <div style={{ display: 'flex', alignItems: 'center', gap: '10px' }}>
                            <div style={{
                                width: '8px',
                                height: '8px',
                                borderRadius: '50%',
                                background: connectionStatus === 'connected' ? '#9333ea' : '#ef4444'
                            }} />
                            <span>{connectionStatus === 'connected' ? 'Connected' : 'Disconnected'}</span>
                        </div>
                        <button
                            onClick={toggleWebSocketConnection}
                            disabled={isRefreshingStatus}
                            title={isRefreshingStatus ? 'Refreshing hardware status...' : undefined}
                            style={{
                                background: connectionStatus === 'connected' ? '#ef4444' : '#10b981',
                                border: 'none',
                                color: '#000000',
                                padding: '8px 16px',
                                borderRadius: '6px',
                                cursor: isRefreshingStatus ? 'not-allowed' : 'pointer',
                                fontSize: '13px',
                                fontWeight: '600',
                                opacity: isRefreshingStatus ? 0.6 : 1
                            }}
                        >
                            {connectionStatus === 'connected' ? 'Disconnect' : 'Connect'}
                        </button>
                    </div>

                    <div style={{ marginBottom: '10px' }}>
                        <label style={{ display: 'block', marginBottom: '6px', fontSize: '13px', color: '#d1d5db' }}>Gateway Endpoint</label>
                        <div style={{
                            width: '100%',
                            padding: '10px 14px',
                            background: '#0a0a0a',
                            border: '1px solid #7c3aed',
                            borderRadius: '6px',
                            color: '#ffffff',
                            fontSize: '13px',
                            fontFamily: 'monospace'
                        }}>
                            {gatewaySocketUrl}
                        </div>
                    </div>

                    <div style={{ fontSize: '12px', color: '#6b7280', marginTop: '10px' }}>
                        <div>Connections now route through the gateway endpoint (/api/local/led/ws) so headers stay intact.</div>
                        {hardwareStatus?.ws?.target ? (
                            <div>Hardware proxy target: <span style={{ color: '#d1d5db' }}>{hardwareStatus.ws.target}</span></div>
                        ) : (
                            <div>The gateway is currently running in mock mode (no hardware target configured).</div>
                        )}
                        {hardwareStatus?.updated_at && (
                            <div>Last updated: {new Date(hardwareStatus.updated_at).toLocaleTimeString()}</div>
                        )}
                    </div>
                </div>

                {/* ─── Connection Log ─── */}
                <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', marginBottom: '8px' }}>
                    <span style={{ color: '#9ca3af', fontSize: '13px' }}>Connection Log</span>
                    <button
                        onClick={refreshHardwareStatus}
                        disabled={isRefreshingStatus}
                        style={{
                            padding: '6px 12px',
                            borderRadius: '6px',
                            border: '1px solid #7c3aed',
                            background: '#0a0a0a',
                            color: '#e5e7eb',
                            fontSize: '12px',
                            cursor: isRefreshingStatus ? 'not-allowed' : 'pointer',
                            opacity: isRefreshingStatus ? 0.6 : 1
                        }}
                    >
                        Refresh
                    </button>
                </div>

                <div style={{
                    background: '#000000',
                    border: '1px solid #7c3aed',
                    borderRadius: '8px',
                    padding: '16px',
                    fontFamily: 'monospace',
                    fontSize: '12px',
                    maxHeight: '200px',
                    overflowY: 'auto',
                    marginBottom: '20px'
                }}>
                    {connectionLog.length > 0 ? (
                        connectionLog.map((entry, index) => (
                            <div key={index} style={{
                                color: entry.type === 'success' ? '#10b981' : entry.type === 'error' ? '#ef4444' : entry.type === 'warning' ? '#f59e0b' : '#9333ea',
                                marginBottom: '3px'
                            }}>
                                [{entry.timestamp}] {entry.message}
                            </div>
                        ))
                    ) : (
                        <div style={{ color: '#6b7280' }}>Connection log will appear here...</div>
                    )}
                </div>

                {/* ─── LED Engine Status ─── */}
                <div style={{
                    padding: '16px',
                    borderRadius: '8px',
                    border: '1px solid #1f2937',
                    background: '#050505',
                    marginBottom: '20px'
                }}>
                    <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', marginBottom: '12px' }}>
                        <span style={{ color: '#9ca3af', fontSize: '13px' }}>LED Engine Status</span>
                        <button
                            onClick={refreshHardwareStatus}
                            disabled={isRefreshingStatus}
                            style={{
                                padding: '6px 12px',
                                borderRadius: '6px',
                                border: '1px solid #7c3aed',
                                background: '#0a0a0a',
                                color: '#e5e7eb',
                                fontSize: '12px',
                                cursor: isRefreshingStatus ? 'not-allowed' : 'pointer',
                                opacity: isRefreshingStatus ? 0.6 : 1
                            }}
                        >
                            Refresh
                        </button>
                    </div>
                    {engineDiagnostics ? (
                        <>
                            <div style={{
                                display: 'grid',
                                gridTemplateColumns: 'repeat(auto-fit, minmax(180px, 1fr))',
                                gap: '12px',
                                marginBottom: '12px'
                            }}>
                                <div style={{ color: '#d1d5db', fontSize: '13px' }}>
                                    <div style={{ color: '#9ca3af', fontSize: '11px' }}>Loop</div>
                                    <div>{engineDiagnostics.running ? 'Running' : 'Stopped'}</div>
                                </div>
                                <div style={{ color: '#d1d5db', fontSize: '13px' }}>
                                    <div style={{ color: '#9ca3af', fontSize: '11px' }}>Mode</div>
                                    <div>{simulationMode ? 'Simulation' : 'Hardware'}</div>
                                </div>
                                <div style={{ color: '#d1d5db', fontSize: '13px' }}>
                                    <div style={{ color: '#9ca3af', fontSize: '11px' }}>Tick Interval</div>
                                    <div>{engineDiagnostics.tick_ms ? `${(Number(engineDiagnostics.tick_ms) || 0).toFixed(2)} ms` : 'Unknown'}</div>
                                </div>
                                <div style={{ color: '#d1d5db', fontSize: '13px' }}>
                                    <div style={{ color: '#9ca3af', fontSize: '11px' }}>Last HID Write</div>
                                    <div>{formatTimestampValue(engineDiagnostics.last_hid_write)}</div>
                                </div>
                                <div style={{ color: '#d1d5db', fontSize: '13px' }}>
                                    <div style={{ color: '#9ca3af', fontSize: '11px' }}>Queue Depth</div>
                                    <div>{queueDepth}</div>
                                </div>
                                <div style={{ color: '#d1d5db', fontSize: '13px' }}>
                                    <div style={{ color: '#9ca3af', fontSize: '11px' }}>Pending Commands</div>
                                    <div>{pendingCommands}</div>
                                </div>
                                <div style={{ color: '#d1d5db', fontSize: '13px' }}>
                                    <div style={{ color: '#9ca3af', fontSize: '11px' }}>WS Connections</div>
                                    <div>{wsConnectionCount}</div>
                                </div>
                                <div style={{ color: '#d1d5db', fontSize: '13px' }}>
                                    <div style={{ color: '#9ca3af', fontSize: '11px' }}>Active Pattern</div>
                                    <div>{activePatternName || 'None'}</div>
                                </div>
                            </div>
                            <div style={{ color: '#9ca3af', fontSize: '12px', marginBottom: '12px' }}>
                                {registryMessage ||
                                    (simulationMode
                                        ? 'Simulation mode - no LED hardware detected.'
                                        : 'Hardware controllers detected.')}
                            </div>
                            {engineDiagnostics.last_error && (
                                <div style={{ color: '#f87171', fontSize: '12px', marginBottom: '12px' }}>
                                    Last error: {engineDiagnostics.last_error}
                                </div>
                            )}
                            <div>
                                <div style={{ color: '#9ca3af', fontSize: '12px', marginBottom: '6px' }}>Engine Log</div>
                                <div style={{
                                    background: '#000000',
                                    border: '1px solid #1f2937',
                                    borderRadius: '6px',
                                    padding: '10px',
                                    fontFamily: 'monospace',
                                    fontSize: '11px',
                                    maxHeight: '140px',
                                    overflowY: 'auto'
                                }}>
                                    {engineEvents.length > 0 ? engineEvents.map((entry, index) => (
                                        <div key={index} style={{ color: '#d1d5db', marginBottom: '4px' }}>
                                            [{formatTimestampValue(entry.timestamp)}] {entry.action}
                                            {entry.pattern && ` ${entry.pattern}`}
                                            {entry.message && ` - ${entry.message}`}
                                        </div>
                                    )) : (
                                        <div style={{ color: '#6b7280' }}>Engine activity will appear here.</div>
                                    )}
                                </div>
                            </div>
                        </>
                    ) : (
                        <div style={{ color: '#6b7280', fontSize: '12px' }}>Diagnostics will appear once the backend runtime reports its status.</div>
                    )}
                </div>

                {/* ─── Detected LED Devices ─── */}
                <div style={{
                    padding: '16px',
                    borderRadius: '8px',
                    border: '1px solid #1f2937',
                    background: '#050505',
                    marginBottom: '20px'
                }}>
                    <div style={{ fontSize: '16px', fontWeight: '700', color: '#9333ea', marginBottom: '12px' }}>
                        Detected LED Devices
                    </div>
                    {connectedDevices.length > 0 ? (
                        <div style={{ display: 'flex', flexDirection: 'column', gap: '10px' }}>
                            {connectedDevices.map((device, index) => (
                                <div key={device.device_id || `active-device-${index}`} style={{
                                    border: '1px solid #1f2937',
                                    borderRadius: '6px',
                                    padding: '10px',
                                    background: '#000000'
                                }}>
                                    <div style={{ color: '#d1d5db', fontSize: '13px', marginBottom: '4px' }}>{device.device_id}</div>
                                    <div style={{ color: '#9ca3af', fontSize: '11px', display: 'flex', gap: '12px', flexWrap: 'wrap' }}>
                                        <span>Channels: {device.channels}</span>
                                        {device.vendor_id && device.product_id && <span>VID: {device.vendor_id} PID: {device.product_id}</span>}
                                        {device.serial && <span>Serial: {device.serial}</span>}
                                        {device.product && <span>{device.product}</span>}
                                    </div>
                                </div>
                            ))}
                        </div>
                    ) : (
                        <div style={{ color: '#6b7280', fontSize: '12px' }}>
                            {simulationMode
                                ? 'Simulation mode - no LED hardware detected.'
                                : 'No LED hardware devices reported yet.'}
                        </div>
                    )}
                </div>

                {/* ─── Channel Test ─── */}
                <div style={{
                    padding: '16px',
                    borderRadius: '8px',
                    border: '1px solid #1f2937',
                    background: '#050505',
                    marginBottom: '20px'
                }}>
                    <div style={{ fontSize: '16px', fontWeight: '700', color: '#9333ea', marginBottom: '12px' }}>
                        Channel Test
                    </div>
                    <div style={{ color: '#9ca3af', fontSize: '12px', marginBottom: '12px' }}>
                        Flash a single LED channel even when running in simulation mode to verify the runtime.
                    </div>
                    {registryDevices.length > 0 ? (
                        <div style={{ display: 'flex', flexDirection: 'column', gap: '12px' }}>
                            <div>
                                <label style={{ display: 'block', color: '#d1d5db', fontSize: '13px', marginBottom: '4px' }}>Device</label>
                                <select
                                    value={channelTestDevice}
                                    onChange={(event) => setChannelTestDevice(event.target.value)}
                                    style={{
                                        width: '100%',
                                        padding: '10px',
                                        borderRadius: '6px',
                                        border: '1px solid #7c3aed',
                                        background: '#000000',
                                        color: '#d1d5db',
                                        fontSize: '13px'
                                    }}
                                >
                                    {registryDevices.map((device, index) => (
                                        <option key={device.device_id || `device-${index}`} value={device.device_id}>
                                            {device.device_id} {device.simulation ? '(simulation)' : ''}
                                        </option>
                                    ))}
                                </select>
                            </div>
                            <div>
                                <label style={{ display: 'block', color: '#d1d5db', fontSize: '13px', marginBottom: '4px' }}>Channel (0-31)</label>
                                <input
                                    type="number"
                                    min="0"
                                    max="31"
                                    value={channelTestChannel}
                                    onChange={(event) => setChannelTestChannel(event.target.value)}
                                    style={{
                                        width: '100%',
                                        padding: '10px',
                                        borderRadius: '6px',
                                        border: '1px solid #7c3aed',
                                        background: '#000000',
                                        color: '#d1d5db',
                                        fontSize: '13px'
                                    }}
                                />
                            </div>
                            <button
                                onClick={handleChannelTest}
                                disabled={isTestingChannel}
                                style={{
                                    padding: '10px 14px',
                                    borderRadius: '6px',
                                    border: '1px solid #7c3aed',
                                    background: isTestingChannel ? '#4c1d95' : '#9333ea',
                                    color: '#ffffff',
                                    fontSize: '13px',
                                    fontWeight: '600',
                                    cursor: isTestingChannel ? 'not-allowed' : 'pointer',
                                    opacity: isTestingChannel ? 0.7 : 1
                                }}
                            >
                                {isTestingChannel ? 'Testing...' : 'Test Channel'}
                            </button>
                            {channelTestResult && (
                                <div style={{
                                    marginTop: '4px',
                                    fontSize: '12px',
                                    color: channelTestResult.status === 'error' ? '#f87171' : '#10b981'
                                }}>
                                    {channelTestResult.status === 'error'
                                        ? channelTestResult.message
                                        : `Channel ${channelTestResult.payload?.channel} acknowledged (${channelTestResult.payload?.mode})`}
                                </div>
                            )}
                        </div>
                    ) : (
                        <div style={{ color: '#6b7280', fontSize: '12px' }}>No devices available for channel diagnostics.</div>
                    )}
                </div>

                {/* ─── Hardware Test ─── */}
                <div style={{ marginBottom: '20px' }}>
                    <div style={{
                        fontSize: '16px',
                        fontWeight: '700',
                        color: '#9333ea',
                        marginBottom: '16px',
                        display: 'flex',
                        alignItems: 'center',
                        gap: '10px'
                    }}>
                        <span>🔥</span>
                        <span>Hardware Test</span>
                    </div>
                    <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: '10px' }}>
                        <button onClick={() => triggerHardwareTest('all_on', { durationMs: 1500, color: '#9333ea' })} style={{ padding: '12px', background: '#000000', border: '1px solid #7c3aed', color: '#d1d5db', borderRadius: '8px', cursor: 'pointer', fontSize: '13px', fontWeight: '600' }}>All LEDs On</button>
                        <button onClick={() => triggerHardwareTest('all_off')} style={{ padding: '12px', background: '#000000', border: '1px solid #7c3aed', color: '#d1d5db', borderRadius: '8px', cursor: 'pointer', fontSize: '13px', fontWeight: '600' }}>All LEDs Off</button>
                        <button
                            disabled
                            title="Chase diagnostics will be enabled once the backend LED pattern runner lands."
                            style={{ padding: '12px', background: '#000000', border: '1px solid #7c3aed', color: '#d1d5db', borderRadius: '8px', cursor: 'not-allowed', fontSize: '13px', fontWeight: '600', opacity: 0.5 }}
                        >
                            <div style={{ display: 'flex', flexDirection: 'column', gap: '4px', alignItems: 'center' }}>
                                <span>Chase Pattern</span>
                                <Tag />
                            </div>
                        </button>
                        <button
                            disabled
                            title="Rainbow test requires backend support; coming soon."
                            style={{ padding: '12px', background: '#000000', border: '1px solid #7c3aed', color: '#d1d5db', borderRadius: '8px', cursor: 'not-allowed', fontSize: '13px', fontWeight: '600', opacity: 0.5 }}
                        >
                            <div style={{ display: 'flex', flexDirection: 'column', gap: '4px', alignItems: 'center' }}>
                                <span>Rainbow Test</span>
                                <Tag />
                            </div>
                        </button>
                    </div>
                </div>
            </div>
        </div>
    )
}

export default HardwareTab

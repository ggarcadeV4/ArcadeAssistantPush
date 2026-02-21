/**
 * LEDLayoutTab.jsx
 * ─────────────────────────────────────────────────────────────
 * Extracted from LEDBlinkyPanel.jsx (L3734–4012)
 *
 * Renders the "LED Layout" tab:
 *   • Channel stats (target file, total mapped, unmapped, unknown)
 *   • Calibration session controls (start / flash / stop)
 *   • Wiring map table
 *   • Channel selection form (logical button, device ID, channel #)
 *   • Preview / Apply / Delete wiring actions
 *   • Channel preview diff display
 *
 * All state and callbacks received via props.
 * ─────────────────────────────────────────────────────────────
 */

import React from 'react'

const LEDLayoutTab = ({
    // Channel state
    channelState,
    isLoadingChannels,
    channelEntries,
    // Calibration
    calibrationToken,
    isStartingCalibration,
    isFlashingChannel,
    isStoppingCalibration,
    startCalibrationSession,
    flashSelectedChannel,
    stopCalibrationSession,
    // Channel selection
    channelSelection,
    channelOptions,
    handleSelectChannel,
    handleChannelFieldChange,
    // Channel actions
    isChannelPreviewing,
    isChannelApplying,
    isDeletingChannel,
    previewChannelUpdate,
    applyChannelUpdate,
    removeChannelMapping,
    // Preview
    channelPreview
}) => (
    <div style={{ padding: '24px', overflowY: 'auto' }}>
        <div style={{
            padding: '24px',
            background: '#000000',
            borderRadius: '12px',
            marginBottom: '20px',
            border: '1px solid #7c3aed'
        }}>
            {/* Header */}
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
                <span>LED Layout &amp; Calibration</span>
            </div>

            {/* Stats grid */}
            <div style={{
                display: 'grid',
                gridTemplateColumns: 'repeat(auto-fit, minmax(200px, 1fr))',
                gap: '12px',
                fontSize: '12px',
                color: '#d1d5db',
                marginBottom: '16px'
            }}>
                <div>Target file: <code style={{ color: '#a78bfa' }}>{channelState.target_file || 'configs/ledblinky/led_channels.json'}</code></div>
                <div>Total mapped: <strong>{channelState.total_channels ?? 0}</strong></div>
                <div>Unmapped buttons: <strong>{Array.isArray(channelState.unmapped) ? channelState.unmapped.length : 0}</strong></div>
                <div>Unknown entries: <strong>{Array.isArray(channelState.unknown_logical) ? channelState.unknown_logical.length : 0}</strong></div>
            </div>

            {/* Calibration controls */}
            <div style={{ display: 'flex', gap: '10px', flexWrap: 'wrap', marginBottom: '16px' }}>
                <button
                    onClick={startCalibrationSession}
                    disabled={isStartingCalibration}
                    style={{
                        padding: '12px 18px',
                        borderRadius: '8px',
                        border: '1px solid #10b981',
                        background: '#051b16',
                        color: '#10b981',
                        fontWeight: '600',
                        cursor: isStartingCalibration ? 'not-allowed' : 'pointer',
                        opacity: isStartingCalibration ? 0.6 : 1
                    }}
                >
                    {isStartingCalibration ? 'Starting...' : 'Start Calibration'}
                </button>
                <button
                    onClick={flashSelectedChannel}
                    disabled={!calibrationToken || !channelSelection.logicalButton || isFlashingChannel}
                    style={{
                        padding: '12px 18px',
                        borderRadius: '8px',
                        border: '1px solid #9333ea',
                        background: '#111111',
                        color: '#d1d5db',
                        fontWeight: '600',
                        cursor: (!calibrationToken || isFlashingChannel) ? 'not-allowed' : 'pointer',
                        opacity: (!calibrationToken || isFlashingChannel) ? 0.5 : 1
                    }}
                >
                    {isFlashingChannel ? 'Flashing...' : 'Flash Selected'}
                </button>
                <button
                    onClick={() => stopCalibrationSession()}
                    disabled={!calibrationToken || isStoppingCalibration}
                    style={{
                        padding: '12px 18px',
                        borderRadius: '8px',
                        border: '1px solid #ef4444',
                        background: '#2c0505',
                        color: '#fca5a5',
                        fontWeight: '600',
                        cursor: !calibrationToken || isStoppingCalibration ? 'not-allowed' : 'pointer',
                        opacity: !calibrationToken || isStoppingCalibration ? 0.5 : 1
                    }}
                >
                    {isStoppingCalibration ? 'Stopping...' : 'Stop Calibration'}
                </button>
            </div>

            {/* Token display */}
            <div style={{ fontSize: '12px', color: '#9ca3af', marginBottom: '16px' }}>
                {calibrationToken
                    ? <>Active token: <code style={{ color: '#a78bfa' }}>{calibrationToken}</code></>
                    : 'Calibration mode inactive.'}
            </div>

            {/* Wiring map */}
            {isLoadingChannels ? (
                <div style={{ color: '#9ca3af', fontSize: '13px', marginBottom: '16px' }}>Loading wiring map...</div>
            ) : (
                <div style={{
                    background: '#050505',
                    border: '1px solid #1f2937',
                    borderRadius: '8px',
                    padding: '12px',
                    marginBottom: '16px',
                    maxHeight: '200px',
                    overflowY: 'auto',
                    fontSize: '12px'
                }}>
                    {channelEntries.length ? channelEntries.map(([logicalButton, entry]) => {
                        const mapping = entry || {}
                        const isMissing = Array.isArray(channelState.unmapped) && channelState.unmapped.includes(logicalButton)
                        const isUnknown = Array.isArray(channelState.unknown_logical) && channelState.unknown_logical.includes(logicalButton)
                        const deviceId = mapping.device_id || mapping.deviceId || '—'
                        const channelValue = mapping.channel || mapping.channel_index || '—'
                        const color = isMissing ? '#f59e0b' : isUnknown ? '#ef4444' : '#d1d5db'
                        return (
                            <div key={logicalButton} style={{
                                display: 'flex',
                                justifyContent: 'space-between',
                                marginBottom: '4px',
                                color
                            }}>
                                <span>{logicalButton}</span>
                                <span style={{ fontFamily: 'monospace' }}>{deviceId} #{channelValue}</span>
                            </div>
                        )
                    }) : (
                        <div style={{ color: '#6b7280' }}>No LED channels stored yet. Run a calibration to seed the file.</div>
                    )}
                </div>
            )}

            {/* Channel selection form */}
            <div style={{
                display: 'grid',
                gridTemplateColumns: 'repeat(auto-fit, minmax(200px, 1fr))',
                gap: '12px',
                marginBottom: '16px'
            }}>
                <div>
                    <label style={{ fontSize: '12px', color: '#9ca3af', marginBottom: '6px', display: 'block' }}>Logical Button</label>
                    <select
                        value={channelSelection.logicalButton}
                        onChange={(e) => handleSelectChannel(e.target.value)}
                        style={{
                            width: '100%',
                            padding: '10px',
                            background: '#0a0a0a',
                            borderRadius: '8px',
                            border: '1px solid #7c3aed',
                            color: '#ffffff',
                            fontSize: '13px'
                        }}
                    >
                        <option value="">-- Select --</option>
                        {channelOptions.map((option) => (
                            <option key={option} value={option}>{option}</option>
                        ))}
                    </select>
                </div>
                <div>
                    <label style={{ fontSize: '12px', color: '#9ca3af', marginBottom: '6px', display: 'block' }}>Device ID</label>
                    <input
                        value={channelSelection.deviceId}
                        onChange={(e) => handleChannelFieldChange('deviceId', e.target.value)}
                        placeholder="e.g. 0x045e:0x028e"
                        style={{
                            width: '100%',
                            padding: '10px',
                            background: '#0a0a0a',
                            borderRadius: '8px',
                            border: '1px solid #7c3aed',
                            color: '#ffffff',
                            fontSize: '13px'
                        }}
                    />
                </div>
                <div>
                    <label style={{ fontSize: '12px', color: '#9ca3af', marginBottom: '6px', display: 'block' }}>Channel #</label>
                    <input
                        type="number"
                        min={1}
                        value={channelSelection.channel}
                        onChange={(e) => handleChannelFieldChange('channel', e.target.value)}
                        placeholder="1"
                        style={{
                            width: '100%',
                            padding: '10px',
                            background: '#0a0a0a',
                            borderRadius: '8px',
                            border: '1px solid #7c3aed',
                            color: '#ffffff',
                            fontSize: '13px'
                        }}
                    />
                </div>
            </div>

            {/* Action buttons */}
            <div style={{ display: 'flex', gap: '12px', flexWrap: 'wrap', marginBottom: '16px' }}>
                <button
                    onClick={previewChannelUpdate}
                    disabled={isChannelPreviewing || !channelSelection.logicalButton}
                    style={{
                        padding: '12px 18px',
                        background: '#111111',
                        borderRadius: '8px',
                        border: '1px solid #7c3aed',
                        color: '#d1d5db',
                        cursor: isChannelPreviewing ? 'not-allowed' : 'pointer',
                        opacity: isChannelPreviewing ? 0.6 : 1,
                        fontWeight: 600
                    }}
                >
                    {isChannelPreviewing ? 'Previewing...' : 'Preview Wiring Change'}
                </button>
                <button
                    onClick={applyChannelUpdate}
                    disabled={isChannelApplying || !channelSelection.logicalButton}
                    style={{
                        padding: '12px 18px',
                        background: '#9333ea',
                        borderRadius: '8px',
                        border: '1px solid #7c3aed',
                        color: '#ffffff',
                        cursor: isChannelApplying ? 'not-allowed' : 'pointer',
                        opacity: isChannelApplying ? 0.6 : 1,
                        fontWeight: 600
                    }}
                >
                    {isChannelApplying ? 'Applying...' : 'Apply Wiring + Backup'}
                </button>
                <button
                    onClick={removeChannelMapping}
                    disabled={isDeletingChannel || !channelSelection.logicalButton}
                    style={{
                        padding: '12px 18px',
                        background: '#2c0505',
                        borderRadius: '8px',
                        border: '1px solid #ef4444',
                        color: '#f87171',
                        cursor: isDeletingChannel ? 'not-allowed' : 'pointer',
                        opacity: isDeletingChannel ? 0.5 : 1,
                        fontWeight: 600
                    }}
                >
                    {isDeletingChannel ? 'Deleting...' : 'Delete Mapping'}
                </button>
            </div>

            {/* Channel preview */}
            {channelPreview && (
                <div style={{
                    background: '#050505',
                    border: '1px solid #1f2937',
                    borderRadius: '8px',
                    padding: '12px'
                }}>
                    <div style={{ fontSize: '13px', color: '#d1d5db', marginBottom: '6px' }}>
                        Target: <code style={{ color: '#a78bfa' }}>{channelPreview.target_file}</code>
                    </div>
                    <div style={{ fontSize: '12px', color: '#9ca3af', marginBottom: '8px', display: 'flex', gap: '12px', flexWrap: 'wrap' }}>
                        <span>Status: {channelPreview.has_changes ? 'Changes detected' : 'No diff'}</span>
                        <span>Total mapped: {channelPreview.total_channels}</span>
                        <span>Unmapped after preview: {Array.isArray(channelPreview.unmapped) ? channelPreview.unmapped.length : 0}</span>
                    </div>
                    <div style={{ fontSize: '12px', color: '#9ca3af', marginBottom: '6px' }}>Diff</div>
                    <pre style={{
                        background: '#000000',
                        borderRadius: '6px',
                        border: '1px solid #1f2937',
                        padding: '10px',
                        maxHeight: '140px',
                        overflowY: 'auto',
                        fontSize: '11px',
                        color: '#d1d5db'
                    }}>{channelPreview.diff}</pre>
                    {(Array.isArray(channelPreview.unmapped) && channelPreview.unmapped.length > 0) && (
                        <div style={{ fontSize: '12px', color: '#fbbf24', marginTop: '8px' }}>
                            Unmapped buttons: {channelPreview.unmapped.join(', ')}
                        </div>
                    )}
                    {(Array.isArray(channelPreview.unknown_logical) && channelPreview.unknown_logical.length > 0) && (
                        <div style={{ fontSize: '12px', color: '#f87171', marginTop: '4px' }}>
                            Unknown entries: {channelPreview.unknown_logical.join(', ')}
                        </div>
                    )}
                </div>
            )}
        </div>
    </div>
)

export default LEDLayoutTab

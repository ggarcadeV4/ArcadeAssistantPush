/**
 * RealtimeControlTab.jsx
 * ─────────────────────────────────────────────────────────────
 * Extracted from LEDBlinkyPanel.jsx (L4948–5396)
 *
 * Renders the "Real-time Control" tab:
 *   • Hardware Status card (connection, device, LED count, WebSocket)
 *   • Test Controls (test all LEDs, flash individual button)
 *   • Per-Control Color Grid (P1-P4 button color pickers)
 *   • Now Playing card (current game, active profile, apply button)
 *
 * All state and callbacks received via props.
 * ─────────────────────────────────────────────────────────────
 */

import React from 'react'

const RealtimeControlTab = ({
    // Hardware status
    connectedDevices,
    simulationMode,
    connectionStatus,
    channelState,
    demoLastError,
    setDemoLastError,
    // Refresh
    refreshHardwareStatus,
    isRefreshingStatus,
    // Test controls
    demoTestDuration,
    setDemoTestDuration,
    isTestingAllLEDs,
    setIsTestingAllLEDs,
    testAllLEDs,
    showToast,
    // Flash controls
    demoFlashPlayer,
    setDemoFlashPlayer,
    demoFlashButton,
    setDemoFlashButton,
    demoFlashColor,
    setDemoFlashColor,
    isFlashingDemo,
    setIsFlashingDemo,
    flashLEDCalibration,
    calibrationToken,
    testLED,
    // Color grid
    mappingForm,
    setMappingForm,
    buildButtonsFromForm,
    applyLEDProfile,
    // Now Playing
    selectedGame,
    selectedProfile,
    selectedGameProfileName,
    selectedProfileMeta,
    availableProfiles,
    setAvailableProfiles,
    listLEDProfiles,
    applyGameProfileBinding,
    buildFormFromButtons,
    getLEDProfile
}) => (
    <div style={{ padding: '24px', display: 'flex', flexDirection: 'column', gap: '24px' }}>

        {/* Block 1: Hardware Status Card */}
        <div style={{
            background: 'linear-gradient(135deg, #111, #0a0a0a)',
            border: '1px solid #9333ea',
            borderRadius: '12px',
            padding: '20px'
        }}>
            <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '16px' }}>
                <h3 style={{ color: '#9333ea', margin: 0, fontSize: '16px', fontWeight: '700' }}>
                    💻 Hardware Status
                </h3>
                <button
                    onClick={refreshHardwareStatus}
                    disabled={isRefreshingStatus}
                    style={{
                        background: isRefreshingStatus ? '#374151' : 'linear-gradient(135deg, #9333ea, #7c3aed)',
                        border: 'none',
                        borderRadius: '8px',
                        color: 'white',
                        padding: '8px 16px',
                        cursor: isRefreshingStatus ? 'not-allowed' : 'pointer',
                        fontSize: '13px',
                        fontWeight: '600'
                    }}
                >
                    {isRefreshingStatus ? '⏳ Refreshing...' : '🔄 Refresh Status'}
                </button>
            </div>
            <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(180px, 1fr))', gap: '12px' }}>
                <div style={{ background: '#0a0a0a', padding: '12px', borderRadius: '8px', border: '1px solid #374151' }}>
                    <div style={{ color: '#9ca3af', fontSize: '11px', marginBottom: '4px' }}>Connection</div>
                    <div style={{ color: connectedDevices.length > 0 ? '#10b981' : simulationMode ? '#f59e0b' : '#ef4444', fontWeight: '600' }}>
                        {connectedDevices.length > 0 ? '✅ Connected' : simulationMode ? '⚠️ Simulation' : '❌ Disconnected'}
                    </div>
                </div>
                <div style={{ background: '#0a0a0a', padding: '12px', borderRadius: '8px', border: '1px solid #374151' }}>
                    <div style={{ color: '#9ca3af', fontSize: '11px', marginBottom: '4px' }}>Device Type</div>
                    <div style={{ color: '#e5e7eb', fontWeight: '600' }}>
                        {connectedDevices[0]?.device_id || 'LED-Wiz (simulated)'}
                    </div>
                </div>
                <div style={{ background: '#0a0a0a', padding: '12px', borderRadius: '8px', border: '1px solid #374151' }}>
                    <div style={{ color: '#9ca3af', fontSize: '11px', marginBottom: '4px' }}>LED Count</div>
                    <div style={{ color: '#e5e7eb', fontWeight: '600' }}>
                        {channelState.total_channels || 32} channels
                    </div>
                </div>
                <div style={{ background: '#0a0a0a', padding: '12px', borderRadius: '8px', border: '1px solid #374151' }}>
                    <div style={{ color: '#9ca3af', fontSize: '11px', marginBottom: '4px' }}>WebSocket</div>
                    <div style={{ color: connectionStatus === 'connected' ? '#10b981' : '#9ca3af', fontWeight: '600' }}>
                        {connectionStatus === 'connected' ? '🔗 Live' : '⚡ Ready'}
                    </div>
                </div>
            </div>
            {demoLastError && (
                <div style={{ marginTop: '12px', padding: '8px 12px', background: 'rgba(239, 68, 68, 0.1)', border: '1px solid #ef4444', borderRadius: '6px', color: '#ef4444', fontSize: '12px' }}>
                    ⚠️ {demoLastError}
                </div>
            )}
        </div>

        {/* Block 2: Test Controls */}
        <div style={{
            background: 'linear-gradient(135deg, #111, #0a0a0a)',
            border: '1px solid #9333ea',
            borderRadius: '12px',
            padding: '20px'
        }}>
            <h3 style={{ color: '#9333ea', margin: '0 0 16px 0', fontSize: '16px', fontWeight: '700' }}>
                🔦 Test Controls
            </h3>

            {/* Test All LEDs */}
            <div style={{ display: 'flex', gap: '12px', alignItems: 'center', marginBottom: '16px', flexWrap: 'wrap' }}>
                <select
                    value={demoTestDuration}
                    onChange={(e) => setDemoTestDuration(Number(e.target.value))}
                    style={{
                        background: '#0a0a0a',
                        border: '1px solid #374151',
                        borderRadius: '6px',
                        color: '#e5e7eb',
                        padding: '8px 12px',
                        fontSize: '13px'
                    }}
                >
                    <option value={500}>500ms</option>
                    <option value={1000}>1 second</option>
                    <option value={2000}>2 seconds</option>
                    <option value={5000}>5 seconds</option>
                </select>
                <button
                    onClick={async () => {
                        setIsTestingAllLEDs(true)
                        setDemoLastError(null)
                        try {
                            await testAllLEDs({ durationMs: demoTestDuration })
                            showToast('All LEDs tested!', 'success')
                        } catch (err) {
                            setDemoLastError(err?.error || err?.message || 'Test failed')
                        } finally {
                            setIsTestingAllLEDs(false)
                        }
                    }}
                    disabled={isTestingAllLEDs}
                    style={{
                        background: isTestingAllLEDs ? '#374151' : 'linear-gradient(135deg, #10b981, #059669)',
                        border: 'none',
                        borderRadius: '8px',
                        color: 'white',
                        padding: '10px 20px',
                        cursor: isTestingAllLEDs ? 'not-allowed' : 'pointer',
                        fontWeight: '600',
                        fontSize: '14px'
                    }}
                >
                    {isTestingAllLEDs ? '⏳ Testing...' : '💡 Test All LEDs'}
                </button>
            </div>

            {/* Flash Selected Control */}
            <div style={{ display: 'flex', gap: '12px', alignItems: 'center', flexWrap: 'wrap' }}>
                <select
                    value={demoFlashPlayer}
                    onChange={(e) => setDemoFlashPlayer(e.target.value)}
                    style={{
                        background: '#0a0a0a',
                        border: '1px solid #374151',
                        borderRadius: '6px',
                        color: '#e5e7eb',
                        padding: '8px 12px',
                        fontSize: '13px'
                    }}
                >
                    {[1, 2, 3, 4].map(p => <option key={p} value={p}>Player {p}</option>)}
                </select>
                <select
                    value={demoFlashButton}
                    onChange={(e) => setDemoFlashButton(e.target.value)}
                    style={{
                        background: '#0a0a0a',
                        border: '1px solid #374151',
                        borderRadius: '6px',
                        color: '#e5e7eb',
                        padding: '8px 12px',
                        fontSize: '13px'
                    }}
                >
                    {[1, 2, 3, 4, 5, 6, 7, 8, 'start', 'coin'].map(b => (
                        <option key={b} value={b}>{typeof b === 'number' ? `Button ${b}` : b.charAt(0).toUpperCase() + b.slice(1)}</option>
                    ))}
                </select>
                <input
                    type="color"
                    value={demoFlashColor}
                    onChange={(e) => setDemoFlashColor(e.target.value)}
                    style={{
                        width: '44px',
                        height: '36px',
                        border: '2px solid #374151',
                        borderRadius: '6px',
                        cursor: 'pointer'
                    }}
                />
                <button
                    onClick={async () => {
                        setIsFlashingDemo(true)
                        setDemoLastError(null)
                        try {
                            const logicalButton = `p${demoFlashPlayer}.button${demoFlashButton}`
                            await flashLEDCalibration({
                                token: calibrationToken || 'demo',
                                logical_button: logicalButton,
                                color: demoFlashColor,
                                duration_ms: 500
                            })
                            showToast(`Flashed P${demoFlashPlayer} ${demoFlashButton}`, 'success')
                        } catch (err) {
                            try {
                                await testLED({ effect: 'solid', color: demoFlashColor, durationMs: 500 })
                            } catch (err2) {
                                setDemoLastError(err?.error || err?.message || 'Flash failed')
                            }
                        } finally {
                            setIsFlashingDemo(false)
                        }
                    }}
                    disabled={isFlashingDemo}
                    style={{
                        background: isFlashingDemo ? '#374151' : 'linear-gradient(135deg, #f59e0b, #d97706)',
                        border: 'none',
                        borderRadius: '8px',
                        color: 'white',
                        padding: '10px 20px',
                        cursor: isFlashingDemo ? 'not-allowed' : 'pointer',
                        fontWeight: '600',
                        fontSize: '14px'
                    }}
                >
                    {isFlashingDemo ? '⏳...' : '⚡ Flash'}
                </button>
            </div>
        </div>

        {/* Block 3: Per-Control Color Grid */}
        <div style={{
            background: 'linear-gradient(135deg, #111, #0a0a0a)',
            border: '1px solid #9333ea',
            borderRadius: '12px',
            padding: '20px'
        }}>
            <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '16px' }}>
                <h3 style={{ color: '#9333ea', margin: 0, fontSize: '16px', fontWeight: '700' }}>
                    🎨 Profile Color Grid
                </h3>
                <button
                    onClick={async () => {
                        setDemoLastError(null)
                        try {
                            const profile = {
                                profile_name: 'manual_profile',
                                scope: 'manual',
                                buttons: buildButtonsFromForm(mappingForm)
                            }
                            await applyLEDProfile(profile)
                            showToast('Colors applied to hardware!', 'success')
                        } catch (err) {
                            setDemoLastError(err?.error || err?.message || 'Apply failed')
                        }
                    }}
                    style={{
                        background: 'linear-gradient(135deg, #9333ea, #7c3aed)',
                        border: 'none',
                        borderRadius: '8px',
                        color: 'white',
                        padding: '8px 16px',
                        cursor: 'pointer',
                        fontWeight: '600',
                        fontSize: '13px'
                    }}
                >
                    ✅ Apply Colors
                </button>
            </div>
            <div style={{ color: '#9ca3af', fontSize: '12px', marginBottom: '16px' }}>
                Click any button to change its color. Changes affect the current profile, not hardware wiring.
            </div>

            {/* P1/P2 8-button layout */}
            <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: '24px', marginBottom: '20px' }}>
                {[1, 2].map(player => (
                    <div key={player} style={{ background: '#0a0a0a', borderRadius: '10px', padding: '16px', border: '1px solid #374151' }}>
                        <div style={{ color: '#c084fc', fontWeight: '700', marginBottom: '12px', fontSize: '14px' }}>
                            Player {player}
                        </div>
                        {/* Row 1: 1,2,3,7 */}
                        <div style={{ display: 'flex', gap: '8px', marginBottom: '8px' }}>
                            {[1, 2, 3, 7].map(btn => {
                                const formKey = `p${player}_button${btn}`
                                const color = mappingForm[formKey] || '#333'
                                return (
                                    <div key={btn} style={{ position: 'relative' }}>
                                        <input
                                            type="color"
                                            value={color}
                                            onChange={(e) => setMappingForm(prev => ({ ...prev, [formKey]: e.target.value }))}
                                            style={{
                                                width: '36px',
                                                height: '36px',
                                                border: '2px solid #7c3aed',
                                                borderRadius: '50%',
                                                cursor: 'pointer',
                                                background: color
                                            }}
                                            title={`P${player} B${btn}`}
                                        />
                                        <span style={{ position: 'absolute', bottom: '-14px', left: '50%', transform: 'translateX(-50%)', fontSize: '10px', color: '#9ca3af' }}>{btn}</span>
                                    </div>
                                )
                            })}
                        </div>
                        {/* Row 2: 4,5,6,8 */}
                        <div style={{ display: 'flex', gap: '8px', marginTop: '16px' }}>
                            {[4, 5, 6, 8].map(btn => {
                                const formKey = `p${player}_button${btn}`
                                const color = mappingForm[formKey] || '#333'
                                return (
                                    <div key={btn} style={{ position: 'relative' }}>
                                        <input
                                            type="color"
                                            value={color}
                                            onChange={(e) => setMappingForm(prev => ({ ...prev, [formKey]: e.target.value }))}
                                            style={{
                                                width: '36px',
                                                height: '36px',
                                                border: '2px solid #7c3aed',
                                                borderRadius: '50%',
                                                cursor: 'pointer',
                                                background: color
                                            }}
                                            title={`P${player} B${btn}`}
                                        />
                                        <span style={{ position: 'absolute', bottom: '-14px', left: '50%', transform: 'translateX(-50%)', fontSize: '10px', color: '#9ca3af' }}>{btn}</span>
                                    </div>
                                )
                            })}
                        </div>
                    </div>
                ))}
            </div>

            {/* P3/P4 4-button layout */}
            <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: '24px' }}>
                {[3, 4].map(player => (
                    <div key={player} style={{ background: '#0a0a0a', borderRadius: '10px', padding: '12px', border: '1px solid #374151' }}>
                        <div style={{ color: '#a855f7', fontWeight: '600', marginBottom: '8px', fontSize: '13px' }}>
                            Player {player}
                        </div>
                        <div style={{ display: 'flex', gap: '6px' }}>
                            {[1, 2, 3, 4].map(btn => {
                                const formKey = `p${player}_button${btn}`
                                const color = mappingForm[formKey] || '#333'
                                return (
                                    <input
                                        key={btn}
                                        type="color"
                                        value={color}
                                        onChange={(e) => setMappingForm(prev => ({ ...prev, [formKey]: e.target.value }))}
                                        style={{
                                            width: '28px',
                                            height: '28px',
                                            border: '2px solid #6b21a8',
                                            borderRadius: '50%',
                                            cursor: 'pointer',
                                            background: color
                                        }}
                                        title={`P${player} B${btn}`}
                                    />
                                )
                            })}
                        </div>
                    </div>
                ))}
            </div>
        </div>

        {/* Block 4: Now Playing / Per-Game Proof */}
        <div style={{
            background: 'linear-gradient(135deg, #111, #0a0a0a)',
            border: '1px solid #9333ea',
            borderRadius: '12px',
            padding: '20px'
        }}>
            <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '16px' }}>
                <h3 style={{ color: '#9333ea', margin: 0, fontSize: '16px', fontWeight: '700' }}>
                    🎮 Now Playing
                </h3>
                <button
                    onClick={async () => {
                        setDemoLastError(null)
                        try {
                            const profiles = await listLEDProfiles()
                            setAvailableProfiles(profiles?.profiles || [])
                            showToast(`Loaded ${profiles?.profiles?.length || 0} profiles`, 'success')
                        } catch (err) {
                            setDemoLastError(err?.error || err?.message || 'Failed to load profiles')
                        }
                    }}
                    style={{
                        background: '#374151',
                        border: 'none',
                        borderRadius: '6px',
                        color: '#e5e7eb',
                        padding: '6px 12px',
                        cursor: 'pointer',
                        fontSize: '12px'
                    }}
                >
                    🔄 Reload Profiles
                </button>
            </div>

            <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: '16px', marginBottom: '16px' }}>
                <div style={{ background: '#0a0a0a', padding: '16px', borderRadius: '8px', border: '1px solid #374151' }}>
                    <div style={{ color: '#9ca3af', fontSize: '11px', marginBottom: '6px' }}>Current Game</div>
                    <div style={{ color: '#e5e7eb', fontWeight: '600', fontSize: '15px' }}>
                        {selectedGame?.title || selectedProfile || 'No game selected'}
                    </div>
                </div>
                <div style={{ background: '#0a0a0a', padding: '16px', borderRadius: '8px', border: '1px solid #374151' }}>
                    <div style={{ color: '#9ca3af', fontSize: '11px', marginBottom: '6px' }}>Active Profile</div>
                    <div style={{ color: '#c084fc', fontWeight: '600', fontSize: '15px' }}>
                        {selectedGameProfileName || selectedProfileMeta?.profile_name || selectedProfile || 'Default'}
                    </div>
                </div>
            </div>

            <button
                onClick={async () => {
                    setDemoLastError(null)
                    try {
                        if (selectedGame && selectedGameProfileName) {
                            const result = await applyGameProfileBinding({
                                gameId: selectedGame.id || selectedGame.game_id,
                                profileName: selectedGameProfileName
                            })
                            if (result?.preview?.buttons) {
                                setMappingForm(buildFormFromButtons(result.preview.buttons))
                            }
                            showToast(`Applied ${selectedGameProfileName} profile!`, 'success')
                        } else if (selectedProfile) {
                            const profile = await getLEDProfile(selectedProfile)
                            if (profile?.buttons) {
                                setMappingForm(buildFormFromButtons(profile.buttons))
                            }
                            await applyLEDProfile(profile)
                            showToast(`Applied ${selectedProfile} profile!`, 'success')
                        } else {
                            setDemoLastError('Select a game or profile first')
                        }
                    } catch (err) {
                        setDemoLastError(err?.error || err?.message || 'Apply failed')
                    }
                }}
                style={{
                    background: 'linear-gradient(135deg, #9333ea, #7c3aed)',
                    border: 'none',
                    borderRadius: '8px',
                    color: 'white',
                    padding: '12px 24px',
                    cursor: 'pointer',
                    fontWeight: '600',
                    fontSize: '14px',
                    width: '100%'
                }}
            >
                🚀 Apply Profile to Hardware
            </button>
        </div>
    </div>
)

export default RealtimeControlTab

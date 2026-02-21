/**
 * CalibrationTab.jsx
 * ─────────────────────────────────────────────────────────────
 * Extracted from LEDBlinkyPanel.jsx (L4466–4576)
 *
 * Renders the "Calibration" tab:
 *   • Wiring Wizard component (left column)
 *   • Current LED Channel Mappings summary
 *   • Arcade Panel Preview with wizard click handler (right column)
 *
 * All state and callbacks received via props.
 * ─────────────────────────────────────────────────────────────
 */

import React from 'react'

const CalibrationTab = ({
    // Wiring Wizard
    WiringWizard,
    wizardState,
    setWizardState,
    cabinetPlayerCount,
    handleWizardMapButton,
    showToast,
    // Channel state
    channelState,
    // Arcade Panel Preview
    ArcadePanelPreview,
    mappingForm,
    currentActiveButtons,
    toggleLED
}) => (
    <div style={{
        padding: '24px',
        overflowY: 'auto',
        display: 'grid',
        gridTemplateColumns: '1fr 1fr',
        gap: '24px'
    }}>
        {/* Left: Wiring Wizard Controls */}
        <div>
            <WiringWizard
                wizardState={wizardState}
                onStateChange={setWizardState}
                numPlayers={cabinetPlayerCount}
                onMapButton={handleWizardMapButton}
                onComplete={() => {
                    setWizardState(prev => ({ ...prev, isActive: false }))
                    showToast('LED mappings saved successfully!', 'success')
                }}
                onCancel={() => {
                    setWizardState(prev => ({ ...prev, isActive: false }))
                    showToast('Calibration cancelled', 'info')
                }}
            />

            {/* Existing Channel Mappings Display */}
            <div style={{
                marginTop: '24px',
                padding: '20px',
                background: '#0f0f0f',
                borderRadius: '12px',
                border: '1px solid #7c3aed'
            }}>
                <div style={{
                    fontSize: '16px',
                    fontWeight: '700',
                    color: '#9333ea',
                    marginBottom: '12px',
                    display: 'flex',
                    alignItems: 'center',
                    gap: '8px'
                }}>
                    <span>📋</span>
                    <span>Current LED Channel Mappings</span>
                </div>
                <p style={{ color: '#9ca3af', fontSize: '13px' }}>
                    {Object.keys(channelState.channels || {}).length > 0
                        ? `${Object.keys(channelState.channels).length} button(s) mapped`
                        : 'No mappings configured. Use the wizard above to create mappings.'}
                </p>
            </div>
        </div>

        {/* Right: Arcade Panel Preview - MUST be visible in calibration mode */}
        <div>
            <div style={{
                padding: '20px',
                background: wizardState.isActive ? '#1a0a2e' : '#0f0f0f',
                borderRadius: '12px',
                border: wizardState.isActive ? '2px solid #10b981' : '1px solid #9333ea',
                transition: 'all 0.3s ease'
            }}>
                <div style={{
                    fontSize: '16px',
                    fontWeight: '700',
                    color: wizardState.isActive ? '#10b981' : '#9333ea',
                    marginBottom: '16px',
                    display: 'flex',
                    alignItems: 'center',
                    gap: '8px'
                }}>
                    <span>{wizardState.isActive ? '👆' : '🎮'}</span>
                    <span>{wizardState.isActive ? 'Click Button to Map' : 'Arcade Panel Preview'}</span>
                </div>

                {wizardState.isActive && (
                    <div style={{
                        marginBottom: '16px',
                        padding: '12px',
                        background: 'rgba(16, 185, 129, 0.15)',
                        borderRadius: '8px',
                        textAlign: 'center',
                        color: '#34d399',
                        fontSize: '14px',
                        fontWeight: '600'
                    }}>
                        👇 Click the button on this panel that matches the blinking LED
                    </div>
                )}

                <ArcadePanelPreview
                    mappingForm={mappingForm}
                    activeButtons={currentActiveButtons}
                    playerCount={cabinetPlayerCount}
                    showLabels={true}
                    onButtonClick={(player, button) => {
                        const buttonId = `p${player}.button${button}`
                        if (wizardState.isActive) {
                            handleWizardMapButton(buttonId)
                        } else {
                            toggleLED(player, button)
                        }
                    }}
                />
            </div>
        </div>
    </div>
)

export default CalibrationTab

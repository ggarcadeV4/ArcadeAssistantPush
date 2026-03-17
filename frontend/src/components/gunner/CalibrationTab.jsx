import React, { useState } from 'react'

/**
 * CalibrationTab — Light gun crosshair calibration wizard
 * Matches Stitch "Retro Shooter Gun Calibration" design
 */
export default function CalibrationTab() {
    const [activeGun, setActiveGun] = useState('1P')
    const [step, setStep] = useState(0)
    const [calibrating, setCalibrating] = useState(false)

    const STEPS = [
        'Point at the CENTER of the screen and pull the trigger',
        'Point at the TOP-LEFT corner and pull the trigger',
        'Point at the TOP-RIGHT corner and pull the trigger',
        'Point at the BOTTOM-LEFT corner and pull the trigger',
        'Point at the BOTTOM-RIGHT corner and pull the trigger',
    ]

    const handleStart = () => {
        console.warn(
            '[Gunner] CalibrationTab: Backend wiring pending. ' +
            'START CALIBRATION does not yet call the backend calibration ' +
            'endpoint. See gunner.py /calibrate/stream for the real path.'
        )
        setCalibrating(true)
        setStep(0)
    }

    const handleReset = () => {
        setCalibrating(false)
        setStep(0)
    }

    const handleTriggerPull = () => {
        if (step < STEPS.length - 1) {
            setStep(s => s + 1)
        } else {
            setCalibrating(false)
            setStep(0)
        }
    }

    return (
        <div className="gunner-calibration">
            {/* Gun Selector */}
            <div className="gunner-calibration__gun-select">
                {['1P', '2P'].map(gun => (
                    <button
                        key={gun}
                        className={`gunner-calibration__gun-btn${activeGun === gun ? ' gunner-calibration__gun-btn--active' : ''}`}
                        onClick={() => setActiveGun(gun)}
                    >
                        {gun} Gun
                    </button>
                ))}
            </div>

            {/* Crosshair Grid Area */}
            <div className="gunner-calibration__grid" onClick={calibrating ? handleTriggerPull : undefined}>
                {/* Corner markers */}
                <div className="gunner-calibration__corner gunner-calibration__corner--tl" />
                <div className="gunner-calibration__corner gunner-calibration__corner--tr" />
                <div className="gunner-calibration__corner gunner-calibration__corner--bl" />
                <div className="gunner-calibration__corner gunner-calibration__corner--br" />

                {/* Center crosshair */}
                <svg className="gunner-calibration__crosshair" viewBox="0 0 100 100" width="80" height="80">
                    <circle cx="50" cy="50" r="20" fill="none" stroke="var(--cyber-cyan)" strokeWidth="1.5" opacity="0.6" />
                    <circle cx="50" cy="50" r="3" fill="var(--cyber-cyan)" />
                    <line x1="50" y1="0" x2="50" y2="40" stroke="var(--cyber-cyan)" strokeWidth="1" opacity="0.5" />
                    <line x1="50" y1="60" x2="50" y2="100" stroke="var(--cyber-cyan)" strokeWidth="1" opacity="0.5" />
                    <line x1="0" y1="50" x2="40" y2="50" stroke="var(--cyber-cyan)" strokeWidth="1" opacity="0.5" />
                    <line x1="60" y1="50" x2="100" y2="50" stroke="var(--cyber-cyan)" strokeWidth="1" opacity="0.5" />
                </svg>

                {/* Step indicator */}
                {calibrating && (
                    <div className="gunner-calibration__step-text">
                        <span className="gunner-calibration__step-num">Step {step + 1}/{STEPS.length}</span>
                        <span className="gunner-calibration__step-instruction">{STEPS[step]}</span>
                    </div>
                )}

                {!calibrating && (
                    <div className="gunner-calibration__idle-text">
                        Click "Start Calibration" to begin
                    </div>
                )}
            </div>

            {/* Status Bar */}
            <div className="gunner-calibration__status">
                <span>Active Gun: <strong style={{ color: 'var(--cyber-cyan)' }}>{activeGun}</strong></span>
                <span>Status: <strong style={{ color: calibrating ? 'var(--cyber-yellow)' : 'var(--cyber-green)' }}>
                    {calibrating ? 'CALIBRATING' : 'READY'}
                </strong></span>
            </div>

            {/* Action Buttons */}
            <div className="gunner-calibration__actions">
                <button className="gunner-btn-action" onClick={handleStart} disabled={calibrating}>
                    Start Calibration
                </button>
                <button className="gunner-btn-action gunner-btn-action--secondary" onClick={handleReset}>
                    Reset
                </button>
            </div>
            <div style={{ marginTop: 10, color: 'var(--cyber-yellow)', fontSize: '0.9rem' }}>
                Calibration UI — backend wiring pending (post-duplication)
            </div>
        </div>
    )
}

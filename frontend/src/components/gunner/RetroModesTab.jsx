import React, { useState } from 'react'

const ENGINES = [
    {
        id: 'arcade', name: 'ARCADE CABINET', icon: '🕹️', active: true,
        latency: '1.2ms', refresh: '60Hz', protocol: 'RawInput',
        description: 'Direct buffer bypass enabled via RawInput for authentic arcade feel.'
    },
    {
        id: 'crt', name: 'CRT SIMULATION', icon: '📺',
        latency: '3.5ms', refresh: '60Hz', protocol: 'DirectInput',
        description: 'CRT shader emulation with scanlines, curvature, and phosphor bloom.'
    },
    {
        id: 'console', name: 'CONSOLE DIRECT', icon: '🎮',
        latency: '2.1ms', refresh: '60Hz', protocol: 'XInput',
        description: 'Console-style input mapping with aim assist and dead zone tuning.'
    },
    {
        id: 'custom', name: 'CUSTOM ENGINE', icon: '⚙️',
        latency: '—', refresh: '—', protocol: '—',
        description: 'Build your own input pipeline with custom parameters.'
    },
]

/**
 * RetroModesTab — Hardware emulation mode selector + CRT filter controls
 * Matches Stitch "Gunner: Retro Engine Selection" design
 */
export default function RetroModesTab() {
    const [selectedEngine, setSelectedEngine] = useState(ENGINES[0])
    const [filters, setFilters] = useState({
        scanlineIntensity: 70,
        curvature: 30,
        phosphorBloom: 45,
    })

    const handleFilterChange = (key, value) => {
        setFilters(prev => ({ ...prev, [key]: value }))
    }

    const handleApplyMode = () => {
        console.warn(
            '[Gunner] RetroModesTab: Apply Mode not yet wired ' +
            'to backend. See gunner.py retro mode registry for real path.'
        )
    }

    const handleOptimizeForFleet = () => {
        console.warn(
            '[Gunner] RetroModesTab: Optimize for Fleet not ' +
            'yet wired to Supabase fleet sync.'
        )
    }

    return (
        <div className="gunner-retro">
            {/* Engine Cards Row */}
            <div className="gunner-retro__engines">
                {ENGINES.map(engine => (
                    <button
                        key={engine.id}
                        className={`gunner-retro__engine-card${selectedEngine.id === engine.id ? ' gunner-retro__engine-card--selected' : ''}`}
                        onClick={() => setSelectedEngine(engine)}
                    >
                        <span className="gunner-retro__engine-icon">{engine.icon}</span>
                        <span className="gunner-retro__engine-name">{engine.name}</span>
                        {engine.active && <span className="gunner-retro__engine-active">ACTIVE</span>}
                    </button>
                ))}
            </div>

            {/* Details Area */}
            <div className="gunner-retro__details">
                {/* Mode Details Panel */}
                <div className="gunner-retro__mode-panel">
                    <h4 className="gunner-info-panel__title">MODE DETAILS PANEL</h4>
                    <div className="gunner-retro__detail-row">
                        <span>Latency Analysis:</span>
                        <span className="gunner-retro__detail-value">{selectedEngine.latency}</span>
                    </div>
                    <div className="gunner-retro__detail-row">
                        <span>Refresh Sync:</span>
                        <span className="gunner-retro__detail-value">{selectedEngine.refresh}</span>
                    </div>
                    <div className="gunner-retro__detail-row">
                        <span>Input Protocol:</span>
                        <span className="gunner-retro__detail-value gunner-retro__detail-value--protocol">{selectedEngine.protocol}</span>
                    </div>
                    <p className="gunner-retro__description">{selectedEngine.description}</p>
                </div>

                {/* CRT Filter Toggle */}
                <div className="gunner-retro__filter-panel">
                    <div className="gunner-retro__filter-preview">
                        <h4 className="gunner-info-panel__title">VISUAL OUTPUT PREVIEW</h4>
                        <div className="gunner-retro__preview-box">
                            <div className="gunner-retro__preview-scanlines"
                                style={{ opacity: filters.scanlineIntensity / 200 }} />
                            <div className="gunner-retro__preview-content">
                                <span className="gunner-retro__preview-text">PREVIEW</span>
                            </div>
                        </div>
                    </div>
                    <div className="gunner-retro__filter-controls">
                        <h4 className="gunner-info-panel__title">FILTER PARAMETERS</h4>
                        {[
                            { key: 'scanlineIntensity', label: 'Scanline Intensity' },
                            { key: 'curvature', label: 'Curvature' },
                            { key: 'phosphorBloom', label: 'Phosphor Bloom' },
                        ].map(({ key, label }) => (
                            <div key={key} className="gunner-retro__slider-row">
                                <label className="gunner-retro__slider-label">{label}</label>
                                <input
                                    type="range"
                                    min="0"
                                    max="100"
                                    value={filters[key]}
                                    onChange={e => handleFilterChange(key, Number(e.target.value))}
                                    className="gunner-retro__slider"
                                />
                                <span className="gunner-retro__slider-value">{filters[key]}%</span>
                            </div>
                        ))}
                    </div>
                </div>
            </div>

            {/* Action Buttons */}
            <div className="gunner-retro__actions">
                <button className="gunner-btn-action" onClick={handleApplyMode}>[Apply Mode]</button>
                <button className="gunner-btn-action gunner-btn-action--green" onClick={handleOptimizeForFleet}>[Optimize for Fleet]</button>
            </div>
            <div style={{ marginTop: 10, color: 'var(--cyber-yellow)', fontSize: '0.9rem' }}>
                Display mode application — backend wiring pending (post-duplication)
            </div>
        </div>
    )
}

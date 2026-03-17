import React, { useState } from 'react'

const DEFAULT_PROFILES = [
    { id: 'time-crisis', name: 'Time Crisis', lastPlayed: 'Today', icon: '🔫', active: true },
    { id: 'house-dead', name: 'House of the Dead', lastPlayed: 'Yesterday', icon: '🧟' },
    { id: 'duck-hunt', name: 'Duck Hunt', lastPlayed: 'Last Week', icon: '🦆' },
    { id: 'virtua-cop', name: 'Virtua Cop', lastPlayed: '2 Weeks Ago', icon: '👮' },
]

/**
 * ProfilesTab — Per-game gun profile management
 * Matches Stitch "Gunner Profiles Management" design
 */
export default function ProfilesTab() {
    const [selectedProfile, setSelectedProfile] = useState(DEFAULT_PROFILES[0])

    const handleSaveProfile = () => {
        console.warn(
            '[Gunner] ProfilesTab: Save Profile not yet wired ' +
            'to backend. See gunner.py /profile/save for the real path.'
        )
    }

    const handleSyncToGun = () => {
        console.warn(
            '[Gunner] ProfilesTab: Sync to Gun not yet wired. ' +
            '/profile/apply is currently a stub in gunner.py line 393.'
        )
    }

    return (
        <div className="gunner-profiles">
            {/* Profile List (left column) */}
            <div className="gunner-profiles__list">
                <h4 className="gunner-profiles__list-title">PROFILE LIST</h4>
                {DEFAULT_PROFILES.map(profile => (
                    <button
                        key={profile.id}
                        className={`gunner-profiles__item${selectedProfile.id === profile.id ? ' gunner-profiles__item--selected' : ''}${profile.active ? ' gunner-profiles__item--active' : ''}`}
                        onClick={() => setSelectedProfile(profile)}
                    >
                        <span className="gunner-profiles__item-icon">{profile.icon}</span>
                        <div className="gunner-profiles__item-info">
                            <span className="gunner-profiles__item-name">{profile.name}</span>
                            <span className="gunner-profiles__item-date">Last Played: {profile.lastPlayed}</span>
                        </div>
                    </button>
                ))}
            </div>

            {/* Configuration Detail (center-right) */}
            <div className="gunner-profiles__detail">
                <div className="gunner-profiles__detail-header">
                    <h2 className="gunner-profiles__detail-title">{selectedProfile.name.toUpperCase()}</h2>
                    {selectedProfile.active && (
                        <span className="gunner-profiles__active-badge">● ACTIVE PROFILE</span>
                    )}
                </div>

                <div className="gunner-profiles__config-area">
                    {/* Config Grid */}
                    <div className="gunner-profiles__config-grid">
                        <h4 className="gunner-info-panel__title">CONFIGURATION GRID</h4>
                        <div className="gunner-profiles__config-row">
                            <span className="gunner-profiles__config-label">Gun Offset:</span>
                            <span className="gunner-profiles__config-value">+2 X, -1 Y</span>
                        </div>
                        <div className="gunner-profiles__config-row">
                            <span className="gunner-profiles__config-label">Recoil Strength:</span>
                            <span className="gunner-profiles__config-value gunner-profiles__config-value--high">High</span>
                        </div>
                        <div className="gunner-profiles__config-row">
                            <span className="gunner-profiles__config-label">Button Mapping:</span>
                            <div className="gunner-profiles__dpad">
                                <div className="gunner-profiles__dpad-up">▲</div>
                                <div className="gunner-profiles__dpad-mid">
                                    <span>◄</span>
                                    <span className="gunner-profiles__dpad-center">●</span>
                                    <span>►</span>
                                </div>
                                <div className="gunner-profiles__dpad-down">▼</div>
                            </div>
                        </div>
                    </div>

                    {/* Gun Schematic */}
                    <div className="gunner-profiles__schematic">
                        <svg viewBox="0 0 200 140" width="100%" className="gunner-profiles__gun-svg">
                            {/* Gun body outline */}
                            <rect x="30" y="30" width="120" height="45" rx="6"
                                fill="none" stroke="var(--cyber-cyan)" strokeWidth="1.5" opacity="0.7" />
                            {/* Barrel */}
                            <rect x="150" y="38" width="40" height="28" rx="3"
                                fill="none" stroke="var(--cyber-cyan)" strokeWidth="1" opacity="0.5" />
                            {/* Grip */}
                            <rect x="55" y="75" width="35" height="55" rx="5"
                                fill="none" stroke="var(--cyber-cyan)" strokeWidth="1.5" opacity="0.7" />
                            {/* Trigger */}
                            <path d="M75 80 Q80 95 70 100" fill="none" stroke="var(--cyber-pink)" strokeWidth="1.5" />
                            {/* Trigger guard */}
                            <path d="M50 78 Q50 105 75 105 Q95 105 95 78" fill="none" stroke="var(--cyber-cyan)" strokeWidth="1" opacity="0.4" />

                            {/* Labels */}
                            <text x="170" y="25" fill="var(--cyber-cyan)" fontSize="8" fontFamily="var(--font-mono)" textAnchor="middle">Reload</text>
                            <text x="170" y="33" fill="var(--cyber-pink)" fontSize="7" fontFamily="var(--font-mono)" textAnchor="middle">(Pump)</text>

                            <text x="25" y="95" fill="var(--cyber-cyan)" fontSize="8" fontFamily="var(--font-mono)" textAnchor="end">Start</text>
                            <text x="25" y="103" fill="var(--cyber-pink)" fontSize="7" fontFamily="var(--font-mono)" textAnchor="end">(Side Button)</text>

                            <text x="110" y="100" fill="var(--cyber-cyan)" fontSize="8" fontFamily="var(--font-mono)">Special</text>
                            <text x="110" y="108" fill="var(--cyber-pink)" fontSize="7" fontFamily="var(--font-mono)">(Trigger Hold)</text>

                            {/* Connection lines */}
                            <line x1="155" y1="35" x2="170" y2="30" stroke="var(--cyber-cyan)" strokeWidth="0.5" strokeDasharray="3" />
                            <line x1="50" y1="90" x2="30" y2="93" stroke="var(--cyber-cyan)" strokeWidth="0.5" strokeDasharray="3" />
                            <line x1="95" y1="90" x2="110" y2="98" stroke="var(--cyber-cyan)" strokeWidth="0.5" strokeDasharray="3" />
                        </svg>
                    </div>
                </div>

                {/* Action Buttons */}
                <div className="gunner-profiles__actions">
                    <button className="gunner-btn-action" onClick={handleSaveProfile}>[Save Profile]</button>
                    <button className="gunner-btn-action gunner-btn-action--pink" onClick={handleSyncToGun}>[Sync to Gun]</button>
                </div>
                <div style={{ marginTop: 10, color: 'var(--cyber-yellow)', fontSize: '0.9rem' }}>
                    Profile save/sync — backend wiring pending (post-duplication)
                </div>
            </div>
        </div>
    )
}

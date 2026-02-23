import React from 'react'

const TABS = [
    { id: 'devices', label: '[Devices]' },
    { id: 'calibration', label: '[Calibration]' },
    { id: 'profiles', label: '[Profiles]' },
    { id: 'retro-modes', label: '[Retro Modes]' },
]

/**
 * GunnerNav — Tab navigation with neon active/hover states
 */
export default function GunnerNav({ activeTab, onTabChange }) {
    return (
        <nav className="gunner-nav">
            {TABS.map(tab => (
                <button
                    key={tab.id}
                    className={`gunner-nav__tab${activeTab === tab.id ? ' gunner-nav__tab--active' : ''}`}
                    onClick={() => onTabChange(tab.id)}
                >
                    {tab.label}
                </button>
            ))}
        </nav>
    )
}

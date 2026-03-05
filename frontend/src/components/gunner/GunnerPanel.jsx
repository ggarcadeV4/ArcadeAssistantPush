import React, { useState, useCallback } from 'react'
import GunnerHeader from './GunnerHeader'
import GunnerNav from './GunnerNav'
import GunnerAlertBar from './GunnerAlertBar'
import DevicesTab from './DevicesTab'
import { EngineeringBaySidebar } from '../../panels/_kit/EngineeringBaySidebar'
import '../../panels/_kit/EngineeringBaySidebar.css'
import './GunnerPanel.css'

/** Gunner persona config for EngineeringBaySidebar */
const GUNNER_PERSONA = {
    id: 'gunner',
    name: 'GUNNER',
    icon: '🔫',
    icon2: '🎯',
    accentColor: '#A855F7',
    accentGlow: 'rgba(168, 85, 247, 0.35)',
    scannerLabel: 'TARGETING...',
    voiceProfile: 'gunner',
    emptyHint: 'Ask Gunner about light gun setup, calibration, or Sinden/Gun4IR config.',
    chips: [
        { id: 'scan', label: 'Scan devices', prompt: 'Scan for all connected light gun devices.' },
        { id: 'cal1', label: 'Calibrate Gun 1', prompt: 'Start calibration wizard for Gun 1.' },
        { id: 'sinden', label: 'Sinden setup', prompt: 'Show me how to configure a Sinden light gun.' },
        { id: 'gun4ir', label: 'Gun4IR config', prompt: 'Help me set up Gun4IR configuration.' },
    ],
};

/**
 * GunnerPanel — Main Retro Shooter Control Center
 *
 * Orchestrates all Gunner sub-components:
 * - Header with title & fleet status
 * - Tab navigation (Devices, Calibration, Profiles, Retro Modes)
 * - Active tab content
 * - AI chat sidebar
 * - Alert bar for critical warnings
 * - Scanline overlay for retro aesthetic
 */
export default function GunnerPanel() {
    const [activeTab, setActiveTab] = useState('devices')
    const [alertMessage, setAlertMessage] = useState(null)

    const handleScan = useCallback(() => {
        console.log('[GunnerPanel] Scan Hardware triggered')
    }, [])

    // Render active tab content
    const renderTabContent = () => {
        switch (activeTab) {
            case 'devices':
                return <DevicesTab onScan={handleScan} />
            case 'calibration':
                return (
                    <div className="gunner-tab-placeholder">
                        ⊕ Calibration Wizard — Coming Soon
                    </div>
                )
            case 'profiles':
                return (
                    <div className="gunner-tab-placeholder">
                        ⊕ Profile Manager — Coming Soon
                    </div>
                )
            case 'retro-modes':
                return (
                    <div className="gunner-tab-placeholder">
                        ⊕ Retro Mode Selector — Coming Soon
                    </div>
                )
            default:
                return null
        }
    }

    return (
        <div className="gunner-panel">
            {/* Scanline overlay */}
            <div className="gunner-scanlines" />

            {/* Header */}
            <GunnerHeader />

            {/* Alert Bar */}
            <GunnerAlertBar message={alertMessage} />

            {/* Tab Navigation */}
            <GunnerNav activeTab={activeTab} onTabChange={setActiveTab} />

            {/* Main Content Area + Chat Sidebar */}
            <div className="gunner-content" style={{ alignItems: 'flex-start' }}>
                <main className="gunner-main">
                    {renderTabContent()}
                </main>
                <EngineeringBaySidebar persona={GUNNER_PERSONA} />
            </div>

            {/* Footer Status Bar */}
            <footer className="gunner-footer">
                <span className="gunner-footer__sync">Last sync: Just now</span>
                <span className="gunner-footer__golden">Golden Baseline: Active</span>
            </footer>
        </div>
    )
}

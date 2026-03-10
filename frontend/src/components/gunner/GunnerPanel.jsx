import React, { useState, useCallback, useEffect } from 'react'
import { listDevices } from '../../services/gunnerClient'
import GunnerHeader from './GunnerHeader'
import GunnerNav from './GunnerNav'
import GunnerAlertBar from './GunnerAlertBar'
import DevicesTab from './DevicesTab'
import CalibrationTab from './CalibrationTab'
import ProfilesTab from './ProfilesTab'
import RetroModesTab from './RetroModesTab'
import { EngineeringBaySidebar } from '../../panels/_kit/EngineeringBaySidebar'
import '../../panels/_kit/EngineeringBaySidebar.css'
import './GunnerPanel.css'

/** Gunner persona config for EngineeringBaySidebar */
const GUNNER_PERSONA = {
    id: 'gunner',
    name: 'GUNNER',
    icon: '🔫',
    icon2: '🎯',
    accentColor: '#EF4444',
    accentGlow: 'rgba(239, 68, 68, 0.35)',
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
 * Layout: Full-width tabs + overlay chat drawer from right.
 * The chat sidebar slides in/out without affecting the tab content layout.
 */
export default function GunnerPanel() {
    const [activeTab, setActiveTab] = useState('devices')
    const [alertMessage, setAlertMessage] = useState(null)
    const [chatOpen, setChatOpen] = useState(false)
    const [devices, setDevices] = useState([])
    const [lastSync, setLastSync] = useState(null)
    const [scanning, setScanning] = useState(false)

    const handleScan = useCallback(async () => {
        setScanning(true)
        setAlertMessage(null)
        try {
            const result = await listDevices()
            const devList = result?.devices || result || []
            setDevices(devList)
            setLastSync(new Date())
            console.log('[GunnerPanel] Scan complete:', devList.length, 'devices')
        } catch (err) {
            console.error('[GunnerPanel] Scan error:', err)
            setAlertMessage('⚠️ Hardware scan failed: ' + (err.message || 'Unknown error'))
        } finally {
            setScanning(false)
        }
    }, [])

    // Auto-scan on mount
    useEffect(() => { handleScan() }, [handleScan])

    const renderTabContent = () => {
        switch (activeTab) {
            case 'devices':
                return <DevicesTab devices={devices.length > 0 ? devices : undefined} onScan={handleScan} />
            case 'calibration':
                return <CalibrationTab />
            case 'profiles':
                return <ProfilesTab />
            case 'retro-modes':
                return <RetroModesTab />
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

            {/* Tab Navigation + Chat button */}
            <div className="gunner-nav-row">
                <GunnerNav activeTab={activeTab} onTabChange={setActiveTab} />
                <button
                    className={`gunner-chat-btn${chatOpen ? ' gunner-chat-btn--active' : ''}`}
                    onClick={() => setChatOpen(prev => !prev)}
                >
                    💬 {chatOpen ? 'Close Chat' : 'Chat'}
                </button>
            </div>

            {/* Full-width tab content */}
            <div className="gunner-content">
                <main className="gunner-main">
                    {renderTabContent()}
                </main>
            </div>

            {/* Chat Drawer Overlay */}
            <div
                className={`gunner-drawer-backdrop${chatOpen ? ' gunner-drawer-backdrop--visible' : ''}`}
                onClick={() => setChatOpen(false)}
            />
            <aside className={`gunner-drawer${chatOpen ? ' gunner-drawer--open' : ''}`}>
                <button
                    className="gunner-drawer__close"
                    onClick={() => setChatOpen(false)}
                    aria-label="Close chat"
                >
                    ✕
                </button>
                <EngineeringBaySidebar persona={GUNNER_PERSONA} />
            </aside>

            {/* Footer Status Bar */}
            <footer className="gunner-footer">
                <span className="gunner-footer__sync">
                    {scanning ? '⏳ Scanning...' : lastSync ? `Last sync: ${lastSync.toLocaleTimeString()}` : 'Last sync: Never'}
                </span>
                <span className="gunner-footer__golden">Golden Baseline: Active</span>
            </footer>
        </div>
    )
}

import React, { useState, useCallback, useEffect, useMemo } from 'react'
import { useLocation } from 'react-router-dom'
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

const MOCK_HARDWARE_ENABLED = ['1', 'true', 'yes', 'on'].includes(
    String(import.meta.env.VITE_MOCK_HARDWARE ?? '').toLowerCase()
)

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
    const [hasScanned, setHasScanned] = useState(false)
    const [lastSync, setLastSync] = useState(null)
    const [scanning, setScanning] = useState(false)

    // AA_HANDOFF: read Dewey handoff context from URL param.
    // When a context is present, auto-open the chat drawer so the user
    // can see their problem statement was carried from Dewey.
    const location = useLocation()
    const deweyContext = useMemo(() => {
      const params = new URLSearchParams(location.search)
      const raw = params.get('context') || ''
      return raw.trim() ? decodeURIComponent(raw) : null
    }, [location.search])

    useEffect(() => {
      if (deweyContext) {
        setChatOpen(true)
      }
    }, [deweyContext])

    const normalizeDeviceType = useCallback((type) => {
        if (!type || type === 'mock') {
            return null
        }

        switch (String(type).toLowerCase()) {
            case 'aimtrak':
                return 'AimTrak'
            case 'gun4ir':
                return 'Gun4IR'
            case 'sinden':
                return 'Sinden'
            default:
                return String(type)
        }
    }, [])

    const normalizeDeviceForCard = useCallback((device, index) => ({
        player: index === 0 ? '1P' : index === 1 ? '2P' : `P${index + 1}`,
        name: String(device?.name ?? 'Light Gun Device').replace(/\s*\(mock\)\s*$/i, ''),
        model: normalizeDeviceType(device?.type),
        connected: Boolean(device?.connected),
        battery: typeof device?.battery === 'number' ? device.battery : null,
        firmware: device?.firmware ?? null,
        vid: device?.vid ?? null,
        pid: device?.pid ?? null,
    }), [normalizeDeviceType])

    const handleScan = useCallback(async () => {
        setScanning(true)
        setAlertMessage(null)
        try {
            const result = await listDevices()
            const devicesFromApi = Array.isArray(result?.devices)
                ? result.devices
                : Array.isArray(result)
                    ? result
                    : []
            const filteredDevices = MOCK_HARDWARE_ENABLED
                ? devicesFromApi
                : devicesFromApi.filter((device) => device?.type !== 'mock')
            const normalizedDevices = filteredDevices.map((device, index) => normalizeDeviceForCard(device, index))
            setDevices(normalizedDevices)
            setLastSync(new Date())

            if (normalizedDevices.length === 0) {
                setAlertMessage('No light gun hardware detected')
            }
        } catch (err) {
            setDevices([])
            setAlertMessage('Scan failed — check USB connection')
        } finally {
            setHasScanned(true)
            setScanning(false)
        }
    }, [normalizeDeviceForCard])

    // Auto-scan on mount
    useEffect(() => { handleScan() }, [handleScan])

    const renderTabContent = () => {
        switch (activeTab) {
            case 'devices':
                return <DevicesTab devices={devices} hasScanned={hasScanned} scanning={scanning} onScan={handleScan} />
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
                {/* AA_HANDOFF: show Dewey context at top of drawer */}
                {deweyContext && (
                    <div style={{
                        margin: '0 0 10px 0',
                        padding: '8px 12px',
                        background: 'rgba(239,68,68,0.12)',
                        border: '1px solid rgba(239,68,68,0.35)',
                        borderRadius: 6,
                        fontSize: 12,
                        color: '#fca5a5',
                        lineHeight: 1.5
                    }}>
                        <strong style={{ display: 'block', color: '#ef4444', marginBottom: 3 }}>
                            🎯 From Dewey:
                        </strong>
                        {deweyContext}
                    </div>
                )}
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

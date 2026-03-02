import React, { useState, useCallback } from 'react'
import GunnerHeader from './GunnerHeader'
import GunnerNav from './GunnerNav'
import GunnerAlertBar from './GunnerAlertBar'
import DevicesTab from './DevicesTab'
import GunnerChatSidebar from './GunnerChatSidebar'
import { useGunnerChat } from '../../hooks/useGunnerChat'
import './GunnerPanel.css'

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
    const [alertMessage, setAlertMessage] = useState('Gun 2P low battery (20%)')
    const chatState = useGunnerChat()

    const handleScan = useCallback(() => {
        console.log('[GunnerPanel] Scan Hardware triggered')
        chatState.send('Scan for all connected light gun devices.')
    }, [chatState.send])

    const handleChatSend = useCallback((text) => {
        chatState.send(text)
    }, [chatState.send])

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
                <GunnerChatSidebar
                    chatState={chatState}
                    onSend={handleChatSend}
                    style={{ height: '100vh', position: 'sticky', top: 0, flexShrink: 0 }}
                />
            </div>

            {/* Footer Status Bar */}
            <footer className="gunner-footer">
                <span className="gunner-footer__sync">Last sync: Just now</span>
                <span className="gunner-footer__golden">Golden Baseline: Active</span>
            </footer>
        </div>
    )
}

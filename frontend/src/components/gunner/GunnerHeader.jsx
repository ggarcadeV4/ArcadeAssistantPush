import React from 'react'

/**
 * GunnerHeader — Title bar with neon styling
 * Shows "GUNNER: RETRO SHOOTER CONTROL CENTER" + MAC/Fleet status
 */
// TODO: Replace with live MAC address from cabinet manifest
// TODO: Replace with live fleet status from heartbeat
export default function GunnerHeader({ macAddress = 'AB12', fleetStatus = 'Connected' }) {
    return (
        <header className="gunner-header">
            <div className="gunner-header__title-row">
                <h1 className="gunner-header__title">
                    <span className="cyan">GUNNER:</span>{' '}
                    <span className="pink">RETRO SHOOTER</span>{' '}
                    <span className="cyan">CONTROL CENTER</span>
                </h1>
                <div className="gunner-header__dots">
                    <div className="gunner-header__dot gunner-header__dot--pink" />
                    <div className="gunner-header__dot gunner-header__dot--cyan" />
                    <div className="gunner-header__dot gunner-header__dot--green" />
                </div>
            </div>
            <div className="gunner-header__status-row">
                <span>MAC Address: <span className="value-cyan">[{macAddress}]</span></span>
                <span className="separator">|</span>
                <span>Fleet Status: <span className="value-green">{fleetStatus}</span></span>
            </div>
        </header>
    )
}

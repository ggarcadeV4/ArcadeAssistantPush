import React from 'react'

/**
 * DeviceCard — Individual light gun device card
 * Shows name, connection status, battery level, and firmware version
 */
export default function DeviceCard({ device }) {
    const {
        name = 'Unknown Gun',
        model = 'Unknown',
        connected = false,
        battery = 0,
        firmware = 'N/A',
        player = '?P'
    } = device || {}

    const batteryClass = battery > 60 ? '--high' : battery > 25 ? '--medium' : '--low'

    return (
        <article className="gunner-device-card">
            <div>
                <h3 className="gunner-device-card__name">{player} Gun: {name}</h3>
                <p className="gunner-device-card__model">{model}</p>
                <div className="gunner-device-card__status">
                    <span className={`gunner-device-card__status-dot gunner-device-card__status-dot--${connected ? 'connected' : 'disconnected'}`} />
                    <span style={{ color: connected ? 'var(--cyber-green)' : 'var(--cyber-red)' }}>
                        {connected ? 'Connected' : 'Disconnected'}
                    </span>
                </div>
            </div>
            <div>
                <div className="gunner-device-card__battery">
                    <div
                        className={`gunner-device-card__battery-fill gunner-device-card__battery-fill${batteryClass}`}
                        style={{ width: `${battery}%` }}
                    />
                </div>
                <div className="gunner-device-card__battery-label">
                    <span>Battery</span>
                    <span>{battery}%</span>
                </div>
                <div className="gunner-device-card__firmware">
                    Firmware: v{firmware}
                </div>
            </div>
        </article>
    )
}

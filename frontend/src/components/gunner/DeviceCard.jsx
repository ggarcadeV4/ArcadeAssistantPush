import React from 'react'

/**
 * DeviceCard — Individual light gun device card
 * Shows name, connection status, battery level, and firmware version
 */
export default function DeviceCard({ device }) {
    const {
        name = 'Light Gun Device',
        model = null,
        connected = false,
        battery = null,
        firmware = null,
        player = '?P',
        vid = null,
        pid = null,
    } = device || {}

    const hasBattery = typeof battery === 'number'
    const batteryPercent = hasBattery ? battery : 0
    const batteryClass = batteryPercent > 60 ? '--high' : batteryPercent > 25 ? '--medium' : '--low'
    const hasFirmware = typeof firmware === 'string' && firmware.trim().length > 0
    const hasVidPid = Boolean(vid || pid)

    return (
        <article className="gunner-device-card">
            <div>
                <h3 className="gunner-device-card__name">{player} Gun: {name}</h3>
                {model ? <p className="gunner-device-card__model">{model}</p> : null}
                <div className="gunner-device-card__status">
                    <span className={`gunner-device-card__status-dot gunner-device-card__status-dot--${connected ? 'connected' : 'disconnected'}`} />
                    <span style={{ color: connected ? 'var(--cyber-green)' : 'var(--cyber-red)' }}>
                        {connected ? 'Connected' : 'Disconnected'}
                    </span>
                </div>
                {hasVidPid ? (
                    <div className="gunner-device-card__detail">
                        {[vid ? `VID: ${vid}` : null, pid ? `PID: ${pid}` : null].filter(Boolean).join(' | ')}
                    </div>
                ) : null}
            </div>
            <div>
                {hasBattery ? (
                    <>
                        <div className="gunner-device-card__battery">
                            <div
                                className={`gunner-device-card__battery-fill gunner-device-card__battery-fill${batteryClass}`}
                                style={{ width: `${batteryPercent}%` }}
                            />
                        </div>
                        <div className="gunner-device-card__battery-label">
                            <span>Battery</span>
                            <span>{`${batteryPercent}%`}</span>
                        </div>
                    </>
                ) : null}
                {hasFirmware ? (
                    <div className="gunner-device-card__firmware">
                        Firmware: v{firmware}
                    </div>
                ) : null}
            </div>
        </article>
    )
}

import React from 'react'

const DEFAULT_SENSORS = [
    { position: 'Top Left', status: 'optimal', signal: 'Optimal (Green)' },
    { position: 'Top Right', status: 'optimal', signal: 'Optimal (Green)' },
    { position: 'Bottom Left', status: 'optimal', signal: 'Optimal (Green)' },
    { position: 'Bottom Right', status: 'optimal', signal: 'Optimal (Green)' },
]

/**
 * SensorGrid — 2×2 quadrant sensor status display
 * Shows signal strength indicator for each sensor position
 */
export default function SensorGrid({ sensors = DEFAULT_SENSORS }) {
    return (
        <div className="gunner-info-panel">
            <h4 className="gunner-info-panel__title">Sensor Grid</h4>
            <div className="gunner-sensor-grid">
                {sensors.map((sensor, i) => (
                    <div key={i} className={`gunner-sensor-cell gunner-sensor-cell--${sensor.status}`}>
                        <div className="gunner-sensor-cell__icon">⊕</div>
                        <div className="gunner-sensor-cell__info">
                            <span className="gunner-sensor-cell__label">{sensor.position}:</span>
                            <span className="gunner-sensor-cell__status">{sensor.signal}</span>
                        </div>
                    </div>
                ))}
            </div>
        </div>
    )
}

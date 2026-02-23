import React from 'react'
import DeviceCard from './DeviceCard'
import SensorGrid from './SensorGrid'
import ConnectionMatrix from './ConnectionMatrix'

// Mock devices for visual prototyping — will be replaced by gunnerClient.listDevices()
const MOCK_DEVICES = [
    {
        player: '1P',
        name: 'Retro Blaster',
        model: 'Sinden Lightgun v2',
        connected: true,
        battery: 85,
        firmware: '1.2.4'
    },
    {
        player: '2P',
        name: 'Retro Blaster',
        model: 'Sinden Lightgun v2',
        connected: true,
        battery: 20,
        firmware: '1.2.4'
    }
]

const MOCK_SENSORS = [
    { position: 'Top Left', status: 'weak', signal: 'Weak (Yellow)' },
    { position: 'Top Right', status: 'optimal', signal: 'Optimal (Green)' },
    { position: 'Bottom Left', status: 'optimal', signal: 'Optimal (Green)' },
    { position: 'Bottom Right', status: 'optimal', signal: 'Optimal (Green)' },
]

/**
 * DevicesTab — Devices tab content
 * Shows gun cards, sensor grid, connection matrix, and scan action
 */
export default function DevicesTab({ devices = MOCK_DEVICES, sensors = MOCK_SENSORS, onScan }) {
    const sensorCount = sensors.filter(s => s.status === 'optimal').length
    const totalSensors = sensors.length

    return (
        <div>
            {/* Gun Cards */}
            <div className="gunner-devices-grid">
                {devices.map((device, i) => (
                    <DeviceCard key={i} device={device} />
                ))}
            </div>

            {/* Sensor Grid + Connection Matrix */}
            <div className="gunner-info-row">
                <SensorGrid sensors={sensors} />
                <ConnectionMatrix />
            </div>

            {/* Action Area */}
            <div className="gunner-action-area">
                <h4 className="gunner-info-panel__title">Action Area</h4>
                <button className="gunner-btn-action" onClick={onScan}>
                    Scan Hardware
                </button>
            </div>

            {/* Golden Baseline */}
            <div className="gunner-baseline">
                <strong>Golden Baseline: </strong>
                <span className="gunner-baseline__value">
                    Sensors: {sensorCount}/{totalSensors} OK
                    {sensorCount === totalSensors ? ' (matches Golden Baseline)' : ''}
                </span>
            </div>
        </div>
    )
}

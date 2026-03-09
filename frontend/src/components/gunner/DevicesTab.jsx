import React from 'react'
import DeviceCard from './DeviceCard'
import SensorGrid from './SensorGrid'
import ConnectionMatrix from './ConnectionMatrix'

const DEFAULT_DEVICES = [
    { player: '1P', name: 'Retro Blaster', model: 'Sinden v2.1', connected: true, battery: 85, firmware: '2.1.3' },
    { player: '2P', name: 'Retro Blaster', model: 'Gun4IR', connected: true, battery: 42, firmware: '1.4.1' },
]

/**
 * DevicesTab — Devices tab content
 * Shows gun cards, sensor grid, connection matrix, and scan action
 */
export default function DevicesTab({ devices = DEFAULT_DEVICES, sensors = [], onScan }) {
    const sensorCount = sensors.filter(s => s.status === 'optimal').length
    const totalSensors = sensors.length

    return (
        <div>
            {/* Gun Cards */}
            <div className="gunner-devices-grid">
                {devices.length > 0 ? devices.map((device, i) => (
                    <DeviceCard key={i} device={device} />
                )) : <div className="gunner-tab-placeholder">No devices detected. Click "Scan Hardware" to refresh.</div>}
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

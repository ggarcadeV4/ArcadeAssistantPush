import React from 'react'
import DeviceCard from './DeviceCard'
import SensorGrid from './SensorGrid'
import ConnectionMatrix from './ConnectionMatrix'

/**
 * DevicesTab — Devices tab content
 * Shows gun cards, sensor grid, connection matrix, and scan action
 */
export default function DevicesTab({ devices = [], hasScanned = false, scanning = false, sensors = [], onScan }) {
    const sensorCount = sensors.filter(s => s.status === 'optimal').length
    const totalSensors = sensors.length
    const showEmptyState = hasScanned && !scanning && devices.length === 0

    return (
        <div>
            {/* Gun Cards */}
            <div className="gunner-devices-grid">
                {devices.length > 0 ? devices.map((device, i) => (
                    <DeviceCard key={i} device={device} />
                )) : showEmptyState ? (
                    <div className="gunner-tab-placeholder">No light gun hardware detected. Connect a Sinden, AimTrak, or Gun4IR device and scan again.</div>
                ) : scanning ? (
                    <div className="gunner-tab-placeholder">Scanning for connected light gun hardware...</div>
                ) : (
                    <div className="gunner-tab-placeholder">No devices detected. Click "Scan Hardware" to refresh.</div>
                )}
            </div>

            {/* Sensor Grid + Connection Matrix */}
            <div className="gunner-info-row">
                <SensorGrid sensors={sensors} />
                <ConnectionMatrix />
            </div>

            {/* Action Area */}
            <div className="gunner-action-area">
                <h4 className="gunner-info-panel__title">Action Area</h4>
                <button className="gunner-btn-action" onClick={onScan} disabled={scanning}>
                    {scanning ? 'Scanning...' : 'Scan Hardware'}
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

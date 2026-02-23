import React from 'react'

/**
 * ConnectionMatrix — Hardware chain flow diagram
 * Shows: Guns → Sensors → USB-C Hub
 */
export default function ConnectionMatrix() {
    return (
        <div className="gunner-info-panel">
            <h4 className="gunner-info-panel__title">Connection Matrix</h4>
            <div className="gunner-connection-matrix">
                <div className="gunner-matrix-node">Guns (1P, 2P)</div>
                <div className="gunner-matrix-arrow">→</div>
                <div className="gunner-matrix-node">Sensors (IR Array)</div>
                <div className="gunner-matrix-arrow">→</div>
                <div className="gunner-matrix-node">USB-C Hub</div>
            </div>
        </div>
    )
}

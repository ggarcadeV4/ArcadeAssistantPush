/**
 * useLEDConnection — manages WebSocket lifecycle, hardware status, and derived connection state.
 * Extracted from LEDBlinkyPanel.jsx.
 */
import { useState, useEffect, useRef, useCallback, useMemo } from 'react'
import LEDWebSocketManager from '../services/LEDWebSocketManager'
import {
    getLEDStatus,
    refreshLEDHardware,
    buildGatewayWebSocketUrl,
    getLEDEngineHealth
} from '../services/ledBlinkyClient'

export function useLEDConnection({ showToast }) {
    const [connectionStatus, setConnectionStatus] = useState('disconnected')
    const [connectionLog, setConnectionLog] = useState([])
    const defaultWebsocketUrl = buildGatewayWebSocketUrl('/api/local/led/ws')
    const [gatewaySocketUrl, setGatewaySocketUrl] = useState(defaultWebsocketUrl)
    const [hardwareStatus, setHardwareStatus] = useState(null)
    const [isRefreshingStatus, setIsRefreshingStatus] = useState(false)
    const [engineHealth, setEngineHealth] = useState(null)

    const wsManagerRef = useRef(null)

    const runtimeStatus = hardwareStatus?.runtime || null

    const registryDevices = useMemo(() => {
        if (runtimeStatus?.registry && Array.isArray(runtimeStatus.registry.all_devices)) {
            return runtimeStatus.registry.all_devices
        }
        return []
    }, [runtimeStatus])

    const engineDiagnostics = engineHealth || hardwareStatus?.engine || runtimeStatus?.engine || null

    const engineEvents = useMemo(() => {
        if (engineHealth && Array.isArray(engineHealth.events)) {
            return engineHealth.events
        }
        if (runtimeStatus && Array.isArray(runtimeStatus.events)) {
            return runtimeStatus.events
        }
        if (runtimeStatus && Array.isArray(runtimeStatus.log)) {
            return runtimeStatus.log
        }
        return []
    }, [engineHealth, runtimeStatus])

    const connectedDevices = useMemo(() => {
        if (runtimeStatus && Array.isArray(runtimeStatus.devices)) {
            return runtimeStatus.devices
        }
        return []
    }, [runtimeStatus])

    const simulationMode = Boolean(
        runtimeStatus?.registry?.simulation_mode ||
        (engineDiagnostics ? engineDiagnostics.simulation_mode : false)
    )

    const wsConnectionCount =
        typeof engineHealth?.ws_client_count === 'number'
            ? engineHealth.ws_client_count
            : typeof hardwareStatus?.connections === 'number'
                ? hardwareStatus.connections
                : 0

    const queueDepth = typeof engineHealth?.queue_depth === 'number' ? engineHealth.queue_depth : 0

    const pendingCommands =
        typeof engineHealth?.pending_commands === 'number' ? engineHealth.pending_commands : queueDepth

    const activePatternName = engineHealth?.active_pattern || engineDiagnostics?.active_pattern || null

    const registryMessage = runtimeStatus?.registry?.message

    const refreshHardwareStatus = useCallback(async () => {
        try {
            setIsRefreshingStatus(true)
            try {
                await refreshLEDHardware()
            } catch (refreshErr) {
                console.warn('Hardware refresh failed (continuing with status fetch)', refreshErr)
            }
            const status = await getLEDStatus()
            setHardwareStatus(status)
            if (Array.isArray(status?.log)) {
                setConnectionLog(status.log)
            }
            const wsPath = status?.ws?.url || '/api/local/led/ws'
            setGatewaySocketUrl(buildGatewayWebSocketUrl(wsPath))
            try {
                const health = await getLEDEngineHealth()
                setEngineHealth(health)
            } catch (healthErr) {
                console.warn('Failed to load LED engine health', healthErr)
                setEngineHealth(null)
            }
            return status
        } catch (err) {
            const message = err?.error || err?.message || 'Failed to load hardware status'
            showToast(message, 'error')
            return null
        } finally {
            setIsRefreshingStatus(false)
        }
    }, [showToast])

    const toggleWebSocketConnection = useCallback(async () => {
        if (connectionStatus === 'connected') {
            wsManagerRef.current?.disconnect()
            await refreshHardwareStatus()
            return
        }

        const latestStatus = await refreshHardwareStatus()
        const targetUrl = buildGatewayWebSocketUrl(latestStatus?.ws?.url || gatewaySocketUrl)
        if (!targetUrl) {
            showToast('Gateway WebSocket unavailable', 'error')
            return
        }
        wsManagerRef.current?.connect(targetUrl)
    }, [connectionStatus, gatewaySocketUrl, refreshHardwareStatus, showToast])

    // Initialize WebSocket manager on mount
    useEffect(() => {
        wsManagerRef.current = new LEDWebSocketManager()
        wsManagerRef.current.init(setConnectionStatus, setConnectionLog, showToast, refreshHardwareStatus)
        wsManagerRef.current.autoReconnectEnabled = true

        return () => {
            if (wsManagerRef.current?.ws) {
                wsManagerRef.current.disableAutoReconnect()
                wsManagerRef.current.disconnect()
            }
        }
    }, [refreshHardwareStatus, showToast])

    // Fetch status on mount
    useEffect(() => {
        refreshHardwareStatus()
    }, [refreshHardwareStatus])

    return {
        // State
        connectionStatus,
        connectionLog,
        gatewaySocketUrl,
        hardwareStatus,
        isRefreshingStatus,
        engineHealth,
        // Derived
        runtimeStatus,
        registryDevices,
        engineDiagnostics,
        engineEvents,
        connectedDevices,
        simulationMode,
        wsConnectionCount,
        queueDepth,
        pendingCommands,
        activePatternName,
        registryMessage,
        // Actions
        refreshHardwareStatus,
        toggleWebSocketConnection,
        // Ref (needed by LED toggle and other callbacks)
        wsManagerRef
    }
}

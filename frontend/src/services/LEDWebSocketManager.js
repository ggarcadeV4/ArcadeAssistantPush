/**
 * LEDWebSocketManager — manages the WebSocket connection to the LED gateway.
 * Extracted from LEDBlinkyPanel.jsx for separation of concerns.
 */
import { closeLEDConnection } from './ledBlinkyClient'

class LEDWebSocketManager {
    constructor() {
        this.ws = null
        this.url = ''
        this.reconnectAttempts = 0
        this.maxReconnectAttempts = 5
        this.reconnectDelay = 2000
        this.isConnecting = false
        this.connectionLog = []
        this.autoReconnectEnabled = false
        this.setConnectionStatus = null
        this.setConnectionLog = null
        this.showToast = null
        this.refreshStatus = null
        this.gatewayConnectionId = null
    }

    // Initialize callbacks from component
    init(setConnectionStatus, setConnectionLog, showToast, refreshStatus) {
        this.setConnectionStatus = setConnectionStatus
        this.setConnectionLog = setConnectionLog
        this.showToast = showToast
        this.refreshStatus = refreshStatus
    }

    async syncStatus() {
        if (typeof this.refreshStatus === 'function') {
            try {
                await this.refreshStatus()
            } catch (err) {
                console.warn('LED status refresh failed', err?.message || err)
            }
        }
    }

    connect(url) {
        if (!url) {
            this.log('Gateway WebSocket URL is missing', 'error')
            this.showToast?.('Gateway WebSocket unavailable', 'error')
            this.setConnectionStatus?.('error')
            return
        }

        if (this.isConnecting) {
            this.log('Connection already in progress...', 'warning')
            return
        }

        this.url = url
        this.gatewayConnectionId = null
        this.isConnecting = true
        this.log(`Attempting to connect to ${url}...`, 'info')
        this.setConnectionStatus?.('connecting')

        try {
            this.ws = new WebSocket(url)

            this.ws.onopen = () => {
                this.isConnecting = false
                this.reconnectAttempts = 0
                this.log('WebSocket connected successfully!', 'success')
                this.setConnectionStatus?.('connected')
                this.showToast?.('Hardware connected via WebSocket', 'websocket')
                this.syncStatus()

                this.send({
                    type: 'handshake',
                    client: 'led-blinky-panel',
                    version: '2.0.0'
                })
            }

            this.ws.onmessage = (event) => {
                try {
                    const data = JSON.parse(event.data)
                    this.handleMessage(data)
                } catch (error) {
                    this.log(`Invalid message received: ${event.data}`, 'error')
                }
            }

            this.ws.onclose = (event) => {
                this.isConnecting = false
                this.log(`Connection closed (Code: ${event.code})`, 'error')
                this.setConnectionStatus?.('disconnected')
                this.gatewayConnectionId = null
                this.syncStatus()

                // Only auto-reconnect if enabled and not a manual disconnect
                if (this.autoReconnectEnabled && event.code !== 1000 && this.reconnectAttempts < this.maxReconnectAttempts) {
                    this.scheduleReconnect()
                }
            }

            this.ws.onerror = (error) => {
                this.isConnecting = false
                this.log('WebSocket error occurred', 'error')
                this.setConnectionStatus?.('error')
                this.syncStatus()
            }

            setTimeout(() => {
                if (this.isConnecting) {
                    this.ws.close()
                    this.log('Connection timeout', 'error')
                    this.setConnectionStatus?.('disconnected')
                }
            }, 10000)

        } catch (error) {
            this.isConnecting = false
            this.log(`Failed to create WebSocket: ${error.message}`, 'error')
            this.setConnectionStatus?.('error')
        }
    }

    disconnect() {
        if (this.gatewayConnectionId) {
            closeLEDConnection(this.gatewayConnectionId).catch(() => {
                this.log('Failed to notify gateway about disconnect', 'warning')
            })
        }
        this.gatewayConnectionId = null
        if (this.ws) {
            this.ws.close(1000, 'User disconnected')
            this.ws = null
        }
        this.log('Disconnected by user', 'info')
        this.setConnectionStatus?.('disconnected')
        this.syncStatus()
    }

    send(data) {
        if (this.ws && this.ws.readyState === WebSocket.OPEN) {
            this.ws.send(JSON.stringify(data))
            return true
        } else {
            this.log('Cannot send data: WebSocket not connected', 'warning')
            return false
        }
    }

    handleMessage(data) {
        this.log(`Received: ${data.type}`, 'info')

        switch (data.type) {
            case 'handshake_response':
                this.log(`Server: ${data.server} v${data.version}`, 'success')
                break
            case 'led_state':
                // Will be handled by component callback
                break
            case 'pattern_complete':
                this.log(`Pattern '${data.pattern}' completed`, 'info')
                break
            case 'error':
                this.log(`Server error: ${data.message}`, 'error')
                this.showToast?.(`Hardware error: ${data.message}`, 'error')
                break
            case 'gateway_status':
                this.gatewayConnectionId = data.connectionId || null
                this.log(`Gateway bridge ready (${data.mode || 'proxy'})`, 'success')
                break
            case 'gateway_notice':
                this.log(`Gateway notice: ${data.status || data.message}`, data.status === 'mock_mode' ? 'warning' : 'info')
                break
            case 'gateway_error':
                this.log(`Gateway error: ${data.message}`, 'error')
                this.showToast?.(`Gateway error: ${data.message}`, 'error')
                break
            case 'mock_ack':
                this.log(`Gateway ack (${data.received_bytes ?? 0} bytes)`, 'info')
                break
            default:
                this.log(`Unknown message type: ${data.type}`, 'warning')
        }
    }

    log(message, type = 'info') {
        const timestamp = new Date().toLocaleTimeString()
        const logEntry = { timestamp, message, type }
        this.setConnectionLog?.(prev => [...prev.slice(-49), logEntry])
    }

    sendLEDCommand(player, button, state, color = null) {
        const command = {
            type: 'led_command',
            player: parseInt(player),
            button: button,
            state: state,
            timestamp: Date.now()
        }

        if (color) {
            command.color = color
        }

        if (this.send(command)) {
            this.log(`LED P${player}-${button}: ${state ? 'ON' : 'OFF'}`, 'info')
        }
    }

    sendPattern(patternName, params = {}) {
        const command = {
            type: 'pattern',
            pattern: patternName,
            params: params,
            timestamp: Date.now()
        }

        if (this.send(command)) {
            this.log(`Pattern sent: ${patternName}`, 'info')
        }
    }

    scheduleReconnect() {
        this.reconnectAttempts++
        const delay = Math.min(this.reconnectDelay * Math.pow(2, this.reconnectAttempts - 1), 30000) // Exponential backoff, max 30s
        this.log(`Auto-reconnecting in ${delay / 1000}s (Attempt ${this.reconnectAttempts}/${this.maxReconnectAttempts})`, 'warning')

        setTimeout(() => {
            if (this.reconnectAttempts <= this.maxReconnectAttempts) {
                this.log('Auto-reconnect attempt...', 'info')
                this.connect(this.url)
            } else {
                this.log('Auto-reconnect failed: Maximum attempts reached', 'error')
                this.showToast?.('Connection failed: Auto-reconnect exhausted', 'error')
            }
        }, delay)
    }

    enableAutoReconnect() {
        this.autoReconnectEnabled = true
        this.log('Auto-reconnect enabled', 'info')
    }

    disableAutoReconnect() {
        this.autoReconnectEnabled = false
        this.reconnectAttempts = 0
        this.log('Auto-reconnect disabled', 'info')
    }
}

export default LEDWebSocketManager

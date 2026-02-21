/**
 * useLEDCalibrationSession — manages calibration token, flash/assign operations, and global helpers.
 * Extracted from LEDBlinkyPanel.jsx.
 */
import { useState, useCallback, useEffect } from 'react'
import {
    startLEDCalibration,
    assignLEDCalibration,
    flashLEDCalibration,
    stopLEDCalibration
} from '../services/ledBlinkyClient'

export function useLEDCalibrationSession({ showToast, loadChannelMappings, channelSelection }) {
    const [calibrationToken, setCalibrationToken] = useState(null)
    const [isStartingCalibration, setIsStartingCalibration] = useState(false)
    const [isStoppingCalibration, setIsStoppingCalibration] = useState(false)
    const [isFlashingChannel, setIsFlashingChannel] = useState(false)

    const startCalibrationSession = useCallback(async () => {
        setIsStartingCalibration(true)
        try {
            const data = await startLEDCalibration()
            setCalibrationToken(data.token)
            showToast('Calibration mode active', 'success')
            return data
        } catch (err) {
            const message = err?.error || err?.message || 'Failed to start calibration'
            showToast(message, 'error')
            throw err
        } finally {
            setIsStartingCalibration(false)
        }
    }, [showToast])

    const stopCalibrationSession = useCallback(
        async (tokenOverride) => {
            const token = tokenOverride || calibrationToken
            if (!token) {
                showToast('No calibration session to stop.', 'error')
                return null
            }
            setIsStoppingCalibration(true)
            try {
                const data = await stopLEDCalibration({ token })
                if (!tokenOverride) {
                    setCalibrationToken(null)
                }
                showToast('Calibration mode ended', 'success')
                return data
            } catch (err) {
                const message = err?.error || err?.message || 'Failed to stop calibration'
                showToast(message, 'error')
                throw err
            } finally {
                setIsStoppingCalibration(false)
            }
        },
        [calibrationToken, showToast]
    )

    const flashCalibrationHelper = useCallback(
        async ({ token, logicalButton, deviceId, channel, durationMs, color } = {}) => {
            const activeToken = token || calibrationToken
            if (!activeToken) {
                throw new Error('Calibration token is required to flash LEDs.')
            }
            if (!logicalButton && (!deviceId || !channel)) {
                throw new Error('Provide logicalButton or both deviceId and channel.')
            }
            const payload = {
                token: activeToken,
                logical_button: logicalButton,
                device_id: deviceId,
                channel,
                duration_ms: durationMs,
                color
            }
            return await flashLEDCalibration(payload)
        },
        [calibrationToken]
    )

    const flashSelectedChannel = useCallback(async () => {
        if (!calibrationToken) {
            showToast('Start calibration before flashing a channel.', 'error')
            return
        }
        if (!channelSelection?.logicalButton) {
            showToast('Select a logical button first.', 'error')
            return
        }
        setIsFlashingChannel(true)
        try {
            await flashCalibrationHelper({ logicalButton: channelSelection.logicalButton })
            showToast(`Flashing ${channelSelection.logicalButton}`, 'success')
        } catch (err) {
            const message = err?.error || err?.detail || err?.message || 'Failed to flash LED'
            showToast(message, 'error')
        } finally {
            setIsFlashingChannel(false)
        }
    }, [calibrationToken, channelSelection?.logicalButton, flashCalibrationHelper, showToast])

    const assignCalibrationMapping = useCallback(
        async ({ token, logicalButton, deviceId, channel, dryRun } = {}) => {
            const activeToken = token || calibrationToken
            if (!activeToken) {
                throw new Error('Calibration token is required to assign wiring.')
            }
            if (!logicalButton || !deviceId || !channel) {
                throw new Error('logicalButton, deviceId, and channel are required.')
            }
            const payload = {
                token: activeToken,
                logical_button: logicalButton,
                device_id: deviceId,
                channel,
                dry_run: dryRun
            }
            const result = await assignLEDCalibration(payload)
            await loadChannelMappings()
            return result
        },
        [calibrationToken, loadChannelMappings]
    )

    // Expose global helpers for AI command integration
    useEffect(() => {
        const helpers = {
            startCalibration: () => startCalibrationSession(),
            assignCalibration: (params) => assignCalibrationMapping(params),
            flashCalibration: (params) => flashCalibrationHelper(params),
            stopCalibration: (token) => stopCalibrationSession(token),
            fetchChannels: () => loadChannelMappings()
        }
        window.AA_LED_CALIBRATION = helpers
        return () => {
            if (window.AA_LED_CALIBRATION === helpers) {
                delete window.AA_LED_CALIBRATION
            }
        }
    }, [
        assignCalibrationMapping,
        flashCalibrationHelper,
        loadChannelMappings,
        startCalibrationSession,
        stopCalibrationSession
    ])

    return {
        calibrationToken,
        setCalibrationToken,
        isStartingCalibration,
        isStoppingCalibration,
        isFlashingChannel,
        startCalibrationSession,
        stopCalibrationSession,
        flashCalibrationHelper,
        flashSelectedChannel,
        assignCalibrationMapping
    }
}

/**
 * useLEDDemoControls — manages demo/test hardware controls and channel test state.
 * Extracted from LEDBlinkyPanel.jsx.
 */
import { useState, useCallback, useEffect } from 'react'
import { testLED, runLEDChannelTest } from '../services/ledBlinkyClient'

export function useLEDDemoControls({ showToast, registryDevices }) {
    // Camera Demo Controls State
    const [demoTestDuration, setDemoTestDuration] = useState(2000)
    const [isTestingAllLEDs, setIsTestingAllLEDs] = useState(false)
    const [demoFlashPlayer, setDemoFlashPlayer] = useState('1')
    const [demoFlashButton, setDemoFlashButton] = useState('1')
    const [demoFlashColor, setDemoFlashColor] = useState('#00FF00')
    const [isFlashingDemo, setIsFlashingDemo] = useState(false)
    const [demoColorPickerControl, setDemoColorPickerControl] = useState(null) // { player, button }
    const [demoLastError, setDemoLastError] = useState(null)

    // Channel test state
    const [channelTestDevice, setChannelTestDevice] = useState('')
    const [channelTestChannel, setChannelTestChannel] = useState('0')
    const [isTestingChannel, setIsTestingChannel] = useState(false)
    const [channelTestResult, setChannelTestResult] = useState(null)

    // Sync channelTestDevice when registryDevices changes
    useEffect(() => {
        if (!registryDevices.length) {
            return
        }
        if (!channelTestDevice || !registryDevices.some((device) => device.device_id === channelTestDevice)) {
            setChannelTestDevice(registryDevices[0].device_id)
        }
    }, [registryDevices, channelTestDevice])

    const triggerHardwareTest = useCallback(
        async (effect, overrides = {}) => {
            try {
                const result = await testLED({ effect, ...overrides })
                if (result?.status) {
                    showToast(`Hardware test: ${result.status}`, 'success')
                }
            } catch (err) {
                const message = err?.error || err?.message || 'Hardware test failed'
                showToast(message, 'error')
            }
        },
        [showToast]
    )

    const handleChannelTest = useCallback(async () => {
        if (!channelTestDevice) {
            showToast('Select a device before running a channel test', 'error')
            return
        }
        const channelNumber = Number(channelTestChannel)
        if (Number.isNaN(channelNumber) || channelNumber < 0) {
            showToast('Channel must be a non-negative number', 'error')
            return
        }

        setIsTestingChannel(true)
        setChannelTestResult(null)
        try {
            const result = await runLEDChannelTest({
                deviceId: channelTestDevice,
                channel: channelNumber,
                durationMs: 300
            })
            setChannelTestResult({ status: 'success', payload: result })
            showToast(`Channel ${channelNumber} test ${result.status}`, 'success')
        } catch (err) {
            const detail = err?.detail || err
            const message = detail?.message || detail?.error || err?.message || 'Channel test failed'
            setChannelTestResult({ status: 'error', message })
            showToast(message, 'error')
        } finally {
            setIsTestingChannel(false)
        }
    }, [channelTestChannel, channelTestDevice, showToast])

    return {
        // Demo controls
        demoTestDuration,
        setDemoTestDuration,
        isTestingAllLEDs,
        setIsTestingAllLEDs,
        demoFlashPlayer,
        setDemoFlashPlayer,
        demoFlashButton,
        setDemoFlashButton,
        demoFlashColor,
        setDemoFlashColor,
        isFlashingDemo,
        setIsFlashingDemo,
        demoColorPickerControl,
        setDemoColorPickerControl,
        demoLastError,
        setDemoLastError,
        // Channel test
        channelTestDevice,
        setChannelTestDevice,
        channelTestChannel,
        setChannelTestChannel,
        isTestingChannel,
        channelTestResult,
        // Actions
        triggerHardwareTest,
        handleChannelTest
    }
}

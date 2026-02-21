/**
 * useLEDChannels — manages LED channel/wiring mapping state and actions.
 * Extracted from LEDBlinkyPanel.jsx.
 */
import { useState, useCallback, useEffect, useMemo } from 'react'
import {
    listLEDChannelMappings,
    previewLEDChannels,
    applyLEDChannels,
    deleteLEDChannelMapping
} from '../services/ledBlinkyClient'

export function useLEDChannels({ showToast, activeMode }) {
    const [channelState, setChannelState] = useState({
        channels: {},
        unmapped: [],
        unknown_logical: [],
        total_channels: 0,
        target_file: ''
    })
    const [isLoadingChannels, setIsLoadingChannels] = useState(false)
    const [channelSelection, setChannelSelection] = useState({
        logicalButton: '',
        deviceId: '',
        channel: ''
    })
    const [channelPreview, setChannelPreview] = useState(null)
    const [isChannelPreviewing, setIsChannelPreviewing] = useState(false)
    const [isChannelApplying, setIsChannelApplying] = useState(false)
    const [isDeletingChannel, setIsDeletingChannel] = useState(false)

    const channelOptions = useMemo(() => {
        const mappedKeys = Object.keys(channelState.channels || {})
        const extras = [
            ...(Array.isArray(channelState.unmapped) ? channelState.unmapped : []),
            ...(Array.isArray(channelState.unknown_logical) ? channelState.unknown_logical : [])
        ]
        const combined = Array.from(new Set([...mappedKeys, ...extras]))
        combined.sort()
        return combined
    }, [channelState])

    const channelEntries = useMemo(() => Object.entries(channelState.channels || {}), [channelState.channels])

    const loadChannelMappings = useCallback(async () => {
        setIsLoadingChannels(true)
        try {
            const data = await listLEDChannelMappings()
            setChannelState(data)
            setChannelPreview(null)
            setChannelSelection((prev) => {
                const docChannels = data.channels || {}
                if (prev.logicalButton) {
                    const entry = docChannels[prev.logicalButton]
                    if (entry) {
                        return {
                            ...prev,
                            deviceId: entry.device_id || '',
                            channel: entry.channel ? String(entry.channel) : ''
                        }
                    }
                }
                const available = Object.keys(docChannels)
                const fallbackCandidates = [
                    ...available,
                    ...(Array.isArray(data.unmapped) ? data.unmapped : []),
                    ...(Array.isArray(data.unknown_logical) ? data.unknown_logical : [])
                ].filter(Boolean)
                const fallback = fallbackCandidates[0] || ''
                if (!fallback) {
                    return {
                        logicalButton: '',
                        deviceId: '',
                        channel: ''
                    }
                }
                const entry = docChannels[fallback]
                return {
                    logicalButton: fallback,
                    deviceId: entry?.device_id || '',
                    channel: entry?.channel ? String(entry.channel) : ''
                }
            })
            return data
        } catch (err) {
            const message = err?.error || err?.message || 'Failed to load LED wiring'
            showToast(message, 'error')
            throw err
        } finally {
            setIsLoadingChannels(false)
        }
    }, [showToast])

    const handleSelectChannel = useCallback(
        (logicalButton) => {
            const mapping = channelState.channels?.[logicalButton]
            setChannelSelection({
                logicalButton,
                deviceId: mapping?.device_id || '',
                channel: mapping?.channel ? String(mapping.channel) : ''
            })
            setChannelPreview(null)
        },
        [channelState.channels]
    )

    const handleChannelFieldChange = useCallback((field, value) => {
        setChannelSelection((prev) => ({ ...prev, [field]: value }))
        setChannelPreview(null)
    }, [])

    const buildChannelUpdatePayload = useCallback(() => {
        const logicalButton = (channelSelection.logicalButton || '').trim()
        if (!logicalButton) {
            throw new Error('Select a logical button to calibrate.')
        }
        const deviceId = (channelSelection.deviceId || '').trim()
        if (!deviceId) {
            throw new Error('Device ID is required.')
        }
        const channelNumber = Number(channelSelection.channel)
        if (!Number.isFinite(channelNumber) || !Number.isInteger(channelNumber) || channelNumber < 1) {
            throw new Error('Channel must be a positive integer.')
        }
        return {
            updates: [
                {
                    logical_button: logicalButton,
                    device_id: deviceId,
                    channel: channelNumber
                }
            ]
        }
    }, [channelSelection])

    const previewChannelUpdate = useCallback(async () => {
        let payload
        try {
            payload = buildChannelUpdatePayload()
        } catch (err) {
            showToast(err?.message || 'Invalid LED wiring payload', 'error')
            return
        }
        setIsChannelPreviewing(true)
        try {
            const preview = await previewLEDChannels(payload)
            setChannelPreview(preview)
            showToast('LED wiring preview ready', 'success')
        } catch (err) {
            const message = err?.error || err?.detail || err?.message || 'LED wiring preview failed'
            showToast(message, 'error')
        } finally {
            setIsChannelPreviewing(false)
        }
    }, [buildChannelUpdatePayload, showToast])

    const applyChannelUpdate = useCallback(async () => {
        let payload
        try {
            payload = buildChannelUpdatePayload()
        } catch (err) {
            showToast(err?.message || 'Invalid LED wiring payload', 'error')
            return
        }
        setIsChannelApplying(true)
        try {
            const result = await applyLEDChannels({ ...payload, dry_run: false })
            setChannelPreview(result.preview)
            try {
                await loadChannelMappings()
            } catch (refreshErr) {
                console.warn('LED channel reload failed', refreshErr)
            }
            const status = result.status === 'applied' ? 'success' : result.status === 'dry_run' ? 'info' : 'info'
            const message =
                result.status === 'applied'
                    ? 'LED wiring updated with backup.'
                    : result.status === 'dry_run'
                        ? 'LED wiring dry-run completed.'
                        : 'No LED wiring changes detected.'
            showToast(message, status)
        } catch (err) {
            const message = err?.error || err?.detail || err?.message || 'LED wiring apply failed'
            showToast(message, 'error')
        } finally {
            setIsChannelApplying(false)
        }
    }, [buildChannelUpdatePayload, loadChannelMappings, showToast])

    const removeChannelMapping = useCallback(async () => {
        const logicalButton = channelSelection.logicalButton
        if (!logicalButton) {
            showToast('Select a logical button to delete.', 'error')
            return
        }
        setIsDeletingChannel(true)
        try {
            await deleteLEDChannelMapping(logicalButton, { dryRun: false })
            await loadChannelMappings()
            showToast(`Removed wiring for ${logicalButton}`, 'success')
        } catch (err) {
            const message = err?.error || err?.detail || err?.message || 'Failed to delete channel'
            showToast(message, 'error')
        } finally {
            setIsDeletingChannel(false)
        }
    }, [channelSelection.logicalButton, loadChannelMappings, showToast])

    // Load on mount
    useEffect(() => {
        loadChannelMappings()
    }, [loadChannelMappings])

    // Reload when layout tab is active
    useEffect(() => {
        if (activeMode === 'layout') {
            loadChannelMappings()
        }
    }, [activeMode, loadChannelMappings])

    return {
        channelState,
        isLoadingChannels,
        channelSelection,
        channelPreview,
        isChannelPreviewing,
        isChannelApplying,
        isDeletingChannel,
        channelOptions,
        channelEntries,
        loadChannelMappings,
        handleSelectChannel,
        handleChannelFieldChange,
        previewChannelUpdate,
        applyChannelUpdate,
        removeChannelMapping
    }
}

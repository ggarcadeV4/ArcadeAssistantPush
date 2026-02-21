/**
 * useLEDProfiles — manages LED profile loading, preview, apply, and mapping form state.
 * Extracted from LEDBlinkyPanel.jsx.
 */
import { useState, useCallback, useEffect, useMemo } from 'react'
import {
    listLEDProfiles,
    getLEDProfile,
    previewLEDProfile,
    applyLEDProfile
} from '../services/ledBlinkyClient'
import {
    DEFAULT_MAPPING_FORM,
    extractButtonsFromPayload,
    buildFormFromButtons,
    buildButtonsFromForm
} from '../utils/buttonMapping'

export function useLEDProfiles({ showToast, activeMode }) {
    const [mappingData, setMappingData] = useState(() =>
        JSON.stringify({ buttons: buildButtonsFromForm(DEFAULT_MAPPING_FORM) }, null, 2)
    )
    const [profilePreview, setProfilePreview] = useState(null)
    const [availableProfiles, setAvailableProfiles] = useState([])
    const [profileSearchTerm, setProfileSearchTerm] = useState('')
    const [selectedProfile, setSelectedProfile] = useState('')
    const [selectedProfileMeta, setSelectedProfileMeta] = useState(null)
    const [isLoadingProfiles, setIsLoadingProfiles] = useState(false)
    const [isApplyingMapping, setIsApplyingMapping] = useState(false)
    const [lastPreviewPayload, setLastPreviewPayload] = useState(null)
    const [lastPreviewProfileKey, setLastPreviewProfileKey] = useState(null)

    const [mappingForm, setMappingForm] = useState(() => ({ ...DEFAULT_MAPPING_FORM }))

    // Sync mappingForm to mappingData (JSON string)
    useEffect(() => {
        if (Object.keys(mappingForm).length > 0) {
            const buttons = buildButtonsFromForm(mappingForm)
            setMappingData(JSON.stringify({ buttons }, null, 2))
        }
    }, [mappingForm])

    useEffect(() => {
        setProfilePreview(null)
        setLastPreviewPayload(null)
        setLastPreviewProfileKey(null)
    }, [mappingData])

    const setButtonColor = useCallback((key, value) => {
        setMappingForm(prev => ({ ...prev, [key]: value }))
    }, [])

    const loadAvailableProfiles = useCallback(async () => {
        setIsLoadingProfiles(true)
        try {
            const data = await listLEDProfiles()
            const profiles = Array.isArray(data?.profiles) ? data.profiles : []
            const normalizedProfiles = profiles.map(profile => {
                if (typeof profile === 'string') {
                    return {
                        value: profile,
                        label: profile,
                        metadata: { filename: profile }
                    }
                }

                const value = profile.profile_name || profile.filename || profile.game || profile.scope || 'profile'
                const filename = profile.filename || `${value}.json`

                const labelParts = []
                if (profile.game) {
                    labelParts.push(profile.game)
                } else if (filename) {
                    labelParts.push(filename)
                } else {
                    labelParts.push(value)
                }

                if (profile.scope) {
                    const scopeLabel = profile.scope === 'default' ? 'Default' : profile.scope
                    labelParts.push(scopeLabel)
                }

                if (Array.isArray(profile.mapping_keys) && profile.mapping_keys.length > 0) {
                    labelParts.push(`${profile.mapping_keys.length} keys`)
                }

                return {
                    value,
                    label: labelParts.join(' • '),
                    metadata: profile
                }
            })

            setAvailableProfiles(normalizedProfiles)
        } catch (err) {
            console.error('Failed to load LED profiles:', err)
            showToast('Failed to load LED profiles', 'error')
        } finally {
            setIsLoadingProfiles(false)
        }
    }, [showToast])

    const refreshProfiles = useCallback(() => {
        if (!isLoadingProfiles) {
            loadAvailableProfiles()
        }
    }, [isLoadingProfiles, loadAvailableProfiles])

    useEffect(() => {
        if ((activeMode === 'animation' || activeMode === 'profiles') && availableProfiles.length === 0 && !isLoadingProfiles) {
            loadAvailableProfiles()
        }
    }, [activeMode, availableProfiles.length, isLoadingProfiles, loadAvailableProfiles])

    const handleLoadProfile = useCallback(async (profileValue) => {
        if (!profileValue) return null

        const profileEntry = availableProfiles.find(profile => profile.value === profileValue)
        const requestName = profileEntry?.value ?? profileValue

        try {
            const profile = await getLEDProfile(requestName)
            const mapping = profile.mapping || {}
            const buttons = extractButtonsFromPayload(mapping)

            if (Object.keys(buttons).length > 0) {
                setMappingForm(buildFormFromButtons(buttons))
                setMappingData(JSON.stringify({ buttons }, null, 2))
            } else {
                setMappingForm({ ...DEFAULT_MAPPING_FORM })
                setMappingData(JSON.stringify(mapping, null, 2))
            }

            const mergedMetadata = {
                ...(typeof profile.metadata === 'object' && profile.metadata ? profile.metadata : {}),
                ...(profileEntry?.metadata || {})
            }
            const payload = {
                profile_name: profile.profile_name || mergedMetadata.profile_name || requestName,
                scope: profile.scope || mergedMetadata.scope || 'game',
                game: profile.game || mergedMetadata.game || requestName,
                metadata: { ...mergedMetadata, source: 'led-blinky-panel' },
                buttons
            }

            setSelectedProfile(profileEntry?.value ?? profileValue)
            setSelectedProfileMeta(mergedMetadata)
            setProfilePreview(null)
            showToast(`Loaded profile: ${payload.game}`, 'success')
            return payload
        } catch (err) {
            console.error('Failed to load profile:', err)
            showToast('Failed to load profile', 'error')
            return null
        }
    }, [availableProfiles, showToast])

    const buildProfilePayload = useCallback(() => {
        if (!mappingData.trim()) {
            throw new Error('Empty mapping payload')
        }

        let parsed
        parsed = JSON.parse(mappingData)

        const buttons = extractButtonsFromPayload(parsed)
        if (Object.keys(buttons).length === 0) {
            throw new Error('No valid button mappings found')
        }

        const profileName = parsed.profile_name || selectedProfile || 'custom-profile'
        const scope = parsed.scope || selectedProfileMeta?.scope || 'game'
        const game = parsed.game || selectedProfileMeta?.game || profileName
        const metadata = {
            ...(typeof parsed.metadata === 'object' && parsed.metadata ? parsed.metadata : {}),
            source: 'led-blinky-panel'
        }

        return {
            profile_name: profileName,
            scope,
            game,
            metadata,
            buttons
        }
    }, [mappingData, selectedProfile, selectedProfileMeta])

    const handlePreviewProfile = useCallback(
        async (payloadOverride = null, { profileKey } = {}) => {
            if (!payloadOverride && !mappingData.trim()) {
                showToast('Please enter mapping data', 'error')
                return
            }

            let payload
            try {
                payload = payloadOverride || buildProfilePayload()
            } catch (err) {
                if (err instanceof SyntaxError) {
                    showToast('Invalid JSON format', 'error')
                } else {
                    const message = err?.message || 'Failed to generate preview'
                    showToast(message, 'error')
                }
                return
            }

            try {
                const payloadString = JSON.stringify(payload)
                const preview = await previewLEDProfile(payload)
                setProfilePreview(preview)
                setLastPreviewPayload(payloadString)
                setLastPreviewProfileKey(profileKey || selectedProfile || payload.profile_name || payload.game || null)
                showToast('Preview generated', 'success')
            } catch (err) {
                if (err instanceof SyntaxError) {
                    showToast('Invalid JSON format', 'error')
                } else {
                    const message = err?.message || 'Failed to generate preview'
                    showToast(message, 'error')
                }
            }
        },
        [buildProfilePayload, mappingData, selectedProfile, showToast]
    )

    const handleApplyProfile = useCallback(async () => {
        if (!mappingData.trim()) {
            showToast('Please enter mapping data', 'error')
            return
        }

        if (!profilePreview) {
            showToast('Preview changes before applying', 'error')
            return
        }

        setIsApplyingMapping(true)
        try {
            const basePayload = buildProfilePayload()
            const payloadString = JSON.stringify(basePayload)
            if (!lastPreviewPayload || payloadString !== lastPreviewPayload) {
                showToast('Preview changes before applying', 'error')
                return
            }
            const result = await applyLEDProfile({ ...basePayload, dry_run: false })
            setProfilePreview(result.preview)
            setLastPreviewPayload(payloadString)
            const statusText = result.status === 'applied' ? 'Profile applied successfully' : 'Dry run'
            showToast(statusText, 'success')
        } catch (err) {
            if (err instanceof SyntaxError) {
                showToast('Invalid JSON format', 'error')
            } else {
                const message = err?.detail || err?.error || err?.message || 'Failed to apply mapping'
                showToast(message, 'error')
            }
        } finally {
            setIsApplyingMapping(false)
        }
    }, [buildProfilePayload, lastPreviewPayload, mappingData, profilePreview, showToast])

    const previewProfileFromLibrary = useCallback(
        async (profileValue) => {
            const payload = await handleLoadProfile(profileValue)
            if (!payload) return
            if (!payload.buttons || Object.keys(payload.buttons).length === 0) {
                showToast('Profile has no button mappings to preview', 'error')
                return
            }
            try {
                await handlePreviewProfile(payload, { profileKey: profileValue })
            } catch {
                /* errors handled inside handlePreviewProfile */
            }
        },
        [handleLoadProfile, handlePreviewProfile, showToast]
    )

    const applyProfileFromLibrary = useCallback(
        async (profileValue) => {
            if (lastPreviewProfileKey !== profileValue) {
                showToast('Preview this profile before applying', 'error')
                return
            }
            await handleApplyProfile()
        },
        [handleApplyProfile, lastPreviewProfileKey, showToast]
    )

    const editProfileInDesigner = useCallback(
        async (profileValue, setActiveMode) => {
            const payload = await handleLoadProfile(profileValue)
            if (payload) {
                setActiveMode('animation')
            }
        },
        [handleLoadProfile]
    )

    // Derived values
    const hasMappingInput = Boolean(mappingData.trim())
    const canApplyProfile = hasMappingInput && Boolean(profilePreview) && Boolean(lastPreviewPayload) && !isApplyingMapping

    const filteredProfiles = useMemo(() => {
        const term = profileSearchTerm.trim().toLowerCase()
        if (!term) {
            return availableProfiles
        }
        return availableProfiles.filter(profile => {
            const label = (profile.label || '').toLowerCase()
            const filename = (profile.metadata?.filename || '').toLowerCase()
            const gameName = (profile.metadata?.game || '').toLowerCase()
            const scope = (profile.metadata?.scope || '').toLowerCase()
            return label.includes(term) || filename.includes(term) || gameName.includes(term) || scope.includes(term)
        })
    }, [availableProfiles, profileSearchTerm])

    const selectedProfileDisplayName =
        selectedProfileMeta?.game ||
        selectedProfileMeta?.profile_name ||
        selectedProfile ||
        'profile'

    const canApplyLibraryProfile =
        Boolean(
            selectedProfile &&
            profilePreview &&
            lastPreviewPayload &&
            lastPreviewProfileKey === selectedProfile &&
            !isApplyingMapping
        )

    const libraryPreviewReady = Boolean(selectedProfile && lastPreviewProfileKey === selectedProfile && profilePreview)

    return {
        // State
        mappingData,
        setMappingData,
        mappingForm,
        setMappingForm,
        profilePreview,
        availableProfiles,
        profileSearchTerm,
        setProfileSearchTerm,
        selectedProfile,
        selectedProfileMeta,
        isLoadingProfiles,
        isApplyingMapping,
        lastPreviewPayload,
        lastPreviewProfileKey,
        // Derived
        hasMappingInput,
        canApplyProfile,
        filteredProfiles,
        selectedProfileDisplayName,
        canApplyLibraryProfile,
        libraryPreviewReady,
        // Actions
        setButtonColor,
        loadAvailableProfiles,
        refreshProfiles,
        handleLoadProfile,
        buildProfilePayload,
        handlePreviewProfile,
        handleApplyProfile,
        previewProfileFromLibrary,
        applyProfileFromLibrary,
        editProfileInDesigner
    }
}

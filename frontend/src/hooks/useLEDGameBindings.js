/**
 * useLEDGameBindings — manages game search, game-to-profile binding state and CRUD.
 * Extracted from LEDBlinkyPanel.jsx.
 */
import { useState, useCallback, useEffect, useRef } from 'react'
import {
    searchLaunchBoxGames,
    fetchGameProfile,
    fetchAllGameProfiles,
    previewGameProfileBinding,
    applyGameProfileBinding,
    deleteGameProfileBinding
} from '../services/ledBlinkyClient'

export function useLEDGameBindings({ showToast, activeMode }) {
    const [gameSearchTerm, setGameSearchTerm] = useState('')
    const [gameResults, setGameResults] = useState([])
    const [isLoadingGames, setIsLoadingGames] = useState(false)
    const [selectedGame, setSelectedGame] = useState(null)
    const [selectedGameBinding, setSelectedGameBinding] = useState(null)
    const [selectedGameProfileName, setSelectedGameProfileName] = useState('')
    const [gameBindingsIndex, setGameBindingsIndex] = useState({})
    const [bindingPreview, setBindingPreview] = useState(null)
    const [lastBindingPreviewKey, setLastBindingPreviewKey] = useState(null)
    const [isPreviewingBinding, setIsPreviewingBinding] = useState(false)
    const [isApplyingBinding, setIsApplyingBinding] = useState(false)
    const [isClearingBinding, setIsClearingBinding] = useState(false)
    const [isLoadingBinding, setIsLoadingBinding] = useState(false)

    const gameSearchQueryRef = useRef('')

    const loadGameBindings = useCallback(async () => {
        try {
            const response = await fetchAllGameProfiles()
            const bindings = Array.isArray(response?.bindings) ? response.bindings : []
            const index = {}
            bindings.forEach(binding => {
                if (binding?.game_id) {
                    index[binding.game_id] = binding
                }
            })
            setGameBindingsIndex(index)
        } catch (err) {
            const message = err?.error || err?.message || 'Failed to load LED game profiles'
            showToast(message, 'error')
        }
    }, [showToast])

    useEffect(() => {
        loadGameBindings()
    }, [loadGameBindings])

    useEffect(() => {
        setBindingPreview(null)
        setLastBindingPreviewKey(null)
    }, [selectedGame?.id, selectedGameProfileName])

    // Update game results when bindings index changes
    useEffect(() => {
        setGameResults(prev =>
            prev.map(game => ({
                ...game,
                assigned_profile: gameBindingsIndex[game.id] || null
            }))
        )
    }, [gameBindingsIndex])

    const loadGameResults = useCallback(
        async (query = '') => {
            setIsLoadingGames(true)
            gameSearchQueryRef.current = query
            try {
                const response = await searchLaunchBoxGames({ query, limit: 50 })
                const games = Array.isArray(response?.games) ? response.games : []
                const augmented = games.map((game) => ({
                    ...game,
                    assigned_profile: gameBindingsIndex[game.id] || null
                }))
                setGameResults(augmented)
                if (selectedGame) {
                    const updatedSelection = augmented.find(game => game.id === selectedGame.id)
                    if (updatedSelection) {
                        setSelectedGame(updatedSelection)
                    }
                }
            } catch (err) {
                const message = err?.error || err?.message || 'Failed to load LaunchBox games'
                showToast(message, 'error')
            } finally {
                setIsLoadingGames(false)
            }
        },
        [gameBindingsIndex, selectedGame, showToast]
    )

    useEffect(() => {
        if (activeMode === 'profiles' && !isLoadingGames && gameResults.length === 0) {
            loadGameResults('')
        }
    }, [activeMode, gameResults.length, isLoadingGames, loadGameResults])

    const handleSearchGames = useCallback(() => {
        loadGameResults(gameSearchTerm.trim())
    }, [gameSearchTerm, loadGameResults])

    const handleGameSearchKeyDown = useCallback(
        (event) => {
            if (event.key === 'Enter') {
                event.preventDefault()
                handleSearchGames()
            }
        },
        [handleSearchGames]
    )

    const handleSelectGame = useCallback(
        async (game) => {
            setSelectedGame(game)
            setSelectedGameBinding(null)
            setBindingPreview(null)
            setLastBindingPreviewKey(null)
            setIsLoadingBinding(true)
            try {
                const response = await fetchGameProfile(game.id)
                if (response?.game) {
                    setSelectedGame(response.game)
                }
                const binding = response?.binding || null
                setSelectedGameBinding(binding)
                setSelectedGameProfileName(binding?.profile_name || gameBindingsIndex[game.id]?.profile_name || '')
            } catch (err) {
                const message = err?.error || err?.message || 'Failed to load game profile'
                showToast(message, 'error')
            } finally {
                setIsLoadingBinding(false)
            }
        },
        [gameBindingsIndex, showToast]
    )

    const handlePreviewGameProfile = useCallback(async () => {
        if (!selectedGame) {
            showToast('Select a LaunchBox game first', 'error')
            return
        }
        if (!selectedGameProfileName) {
            showToast('Choose a profile to preview', 'error')
            return
        }
        setIsPreviewingBinding(true)
        try {
            const response = await previewGameProfileBinding({
                gameId: selectedGame.id,
                profileName: selectedGameProfileName
            })
            setBindingPreview(response?.preview || null)
            setLastBindingPreviewKey(`${selectedGame.id}:${selectedGameProfileName}`)
            showToast('Binding preview ready', 'success')
        } catch (err) {
            const message = err?.error || err?.message || 'Failed to preview binding'
            showToast(message, 'error')
        } finally {
            setIsPreviewingBinding(false)
        }
    }, [selectedGame, selectedGameProfileName, showToast])

    const handleApplyGameProfile = useCallback(async () => {
        if (!selectedGame) {
            showToast('Select a LaunchBox game first', 'error')
            return
        }
        if (!selectedGameProfileName) {
            showToast('Choose a profile to assign', 'error')
            return
        }
        const previewKey = `${selectedGame.id}:${selectedGameProfileName}`
        if (lastBindingPreviewKey !== previewKey) {
            showToast('Preview the binding before applying', 'error')
            return
        }
        setIsApplyingBinding(true)
        try {
            const response = await applyGameProfileBinding({
                gameId: selectedGame.id,
                profileName: selectedGameProfileName
            })
            const binding = response?.binding || null
            setBindingPreview(response?.preview || null)
            setSelectedGameBinding(binding)
            setGameBindingsIndex(prev => ({ ...prev, [selectedGame.id]: binding }))
            setLastBindingPreviewKey(previewKey)
            showToast(`Assigned ${selectedGameProfileName} to ${selectedGame.title}`, 'success')
        } catch (err) {
            const message = err?.error || err?.message || 'Failed to assign LED profile'
            showToast(message, 'error')
        } finally {
            setIsApplyingBinding(false)
        }
    }, [lastBindingPreviewKey, selectedGame, selectedGameProfileName, showToast])

    const handleClearGameProfile = useCallback(async () => {
        if (!selectedGame) {
            showToast('Select a LaunchBox game first', 'error')
            return
        }
        if (!selectedGameBinding) {
            showToast('This game is not assigned to a profile', 'error')
            return
        }
        setIsClearingBinding(true)
        try {
            await deleteGameProfileBinding(selectedGame.id)
            setGameBindingsIndex(prev => {
                const next = { ...prev }
                delete next[selectedGame.id]
                return next
            })
            setSelectedGameBinding(null)
            setSelectedGameProfileName('')
            setBindingPreview(null)
            setLastBindingPreviewKey(null)
            showToast(`Cleared LED profile for ${selectedGame.title}`, 'success')
        } catch (err) {
            const message = err?.error || err?.message || 'Failed to remove assignment'
            showToast(message, 'error')
        } finally {
            setIsClearingBinding(false)
        }
    }, [selectedGame, selectedGameBinding, showToast])

    // Derived
    const bindingRequestKey = selectedGame && selectedGameProfileName ? `${selectedGame.id}:${selectedGameProfileName}` : null
    const canPreviewBinding = Boolean(selectedGame && selectedGameProfileName && !isPreviewingBinding && !isLoadingBinding)
    const canApplyBinding =
        Boolean(bindingPreview && bindingRequestKey && lastBindingPreviewKey === bindingRequestKey && !isApplyingBinding)
    const canClearBinding = Boolean(selectedGameBinding && !isClearingBinding)

    return {
        gameSearchTerm,
        setGameSearchTerm,
        gameResults,
        isLoadingGames,
        selectedGame,
        selectedGameBinding,
        selectedGameProfileName,
        setSelectedGameProfileName,
        gameBindingsIndex,
        bindingPreview,
        lastBindingPreviewKey,
        isPreviewingBinding,
        isApplyingBinding,
        isClearingBinding,
        isLoadingBinding,
        bindingRequestKey,
        canPreviewBinding,
        canApplyBinding,
        canClearBinding,
        loadGameBindings,
        loadGameResults,
        handleSearchGames,
        handleGameSearchKeyDown,
        handleSelectGame,
        handlePreviewGameProfile,
        handleApplyGameProfile,
        handleClearGameProfile
    }
}

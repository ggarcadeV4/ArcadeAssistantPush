// @hook: useShaderPreview
// @owner: LoRa
// @extracted-from: LaunchBoxPanel.jsx (Phase 1a)
// @purpose: Manages shader preview modal state, apply/remove/preview logic

import { useState, useCallback } from 'react'

/**
 * useShaderPreview – extracts shader preview state and handlers from
 * LaunchBoxPanel.jsx. Owns shaderModal, shaderPreview, and pendingShaderApply
 * state, plus openShaderPreview, closeShaderPreview, applyShaderChange,
 * removeShaderBinding, maybeHandleShaderToolCalls, and cancelShaderPreview.
 *
 * @param {Object} opts
 * @param {Function} opts.addMessage – append a chat message
 * @param {Function} opts.showToast  – display a toast notification
 * @param {Function} opts.setChatOpen – open the chat sidebar (needed by openShaderPreview)
 * @param {string}   opts.deviceId   – current device ID for API headers
 */
export default function useShaderPreview({ addMessage, showToast, setChatOpen, deviceId }) {
  // Shader modal state
  const [shaderPreview, setShaderPreview] = useState(null)
  const [shaderModal, setShaderModal] = useState({ open: false, applying: false, error: '', gameId: '', shaderName: '', emulator: '', diff: '', oldConfig: null, newConfig: null })
  const [pendingShaderApply, setPendingShaderApply] = useState(null)

  const openShaderPreview = useCallback((preview) => {
    const gameId = preview?.gameId || preview?.game_id || ''
    const shaderName = preview?.shaderName || preview?.shader_name || ''
    const emulator = preview?.emulator || ''
    const oldConfig = preview?.old || null
    const newConfig = preview?.new || null
    setShaderPreview({
      diff: preview?.diff || '',
      oldText: JSON.stringify(oldConfig || { shader: 'none' }, null, 2),
      newText: JSON.stringify(newConfig || {}, null, 2),
      gameId,
      shaderName,
      emulator
    })
    setPendingShaderApply({ game_id: gameId, shader_name: shaderName, emulator })
    setShaderModal(prev => ({ ...prev, open: true, gameId, shaderName, emulator, diff: preview?.diff || '', oldConfig, newConfig }))
    setChatOpen(true)
  }, [setChatOpen])

  const closeShaderPreview = useCallback(() => {
    setShaderModal(prev => ({ ...prev, open: false, applying: false, error: '' }))
  }, [])

  const applyShaderChange = useCallback(async () => {
    const applyReq = pendingShaderApply || { game_id: shaderModal.gameId, shader_name: shaderModal.shaderName, emulator: shaderModal.emulator }
    const { game_id, shader_name, emulator } = applyReq
    if (!game_id || !shader_name || !emulator) return
    try {
      setShaderModal(prev => ({ ...prev, applying: true, error: '' }))
      const resp = await fetch('/api/launchbox/shaders/apply', {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
          'x-scope': 'config',
          'x-device-id': deviceId,
          'x-panel': 'launchbox'
        },
        body: JSON.stringify({ game_id, shader_name, emulator })
      })
      const result = await resp.json().catch(() => ({}))
      if (result?.success) {
        addMessage(` Shader applied successfully! Backup saved at ${result?.backup_path || 'none'}`, 'assistant')
        showToast('Shader applied')
        closeShaderPreview()
      } else {
        const msg = result?.error || 'Failed to apply shader'
        addMessage(` Failed to apply shader: ${msg}`, 'assistant')
        setShaderModal(prev => ({ ...prev, applying: false, error: msg }))
        showToast('Shader apply failed')
      }
    } catch (e) {
      setShaderModal(prev => ({ ...prev, applying: false, error: e?.message || String(e) }))
      showToast('Shader apply error')
    }
    finally {
      setShaderPreview(null)
      setPendingShaderApply(null)
    }
  }, [pendingShaderApply, shaderModal, deviceId, addMessage, showToast, closeShaderPreview])

  const removeShaderBinding = useCallback(async () => {
    const { gameId, emulator } = shaderModal
    if (!gameId) return
    try {
      setShaderModal(prev => ({ ...prev, applying: true, error: '' }))
      const qs = emulator ? `?emulator=${encodeURIComponent(emulator)}` : ''
      const resp = await fetch(`/api/launchbox/shaders/game/${encodeURIComponent(gameId)}${qs}`, {
        method: 'DELETE',
        headers: {
          'x-scope': 'config',
          'x-device-id': deviceId,
          'x-panel': 'launchbox'
        }
      })
      const result = await resp.json().catch(() => ({}))
      if (result?.success) {
        const count = Number(result?.removed_count || 1)
        addMessage(`Removed ${count} shader binding(s) for ${gameId}`, 'assistant')
        showToast('Shader removed')
        closeShaderPreview()
      } else {
        const msg = result?.error || 'Failed to remove shader'
        setShaderModal(prev => ({ ...prev, applying: false, error: msg }))
        showToast('Shader remove failed')
      }
    } catch (e) {
      setShaderModal(prev => ({ ...prev, applying: false, error: e?.message || String(e) }))
      showToast('Shader remove error')
    }
  }, [shaderModal, deviceId, addMessage, showToast, closeShaderPreview])

  const maybeHandleShaderToolCalls = useCallback((toolCalls, aiText = '') => {
    try {
      const arr = Array.isArray(toolCalls) ? toolCalls : []
      for (const tc of arr) {
        if (!tc || tc.name !== 'manage_shader') continue
        const action = tc.input?.action
        if (action === 'preview') {
          openShaderPreview({
            gameId: tc.input?.game_id,
            shaderName: tc.input?.shader_name,
            // Prefer emulator returned by the tool (may switch mame<->retroarch)
            emulator: (tc.result && tc.result.emulator) || tc.input?.emulator,
            diff: tc.result?.diff,
            old: tc.result?.old,
            new: tc.result?.new
          })
          break
        }
        if (action === 'apply') {
          const ok = Boolean(tc.result?.success)
          const backup = tc.result?.backup_path || 'none'
          if (ok) {
            addMessage(` Shader applied successfully! Backup saved at ${backup}`, 'assistant')
            showToast('Shader applied')
            setShaderPreview(null)
            setPendingShaderApply(null)
            closeShaderPreview()
          } else {
            const msg = tc.result?.error || 'unknown error'
            addMessage(` Failed to apply shader: ${msg}`, 'assistant')
            showToast('Shader apply failed')
          }
        }
        if (action === 'remove') {
          const count = Number(tc.result?.removed_count || 0)
          if (count > 0) showToast(`Removed ${count} shader binding(s)`)
        }
      }
      // Fallback detection if AI text mentions preview
      if (typeof aiText === 'string' && (aiText.includes('preview_ready') || aiText.toLowerCase().includes('shader preview'))) {
        // Best-effort: open empty modal to prompt user
        setShaderModal(prev => ({ ...prev, open: true }))
      }
    } catch (e) {
      console.warn('[LaunchBox UI] manage_shader handling error:', e)
    }
  }, [openShaderPreview, showToast])

  // Cancel shader preview — used by the JSX cancel button
  const cancelShaderPreview = useCallback(() => {
    addMessage('Shader change cancelled.', 'assistant')
    setShaderPreview(null)
    setPendingShaderApply(null)
    closeShaderPreview()
  }, [addMessage, closeShaderPreview])

  return {
    shaderModal,
    shaderPreview,
    pendingShaderApply,
    maybeHandleShaderToolCalls,
    applyShaderChange,
    closeShaderPreview,
    openShaderPreview,
    removeShaderBinding,
    cancelShaderPreview,
  }
}

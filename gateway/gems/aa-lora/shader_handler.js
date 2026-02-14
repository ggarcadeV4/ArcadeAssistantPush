/**
 * Shader Handler Module - manage_shader tool implementation
 * Part of: aa-lora gem (Day 2 Final Transplant)
 * 
 * Extracted from launchboxAI.js lines 967-1250
 * 
 * Handles: get_current, preview, apply, remove shader actions
 * Uses dependency injection for backend URL and headers
 * 
 * REDLINES: 
 * - Does NOT touch ledwiz_driver.py or MAME JOYCODE logic
 * - API contract maintained via parent index.js
 */

/**
 * Context object for shader operations (dependency injection)
 * @typedef {Object} ShaderContext
 * @property {string} backendUrl - FastAPI backend URL
 * @property {Object} headers - Request headers including x-device-id
 */

/**
 * Get current shader for a game
 * @param {ShaderContext} ctx 
 * @param {string} gameId 
 * @returns {Promise<Object>}
 */
export async function getCurrentShader(ctx, gameId) {
    const { backendUrl, headers = {} } = ctx;
    const response = await fetch(`${backendUrl}/api/launchbox/shaders/game/${encodeURIComponent(gameId)}`, {
        headers: {
            'x-scope': 'state',
            'x-device-id': headers['x-device-id'] || 'unknown',
            'x-panel': 'launchbox'
        }
    });
    return response.json().catch(() => ({}));
}

/**
 * Preview shader changes
 * @param {ShaderContext} ctx 
 * @param {Object} args - { game_id, shader_name, emulator }
 * @returns {Promise<Object>}
 */
export async function previewShader(ctx, args) {
    const { backendUrl, headers = {} } = ctx;
    const { game_id, shader_name, emulator } = args;

    if (!shader_name || !emulator) {
        return { error: 'shader_name and emulator required for preview action' };
    }

    let response = await fetch(`${backendUrl}/api/launchbox/shaders/preview`, {
        method: 'POST',
        headers: {
            'Content-Type': 'application/json',
            'x-scope': 'state',
            'x-device-id': headers['x-device-id'] || 'unknown',
            'x-panel': 'launchbox'
        },
        body: JSON.stringify({ game_id, shader_name, emulator })
    });
    let preview = await response.json().catch(() => ({}));

    // Fallback: if shader not found, try alternate emulator based on catalog
    if (preview?.error && /not found/i.test(preview.error)) {
        const fallbackResult = await tryShaderFallback(ctx, args, 'preview');
        if (fallbackResult) {
            preview = fallbackResult.result;
            args.emulator = fallbackResult.emulator;
            if (fallbackResult.shader_name) args.shader_name = fallbackResult.shader_name;
        }
    }

    return preview;
}

/**
 * Apply shader to game
 * @param {ShaderContext} ctx 
 * @param {Object} args - { game_id, shader_name, emulator }
 * @returns {Promise<{ success: boolean, result: Object, emulator?: string, shader_name?: string }>}
 */
export async function applyShader(ctx, args) {
    const { backendUrl, headers = {} } = ctx;
    const { game_id, shader_name, emulator } = args;

    if (!shader_name || !emulator) {
        return { success: false, result: { error: 'shader_name and emulator required for apply action' } };
    }

    let response = await fetch(`${backendUrl}/api/launchbox/shaders/apply`, {
        method: 'POST',
        headers: {
            'Content-Type': 'application/json',
            'x-scope': 'config',
            'x-device-id': headers['x-device-id'] || 'unknown',
            'x-panel': 'launchbox'
        },
        body: JSON.stringify({ game_id, shader_name, emulator })
    });
    let result = await response.json().catch(() => ({}));
    let success = Boolean(result?.success);

    // Fallback: if not found, try alternate emulator
    if (!success && result?.error && /not found/i.test(result.error)) {
        const fallbackResult = await tryShaderFallback(ctx, args, 'apply');
        if (fallbackResult && fallbackResult.success) {
            result = fallbackResult.result;
            success = true;
            args.emulator = fallbackResult.emulator;
            if (fallbackResult.shader_name) args.shader_name = fallbackResult.shader_name;
        }
    }

    return { success, result, emulator: args.emulator, shader_name: args.shader_name };
}

/**
 * Remove shader from game
 * @param {ShaderContext} ctx 
 * @param {Object} args - { game_id, emulator? }
 * @returns {Promise<{ success: boolean, removedCount: number, result: Object }>}
 */
export async function removeShader(ctx, args) {
    const { backendUrl, headers = {} } = ctx;
    const { game_id, emulator } = args;

    const qs = new URLSearchParams();
    if (emulator) qs.append('emulator', emulator);
    const url = `${backendUrl}/api/launchbox/shaders/game/${encodeURIComponent(game_id)}${qs.toString() ? `?${qs.toString()}` : ''}`;

    const response = await fetch(url, {
        method: 'DELETE',
        headers: {
            'x-scope': 'config',
            'x-device-id': headers['x-device-id'] || 'unknown',
            'x-panel': 'launchbox'
        }
    });
    const result = await response.json().catch(() => ({}));
    const success = Boolean(result?.success);
    const removedCount = Number(result?.removed_count || 0);

    return { success, removedCount, result };
}

/**
 * Try shader fallback on alternate emulator
 * @param {ShaderContext} ctx 
 * @param {Object} args 
 * @param {string} action - 'preview' or 'apply'
 * @returns {Promise<Object|null>}
 */
async function tryShaderFallback(ctx, args, action) {
    const { backendUrl, headers = {} } = ctx;
    const { game_id, shader_name, emulator } = args;

    try {
        const catResp = await fetch(`${backendUrl}/api/launchbox/shaders/available`, {
            headers: {
                'x-scope': 'state',
                'x-panel': 'launchbox',
                'x-device-id': headers['x-device-id'] || 'unknown'
            }
        });
        const catalog = await catResp.json().catch(() => ({}));
        const inRA = Array.isArray(catalog?.retroarch) && catalog.retroarch.some(s => s?.name === shader_name);
        const inMame = Array.isArray(catalog?.mame) && catalog.mame.some(s => s?.name === shader_name);

        let effectiveEmulator = emulator;
        if (inRA && emulator !== 'retroarch') effectiveEmulator = 'retroarch';
        else if (inMame && emulator !== 'mame') effectiveEmulator = 'mame';

        if (effectiveEmulator !== emulator) {
            const endpoint = action === 'preview' ? 'preview' : 'apply';
            const retry = await fetch(`${backendUrl}/api/launchbox/shaders/${endpoint}`, {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json',
                    'x-scope': action === 'preview' ? 'state' : 'config',
                    'x-device-id': headers['x-device-id'] || 'unknown',
                    'x-panel': 'launchbox'
                },
                body: JSON.stringify({ game_id, shader_name, emulator: effectiveEmulator })
            });
            const retryBody = await retry.json().catch(() => ({}));

            if (action === 'preview' && retry.ok && (retryBody?.diff || retryBody?.new)) {
                return { result: retryBody, emulator: effectiveEmulator };
            }
            if (action === 'apply' && retry.ok && retryBody?.success) {
                return { success: true, result: retryBody, emulator: effectiveEmulator };
            }
        }

        // If still failing on mame, try a sensible CRT shader
        if ((effectiveEmulator === 'mame' || emulator === 'mame')) {
            const mameList = Array.isArray(catalog?.mame) ? catalog.mame : [];
            const crtCandidate = mameList.find(s => /crt/i.test(s?.name)) || mameList.find(Boolean);
            if (crtCandidate?.name) {
                const endpoint = action === 'preview' ? 'preview' : 'apply';
                const retry2 = await fetch(`${backendUrl}/api/launchbox/shaders/${endpoint}`, {
                    method: 'POST',
                    headers: {
                        'Content-Type': 'application/json',
                        'x-scope': action === 'preview' ? 'state' : 'config',
                        'x-device-id': headers['x-device-id'] || 'unknown',
                        'x-panel': 'launchbox'
                    },
                    body: JSON.stringify({ game_id, shader_name: crtCandidate.name, emulator: 'mame' })
                });
                const retryBody2 = await retry2.json().catch(() => ({}));

                if (action === 'preview' && retry2.ok && (retryBody2?.diff || retryBody2?.new)) {
                    return { result: retryBody2, emulator: 'mame', shader_name: crtCandidate.name };
                }
                if (action === 'apply' && retry2.ok && retryBody2?.success) {
                    return { success: true, result: retryBody2, emulator: 'mame', shader_name: crtCandidate.name };
                }
            }
        }
    } catch (_) {
        // Ignore fallback failures
    }

    return null;
}

/**
 * Execute manage_shader tool call
 * @param {ShaderContext} ctx 
 * @param {Object} toolUse - Tool use block from Claude
 * @returns {Promise<{ toolResult: Object, shaderApplied: boolean }>}
 */
export async function executeManageShader(ctx, toolUse) {
    const args = toolUse.input || {};
    const { action, game_id, shader_name, emulator } = args;
    let shaderApplied = false;

    try {
        if (action === 'get_current') {
            const currentShader = await getCurrentShader(ctx, game_id);
            return {
                toolResult: {
                    type: 'tool_result',
                    tool_use_id: toolUse.id,
                    content: JSON.stringify({
                        status: 'current_shader',
                        game_id,
                        shader: currentShader?.shader ?? currentShader?.shader_name ?? 'none',
                        data: currentShader
                    })
                },
                shaderApplied: false
            };
        }

        if (action === 'preview') {
            const preview = await previewShader(ctx, args);
            const contentPayload = preview?.error
                ? {
                    status: 'error',
                    game_id,
                    shader_name: args.shader_name || shader_name,
                    emulator: args.emulator || emulator,
                    message: preview.error
                }
                : {
                    status: 'preview_ready',
                    game_id,
                    shader_name: args.shader_name || shader_name,
                    emulator: args.emulator || emulator,
                    diff: preview?.diff,
                    old: preview?.old,
                    new: preview?.new,
                    message: 'Show this preview to the user and ask for confirmation before applying.'
                };

            return {
                toolResult: {
                    type: 'tool_result',
                    tool_use_id: toolUse.id,
                    content: JSON.stringify(contentPayload)
                },
                shaderApplied: false
            };
        }

        if (action === 'apply') {
            const { success, result } = await applyShader(ctx, args);
            const msg = success
                ? `Shader '${shader_name}' applied successfully. Backup: ${result?.backup_path || 'none'}`
                : `Failed to apply shader: ${result?.error || 'unknown error'}`;

            return {
                toolResult: {
                    type: 'tool_result',
                    tool_use_id: toolUse.id,
                    content: JSON.stringify({
                        status: success ? 'applied' : 'error',
                        game_id,
                        shader_name,
                        emulator: args.emulator || emulator,
                        backup_path: result?.backup_path,
                        message: msg
                    })
                },
                shaderApplied: success
            };
        }

        if (action === 'remove') {
            const { success, removedCount } = await removeShader(ctx, args);
            const msg = success
                ? `Removed ${removedCount} shader binding(s) for ${game_id}`
                : `Failed to remove shader: unknown error`;

            return {
                toolResult: {
                    type: 'tool_result',
                    tool_use_id: toolUse.id,
                    content: JSON.stringify({
                        status: success ? 'removed' : 'error',
                        game_id,
                        removed_count: removedCount,
                        message: msg
                    })
                },
                shaderApplied: false
            };
        }

        // Unknown action
        return {
            toolResult: {
                type: 'tool_result',
                tool_use_id: toolUse.id,
                content: JSON.stringify({ status: 'error', message: `Unknown action: ${action}` })
            },
            shaderApplied: false
        };

    } catch (e) {
        return {
            toolResult: {
                type: 'tool_result',
                tool_use_id: toolUse.id,
                content: JSON.stringify({ status: 'error', message: e.message })
            },
            shaderApplied: false
        };
    }
}

export default {
    getCurrentShader,
    previewShader,
    applyShader,
    removeShader,
    executeManageShader
};

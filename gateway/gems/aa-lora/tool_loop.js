/**
 * Tool Loop Module - AI tool calling loop implementation
 * Part of: aa-lora gem (Day 2 Final Transplant)
 * 
 * Extracted from launchboxAI.js executeToolCallingLoop (lines 886-1352)
 * 
 * Implements the Anthropic tool calling pattern:
 * 1. Call AI with user message
 * 2. If stop_reason === 'tool_use': execute tools, build results, call again
 * 3. Repeat until stop_reason !== 'tool_use'
 * 4. Return final text response
 * 
 * REDLINES: 
 * - Does NOT touch ledwiz_driver.py or MAME JOYCODE logic
 * - API contract maintained by parent index.js
 */

import { executeManageShader } from './shader_handler.js';

/**
 * Tool environment context (dependency injection)
 * @typedef {Object} ToolEnv
 * @property {string} backendUrl - FastAPI backend URL
 * @property {Object} headers - Request headers
 * @property {Object} tools - Tool function map (launchboxTools)
 * @property {Function} callAI - AI API call function
 */

/**
 * Tool loop result
 * @typedef {Object} ToolLoopResult
 * @property {string} finalText - Final AI response text
 * @property {Array} toolCallsMade - List of tool calls made
 * @property {number} rounds - Number of AI conversation rounds
 * @property {boolean} gameLaunched - Whether a game was launched
 * @property {Array} messages - Final conversation messages
 * @property {string} provider - AI provider used
 * @property {string} model - AI model used
 * @property {number} latencyMs - Total latency in milliseconds
 * @property {Object} usage - Token usage { prompt_tokens, completion_tokens }
 */

/**
 * Execute the tool calling loop until AI stops requesting tools
 * 
 * @param {string} systemPrompt - System prompt for AI
 * @param {Array} messages - Conversation messages
 * @param {ToolEnv} toolEnv - Tool environment context
 * @returns {Promise<ToolLoopResult>}
 */
export async function executeToolCallingLoop(systemPrompt, messages, toolEnv = {}) {
    const { tools = {}, callAI } = toolEnv;

    if (!callAI) {
        throw new Error('callAI function required in toolEnv');
    }

    // Ensure content blocks are in Claude format
    if (!Array.isArray(messages) || messages.length === 0) {
        messages = [{ role: 'user', content: [{ type: 'text', text: '' }] }];
    }

    let continueLoop = true;
    let rounds = 0;
    const maxRounds = 10; // Safety limit to prevent infinite loops
    const toolCallsMade = [];
    let finalText = '';
    let gameLaunched = false;

    // Telemetry tracking
    const startTime = Date.now();
    let lastProvider = 'gemini';
    let lastModel = 'gemini-2.5-flash';
    let totalInputTokens = 0;
    let totalOutputTokens = 0;

    // Shader context for manage_shader calls
    const shaderCtx = {
        backendUrl: toolEnv.backendUrl,
        headers: toolEnv.headers || {}
    };

    // Main tool calling loop
    while (continueLoop && rounds < maxRounds) {
        rounds++;
        console.log(`[LaunchBox AI] Round ${rounds}: Calling AI...`);
        try {
            console.log('[LoRa Debug] Pre-call history length:', messages.length);
            console.log('[LoRa Debug] Pre-call last 2:', messages.slice(-2).map(m => ({ role: m.role, types: (Array.isArray(m.content) ? m.content.map(c => c.type) : typeof m.content) })));
        } catch (_) { }

        // Call AI API
        const response = await callAI(systemPrompt, messages);

        // Track provider/model/usage for telemetry
        if (response.provider) lastProvider = response.provider;
        if (response.model) lastModel = response.model;
        if (response.usage) {
            totalInputTokens += response.usage.prompt_tokens || response.usage.input_tokens || 0;
            totalOutputTokens += response.usage.completion_tokens || response.usage.output_tokens || 0;
        }

        console.log(`[LaunchBox AI] Round ${rounds} stop_reason:`, response.stop_reason);

        const responseContent = Array.isArray(response.content)
            ? response.content
            : (typeof response.content === 'string'
                ? [{ type: 'text', text: response.content }]
                : []);

        // Extract text content from this response
        const textBlocks = responseContent.filter(b => b.type === 'text');
        const currentText = textBlocks.map(b => b.text).join('\n');
        if (currentText) {
            finalText = currentText; // Keep the latest text
        }

        // Check if AI wants to use tools
        if (response.stop_reason === 'tool_use') {
            // Extract tool use blocks
            const toolUseBlocks = responseContent.filter(b => b.type === 'tool_use');

            console.log(`[LaunchBox AI] Round ${rounds}: ${toolUseBlocks.length} tool(s) requested`);

            // Add assistant's response to conversation (must include ALL content blocks)
            messages.push({
                role: 'assistant',
                content: responseContent
            });
            try { console.log('[LoRa Debug] After assistant tool_use, history length:', messages.length); } catch (_) { }

            // Execute all tools and build tool_result blocks
            const toolResultBlocks = [];
            // Workflow guard flags
            const hasShaderPreview = toolUseBlocks.some(b => b.name === 'manage_shader' && (b.input?.action === 'preview'));
            let shaderAppliedThisRound = false;

            for (const toolUse of toolUseBlocks) {
                console.log(`[LaunchBox AI] Executing tool: ${toolUse.name}`, toolUse.input);

                // Special-case: manage_shader tool handled by shader_handler module
                if (toolUse.name === 'manage_shader') {
                    const { toolResult, shaderApplied } = await executeManageShader(shaderCtx, toolUse);
                    toolResultBlocks.push(toolResult);
                    toolCallsMade.push({ name: 'manage_shader', input: toolUse.input, result: JSON.parse(toolResult.content) });
                    if (shaderApplied) shaderAppliedThisRound = true;
                    continue;
                }

                // Execute the tool via shared module
                const toolFunction = tools[toolUse.name];
                if (!toolFunction) {
                    console.error(`[LaunchBox AI] Unknown tool: ${toolUse.name}`);

                    // Send error as tool result
                    toolResultBlocks.push({
                        type: 'tool_result',
                        tool_use_id: toolUse.id,
                        content: JSON.stringify({
                            success: false,
                            error: `Unknown tool: ${toolUse.name}`
                        })
                    });
                    continue;
                }

                let toolResult;
                try {
                    // Enforce order: do not launch if a shader preview is pending and not yet applied
                    if (toolUse.name === 'launch_game' && hasShaderPreview && !shaderAppliedThisRound) {
                        toolResult = {
                            success: false,
                            error: 'shader_preview_pending',
                            message: 'Shader preview requested. Apply (or cancel) the shader before launching the game.'
                        };
                    } else {
                        // Optional: small delay if shader was just applied so user can read confirmation
                        if (toolUse.name === 'launch_game' && shaderAppliedThisRound) {
                            await new Promise(resolve => setTimeout(resolve, 3000));
                        }
                        toolResult = await toolFunction(toolUse.input);
                    }
                } catch (error) {
                    console.error(`[LaunchBox AI] Tool execution error:`, error);
                    toolResult = {
                        success: false,
                        error: error.message
                    };
                }

                console.log(`[LaunchBox AI] Tool result:`, JSON.stringify(toolResult).substring(0, 200));

                // Track if a game was launched
                if (toolUse.name === 'launch_game' && toolResult.success) {
                    gameLaunched = true;
                }

                // Track tool calls for response
                toolCallsMade.push({
                    name: toolUse.name,
                    input: toolUse.input,
                    result: toolResult
                });

                // Build tool_result block
                toolResultBlocks.push({
                    type: 'tool_result',
                    tool_use_id: toolUse.id,
                    content: JSON.stringify(toolResult)
                });
            }

            // Add tool results as a user message
            messages.push({
                role: 'user',
                content: toolResultBlocks
            });
            try { console.log('[LoRa Debug] After tool_result, history length:', messages.length); } catch (_) { }

            // Continue loop - AI will process tool results
            continueLoop = true;

        } else {
            // AI finished (stop_reason is 'end_turn' or 'max_tokens')
            console.log(`[LaunchBox AI] Conversation complete after ${rounds} round(s)`);
            continueLoop = false;
        }
    }

    // Safety check
    if (rounds >= maxRounds) {
        console.warn(`[LaunchBox AI] Hit max rounds (${maxRounds}), stopping loop`);
    }

    return {
        finalText: finalText || 'I processed your request.',
        toolCallsMade,
        rounds,
        gameLaunched,
        messages,
        // Telemetry data
        provider: lastProvider,
        model: lastModel,
        latencyMs: Date.now() - startTime,
        usage: {
            prompt_tokens: totalInputTokens,
            completion_tokens: totalOutputTokens
        }
    };
}

export default {
    executeToolCallingLoop
};

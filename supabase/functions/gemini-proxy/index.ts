// Arcade Assistant - Gemini AI Proxy Edge Function
// Proxies AI requests to Google's Gemini API using Supabase secrets
// Supports function calling (tools) for LoRa and other agents
import "jsr:@supabase/functions-js/edge-runtime.d.ts";

// CORS headers for local development
const corsHeaders = {
    'Access-Control-Allow-Origin': '*',
    'Access-Control-Allow-Headers': 'authorization, x-client-info, apikey, content-type, x-scope, x-device-id',
};

interface ClaudeTool {
    name: string;
    description?: string;
    input_schema?: {
        type: string;
        properties?: Record<string, unknown>;
        required?: string[];
    };
}

interface GeminiRequest {
    messages: Array<{
        role: string;
        content: string | Array<{
            type: string;
            text?: string;
            id?: string;  // tool_use id
            tool_use_id?: string;
            name?: string;
            input?: unknown;
            content?: string | unknown;  // tool_result content
        }>
    }>;
    max_tokens?: number;
    temperature?: number;
    model?: string;
    system?: string;
    tools?: ClaudeTool[];
}

interface GeminiContent {
    role: string;
    parts: Array<{ text?: string; functionCall?: { name: string; args: Record<string, unknown> }; functionResponse?: { name: string; response: { content: unknown } } }>;
}

interface GeminiFunctionDeclaration {
    name: string;
    description?: string;
    parameters?: {
        type: string;
        properties?: Record<string, unknown>;
        required?: string[];
    };
}

/**
 * Convert Claude tool format to Gemini functionDeclarations
 */
function convertToolsToGemini(claudeTools: ClaudeTool[]): GeminiFunctionDeclaration[] {
    return claudeTools.map(tool => ({
        name: tool.name,
        description: tool.description || `Execute ${tool.name}`,
        parameters: tool.input_schema ? {
            type: tool.input_schema.type || 'object',
            properties: tool.input_schema.properties || {},
            required: tool.input_schema.required || []
        } : { type: 'object', properties: {} }
    }));
}

Deno.serve(async (req) => {
    // Handle CORS preflight
    if (req.method === 'OPTIONS') {
        return new Response('ok', { headers: corsHeaders });
    }

    try {
        // Get Google API key from Supabase secrets
        const GOOGLE_API_KEY = Deno.env.get("GOOGLE_API_KEY");

        if (!GOOGLE_API_KEY || GOOGLE_API_KEY === 'placeholder-boot-only') {
            return new Response(
                JSON.stringify({
                    error: "Google API key not configured in Supabase secrets",
                    code: "NOT_CONFIGURED"
                }),
                {
                    status: 501,
                    headers: { ...corsHeaders, 'Content-Type': 'application/json' }
                }
            );
        }

        // Parse request body
        const body = await req.json() as GeminiRequest;

        // Validate required fields
        if (!body?.messages || !Array.isArray(body.messages) || body.messages.length === 0) {
            return new Response(
                JSON.stringify({
                    error: "Missing required field: messages (array)"
                }),
                {
                    status: 400,
                    headers: { ...corsHeaders, 'Content-Type': 'application/json' }
                }
            );
        }

        // Convert messages to Gemini format
        // Gemini uses "user" and "model" roles, with content as parts array
        const contents: GeminiContent[] = [];
        let systemInstruction: string | undefined;

        // Track tool_use blocks to map tool_use_id -> function name
        // This is critical: Gemini's functionResponse needs the actual function name,
        // but Claude's tool_result only provides tool_use_id
        const toolUseIdToName: Record<string, string> = {};

        for (const msg of body.messages) {
            if (msg.role === 'system') {
                // Gemini handles system prompts via systemInstruction
                if (typeof msg.content === 'string') {
                    systemInstruction = msg.content;
                }
            } else if (msg.role === 'tool') {
                // Tool result - convert to Gemini functionResponse format
                // Claude sends: { role: 'user', content: [{ type: 'tool_result', tool_use_id, content }] }
                // We need to handle this in the next message parsing
                continue;
            } else {
                const parts: GeminiContent['parts'] = [];

                // Handle both string content and Claude's content array format
                if (typeof msg.content === 'string') {
                    // Simple string message
                    parts.push({ text: msg.content });
                } else if (Array.isArray(msg.content)) {
                    // Claude's content blocks format
                    for (const block of msg.content) {
                        if (block.type === 'text' && block.text) {
                            parts.push({ text: block.text });
                        } else if (block.type === 'tool_use') {
                            // Claude tool_use block - convert to Gemini functionCall
                            // Also track the mapping from id -> name for tool_result resolution
                            const funcName = block.name || '';
                            const toolId = block.id || '';
                            if (toolId && funcName) {
                                toolUseIdToName[toolId] = funcName;
                            }
                            parts.push({
                                functionCall: {
                                    name: funcName,
                                    args: (block.input as Record<string, unknown>) || {}
                                }
                            });
                        } else if (block.type === 'tool_result') {
                            // Claude tool_result - convert to Gemini functionResponse
                            // CRITICAL FIX: Use the tracked function name, not tool_use_id
                            const toolId = block.tool_use_id || '';
                            const funcName = toolUseIdToName[toolId] || block.name || toolId || 'unknown';

                            // Parse content - it may be stringified JSON
                            let responseContent = block.content || block.text || '';
                            if (typeof responseContent === 'string') {
                                try {
                                    responseContent = JSON.parse(responseContent);
                                } catch {
                                    // Keep as string if not valid JSON
                                }
                            }

                            parts.push({
                                functionResponse: {
                                    name: funcName,
                                    response: { content: responseContent }
                                }
                            });
                        }
                    }
                }

                if (parts.length > 0) {
                    // Skip messages with empty or meaningless parts (causes 400 Bad Request)
                    // A part is meaningful if it has: text with content, or a function call/response
                    const hasMeaningfulContent = parts.some(p =>
                        (p.text && p.text.trim().length > 0) ||
                        p.functionCall ||
                        p.functionResponse
                    );

                    if (!hasMeaningfulContent) {
                        continue;  // Skip this message entirely
                    }

                    // Gemini requires function responses to be from 'user' role (confusingly)
                    // but functionCall parts should be from 'model' role
                    const hasFunctionResponse = parts.some(p => p.functionResponse);
                    const hasFunctionCall = parts.some(p => p.functionCall);

                    let role: string;
                    if (hasFunctionCall) {
                        role = 'model';  // Assistant made the function call
                    } else if (hasFunctionResponse) {
                        role = 'user';   // User provides function results (Gemini's convention)
                    } else {
                        role = msg.role === 'assistant' ? 'model' : 'user';
                    }

                    contents.push({ role, parts });
                }
            }
        }

        // Use system from body if provided (takes precedence)
        if (body.system) {
            systemInstruction = body.system;
        }

        // Prepare Gemini API request
        // Use consistent model name (not -exp which may be deprecated)
        const model = body.model || "gemini-2.0-flash";
        const geminiRequest: Record<string, unknown> = {
            contents,
            generationConfig: {
                maxOutputTokens: body.max_tokens || 1024,
                temperature: body.temperature ?? 0.7,
            }
        };

        // Add system instruction if provided
        if (systemInstruction) {
            geminiRequest.systemInstruction = {
                parts: [{ text: systemInstruction }]
            };
        }

        // Add function declarations if tools are provided
        if (body.tools && Array.isArray(body.tools) && body.tools.length > 0) {
            const functionDeclarations = convertToolsToGemini(body.tools);
            geminiRequest.tools = [{
                functionDeclarations
            }];
            // Enable automatic function calling mode
            geminiRequest.toolConfig = {
                functionCallingConfig: {
                    mode: "AUTO"
                }
            };
            console.log(`[Gemini Proxy] Added ${functionDeclarations.length} function declarations`);
        }

        console.log(`[Gemini Proxy] Forwarding request with ${contents.length} messages to ${model}`);

        // Call Gemini API
        const geminiUrl = `https://generativelanguage.googleapis.com/v1beta/models/${model}:generateContent?key=${GOOGLE_API_KEY}`;

        const geminiResponse = await fetch(geminiUrl, {
            method: "POST",
            headers: {
                "Content-Type": "application/json",
            },
            body: JSON.stringify(geminiRequest)
        });

        if (!geminiResponse.ok) {
            const errorText = await geminiResponse.text();
            console.error(`[Gemini Proxy] API error (${geminiResponse.status}):`, errorText);

            return new Response(
                JSON.stringify({
                    error: `Gemini API error: ${geminiResponse.status}`,
                    detail: errorText
                }),
                {
                    status: geminiResponse.status,
                    headers: { ...corsHeaders, 'Content-Type': 'application/json' }
                }
            );
        }

        const geminiData = await geminiResponse.json();

        // Extract content from Gemini response
        const candidate = geminiData.candidates?.[0];
        const responseParts = candidate?.content?.parts || [];
        const finishReason = candidate?.finishReason || 'STOP';

        // Convert Gemini response to Claude-compatible format
        // This allows the Gateway's executeToolCallingLoop to work unchanged
        const claudeContent: Array<{ type: string; text?: string; id?: string; name?: string; input?: unknown }> = [];
        let hasToolUse = false;

        for (const part of responseParts) {
            if (part.text) {
                claudeContent.push({ type: 'text', text: part.text });
            } else if (part.functionCall) {
                hasToolUse = true;
                claudeContent.push({
                    type: 'tool_use',
                    id: `toolu_${Date.now()}_${Math.random().toString(36).slice(2)}`,
                    name: part.functionCall.name,
                    input: part.functionCall.args || {}
                });
            }
        }

        // If no content, add empty text
        if (claudeContent.length === 0) {
            claudeContent.push({ type: 'text', text: '' });
        }

        // Determine stop_reason in Claude format
        let stopReason = 'end_turn';
        if (hasToolUse) {
            stopReason = 'tool_use';
        } else if (finishReason === 'MAX_TOKENS') {
            stopReason = 'max_tokens';
        } else if (finishReason === 'SAFETY') {
            stopReason = 'stop_sequence';
        }

        // Build Claude-compatible response
        const unifiedResponse = {
            id: `gemini-${Date.now()}`,
            type: 'message',
            role: 'assistant',
            provider: 'gemini',
            model: model,
            content: claudeContent,
            stop_reason: stopReason,
            stop_sequence: null,
            usage: {
                input_tokens: geminiData.usageMetadata?.promptTokenCount || 0,
                output_tokens: geminiData.usageMetadata?.candidatesTokenCount || 0,
            }
        };

        console.log(`[Gemini Proxy] Success - ${unifiedResponse.usage.input_tokens} + ${unifiedResponse.usage.output_tokens} tokens, stop_reason: ${stopReason}`);

        return new Response(
            JSON.stringify(unifiedResponse),
            {
                status: 200,
                headers: { ...corsHeaders, 'Content-Type': 'application/json' }
            }
        );

    } catch (error) {
        console.error("[Gemini Proxy] Error:", error);

        return new Response(
            JSON.stringify({
                error: error instanceof Error ? error.message : "Internal server error"
            }),
            {
                status: 500,
                headers: { ...corsHeaders, 'Content-Type': 'application/json' }
            }
        );
    }
});

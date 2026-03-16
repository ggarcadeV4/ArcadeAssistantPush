// Arcade Assistant - Anthropic AI Proxy Edge Function
// Proxies AI requests to Anthropic API using Supabase secrets
import "jsr:@supabase/functions-js/edge-runtime.d.ts";

// CORS headers for local development
const corsHeaders = {
  'Access-Control-Allow-Origin': '*',
  'Access-Control-Allow-Headers': 'authorization, x-client-info, apikey, content-type, x-scope, x-device-id',
};

interface AnthropicRequest {
  messages: Array<{ role: string; content: unknown }>;
  max_tokens?: number;
  temperature?: number;
  model?: string;
  system?: string;
  tools?: unknown[];
}

Deno.serve(async (req) => {
  // Handle CORS preflight
  if (req.method === 'OPTIONS') {
    return new Response('ok', { headers: corsHeaders });
  }

  try {
    // Get Anthropic API key from Supabase secrets
    const ANTHROPIC_API_KEY = Deno.env.get("ANTHROPIC_API_KEY");

    if (!ANTHROPIC_API_KEY || ANTHROPIC_API_KEY === 'placeholder-boot-only') {
      return new Response(
        JSON.stringify({
          error: "Anthropic API key not configured in Supabase secrets",
          code: "NOT_CONFIGURED"
        }),
        {
          status: 501,
          headers: { ...corsHeaders, 'Content-Type': 'application/json' }
        }
      );
    }

    // Parse request body
    const body = await req.json() as AnthropicRequest;

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

    // Extract system messages from inline messages and promote to top-level system parameter
    // Anthropic Messages API does NOT accept role: 'system' in the messages array
    const systemMessages: string[] = [];
    const cleanedMessages = body.messages.filter(msg => {
      if (msg.role === 'system') {
        const text = typeof msg.content === 'string' ? msg.content : '';
        if (text) systemMessages.push(text);
        return false; // Remove from messages array
      }
      return true;
    });

    // Build system prompt: prefer explicit body.system, then inline system messages
    const systemPrompt = body.system || (systemMessages.length > 0 ? systemMessages.join('\n\n') : undefined);

    // Prepare Anthropic API request - pass through all fields for tool calling support
    const anthropicRequest: Record<string, unknown> = {
      model: body.model || "claude-3-5-sonnet-20241022",
      max_tokens: body.max_tokens || 500,
      messages: cleanedMessages
    };

    // Include optional fields if provided (critical for tool calling)
    if (systemPrompt) anthropicRequest.system = systemPrompt;
    if (body.tools) anthropicRequest.tools = body.tools;
    if (body.temperature !== undefined) anthropicRequest.temperature = body.temperature;

    console.log(`[Anthropic Proxy] Forwarding request with ${body.messages.length} messages`);

    // Call Anthropic API
    const anthropicResponse = await fetch("https://api.anthropic.com/v1/messages", {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
        "x-api-key": ANTHROPIC_API_KEY,
        "anthropic-version": "2023-06-01"
      },
      body: JSON.stringify(anthropicRequest)
    });

    if (!anthropicResponse.ok) {
      const errorText = await anthropicResponse.text();
      console.error(`[Anthropic Proxy] API error (${anthropicResponse.status}):`, errorText);

      return new Response(
        JSON.stringify({
          error: `Anthropic API error: ${anthropicResponse.status}`,
          detail: errorText
        }),
        {
          status: anthropicResponse.status,
          headers: { ...corsHeaders, 'Content-Type': 'application/json' }
        }
      );
    }

    const anthropicData = await anthropicResponse.json();

    // Pass through the raw Anthropic response to support tool calling
    // The gateway's executeToolCallingLoop expects the full Anthropic format
    // with content array, stop_reason, etc.
    console.log(`[Anthropic Proxy] Success - ${anthropicData.usage?.input_tokens || 0} + ${anthropicData.usage?.output_tokens || 0} tokens`);

    return new Response(
      JSON.stringify(anthropicData),
      {
        status: 200,
        headers: { ...corsHeaders, 'Content-Type': 'application/json' }
      }
    );


  } catch (error) {
    console.error("[Anthropic Proxy] Error:", error);

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

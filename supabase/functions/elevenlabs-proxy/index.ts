// Arcade Assistant - ElevenLabs TTS Proxy Edge Function
// Proxies TTS requests to ElevenLabs API using Supabase secrets
import "jsr:@supabase/functions-js/edge-runtime.d.ts";

// CORS headers for local development
const corsHeaders = {
  'Access-Control-Allow-Origin': '*',
  'Access-Control-Allow-Headers': 'authorization, x-client-info, apikey, content-type, x-scope, x-device-id',
};

interface TTSRequest {
  text: string;
  voice_id?: string;
  model_id?: string;
  stability?: number;
  similarity_boost?: number;
}

Deno.serve(async (req) => {
  // Handle CORS preflight
  if (req.method === 'OPTIONS') {
    return new Response('ok', { headers: corsHeaders });
  }

  try {
    // Get ElevenLabs API key from Supabase secrets
    const ELEVENLABS_API_KEY = Deno.env.get("ELEVENLABS_API_KEY");

    if (!ELEVENLABS_API_KEY || ELEVENLABS_API_KEY === 'placeholder-boot-only') {
      return new Response(
        JSON.stringify({
          error: "ElevenLabs API key not configured in Supabase secrets",
          code: "NOT_CONFIGURED"
        }),
        {
          status: 501,
          headers: { ...corsHeaders, 'Content-Type': 'application/json' }
        }
      );
    }

    // Parse request body
    const body = await req.json() as TTSRequest;

    // Validate required fields
    if (!body?.text || typeof body.text !== 'string' || body.text.trim().length === 0) {
      return new Response(
        JSON.stringify({
          error: "Missing required field: text (non-empty string)"
        }),
        {
          status: 400,
          headers: { ...corsHeaders, 'Content-Type': 'application/json' }
        }
      );
    }

    // Validate text length (ElevenLabs limit)
    if (body.text.length > 5000) {
      return new Response(
        JSON.stringify({
          error: "Text too long (max 5000 characters)"
        }),
        {
          status: 400,
          headers: { ...corsHeaders, 'Content-Type': 'application/json' }
        }
      );
    }

    // Default voice ID (Adam) if not specified
    const voiceId = body.voice_id || "pNInz6obpgDQGcFmaJgB";
    const modelId = body.model_id || "eleven_monolingual_v1";

    // Prepare ElevenLabs API request
    const elevenLabsRequest = {
      text: body.text,
      model_id: modelId,
      voice_settings: {
        stability: body.stability ?? 0.5,
        similarity_boost: body.similarity_boost ?? 0.75
      }
    };

    console.log(`[ElevenLabs Proxy] Generating speech for ${body.text.length} characters (voice: ${voiceId})`);

    // Call ElevenLabs API
    const elevenLabsResponse = await fetch(
      `https://api.elevenlabs.io/v1/text-to-speech/${voiceId}`,
      {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
          "xi-api-key": ELEVENLABS_API_KEY
        },
        body: JSON.stringify(elevenLabsRequest)
      }
    );

    if (!elevenLabsResponse.ok) {
      const errorText = await elevenLabsResponse.text();
      console.error(`[ElevenLabs Proxy] API error (${elevenLabsResponse.status}):`, errorText);

      return new Response(
        JSON.stringify({
          error: `ElevenLabs API error: ${elevenLabsResponse.status}`,
          detail: errorText
        }),
        {
          status: elevenLabsResponse.status,
          headers: { ...corsHeaders, 'Content-Type': 'application/json' }
        }
      );
    }

    // Stream audio response
    const audioData = await elevenLabsResponse.arrayBuffer();

    console.log(`[ElevenLabs Proxy] Success - Generated ${audioData.byteLength} bytes of audio`);

    // Return audio with appropriate headers
    return new Response(audioData, {
      status: 200,
      headers: {
        ...corsHeaders,
        'Content-Type': 'audio/mpeg',
        'Content-Length': audioData.byteLength.toString()
      }
    });

  } catch (error) {
    console.error("[ElevenLabs Proxy] Error:", error);

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

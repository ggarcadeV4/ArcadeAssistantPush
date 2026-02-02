// Arcade Assistant - Send Command Edge Function
// LEGACY FUNCTION - DISABLED
// This function uses the old Fleet Manager schema (devices/commands/telemetry tables).
// Canonical replacement: Use cabinet / command_queue / cabinet_telemetry tables via Python backend.
// See: backend/services/supabase_client.py
import "jsr:@supabase/functions-js/edge-runtime.d.ts";

// CORS headers for local development
const corsHeaders = {
  'Access-Control-Allow-Origin': '*',
  'Access-Control-Allow-Headers': 'authorization, x-client-info, apikey, content-type',
};

Deno.serve(async (req: Request) => {
  // Handle CORS preflight
  if (req.method === 'OPTIONS') {
    return new Response('ok', { headers: corsHeaders });
  }

  // LEGACY FUNCTION DISABLED - Use canonical tables via Python backend
  return new Response(
    JSON.stringify({
      error: "LEGACY FUNCTION DISABLED: send_command uses deprecated schema. Use command_queue table via Python backend.",
      canonical_tables: {
        devices: "cabinet",
        commands: "command_queue",
        telemetry: "cabinet_telemetry"
      }
    }),
    {
      status: 410, // Gone
      headers: { ...corsHeaders, 'Content-Type': 'application/json' }
    }
  );
});

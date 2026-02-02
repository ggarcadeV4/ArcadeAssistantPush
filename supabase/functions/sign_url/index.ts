// Arcade Assistant - Sign URL Edge Function
// Returns temporary signed URLs for private storage buckets
import "jsr:@supabase/functions-js/edge-runtime.d.ts";
import { createClient } from "npm:@supabase/supabase-js@2";

// CORS headers for local development
const corsHeaders = {
  'Access-Control-Allow-Origin': '*',
  'Access-Control-Allow-Headers': 'authorization, x-client-info, apikey, content-type',
};

interface SignUrlRequest {
  bucket: "updates" | "assets";
  path: string;
  expiresIn?: number;  // seconds, default 10 minutes
}

interface SignUrlResponse {
  url: string;
  expires_at: string;
}

Deno.serve(async (req) => {
  // Handle CORS preflight
  if (req.method === 'OPTIONS') {
    return new Response('ok', { headers: corsHeaders });
  }

  try {
    // Initialize Supabase admin client
    const supabaseUrl = Deno.env.get("SUPABASE_URL");
    const supabaseServiceKey = Deno.env.get("SUPABASE_SERVICE_ROLE_KEY");

    if (!supabaseUrl || !supabaseServiceKey) {
      throw new Error("Missing Supabase environment variables");
    }

    const admin = createClient(supabaseUrl, supabaseServiceKey, {
      auth: { persistSession: false }
    });

    // Parse request body
    const body = await req.json() as SignUrlRequest;

    // Validate required fields
    if (!body?.bucket || !body?.path) {
      return new Response(
        JSON.stringify({
          error: "Missing required fields: bucket and path"
        }),
        {
          status: 400,
          headers: { ...corsHeaders, 'Content-Type': 'application/json' }
        }
      );
    }

    // Validate bucket name
    const validBuckets = ['updates', 'assets'];
    if (!validBuckets.includes(body.bucket)) {
      return new Response(
        JSON.stringify({
          error: `Invalid bucket: ${body.bucket}. Must be one of: ${validBuckets.join(', ')}`
        }),
        {
          status: 400,
          headers: { ...corsHeaders, 'Content-Type': 'application/json' }
        }
      );
    }

    // Default expiry: 10 minutes (600 seconds)
    const expiresIn = body.expiresIn || 600;

    // Validate expiry (max 1 hour for security)
    if (expiresIn < 60 || expiresIn > 3600) {
      return new Response(
        JSON.stringify({
          error: "expiresIn must be between 60 and 3600 seconds"
        }),
        {
          status: 400,
          headers: { ...corsHeaders, 'Content-Type': 'application/json' }
        }
      );
    }

    // Check if file exists
    const { data: fileList, error: listError } = await admin
      .storage
      .from(body.bucket)
      .list(body.path.split('/').slice(0, -1).join('/'), {
        limit: 100,
        search: body.path.split('/').pop()
      });

    if (listError) {
      console.error("Error checking file existence:", listError);
      throw listError;
    }

    if (!fileList || fileList.length === 0) {
      return new Response(
        JSON.stringify({
          error: `File not found: ${body.path} in bucket ${body.bucket}`
        }),
        {
          status: 404,
          headers: { ...corsHeaders, 'Content-Type': 'application/json' }
        }
      );
    }

    // Create signed URL
    const { data, error: signError } = await admin
      .storage
      .from(body.bucket)
      .createSignedUrl(body.path, expiresIn);

    if (signError) {
      console.error("Error creating signed URL:", signError);
      throw signError;
    }

    if (!data?.signedUrl) {
      throw new Error("Failed to generate signed URL");
    }

    // Calculate expiration timestamp
    const expiresAt = new Date(Date.now() + expiresIn * 1000).toISOString();

    console.log(`Signed URL created for ${body.bucket}/${body.path}, expires at ${expiresAt}`);

    // Return success response
    const response: SignUrlResponse = {
      url: data.signedUrl,
      expires_at: expiresAt
    };

    return new Response(
      JSON.stringify(response),
      {
        status: 200,
        headers: { ...corsHeaders, 'Content-Type': 'application/json' }
      }
    );

  } catch (error) {
    console.error("Error in sign_url function:", error);

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

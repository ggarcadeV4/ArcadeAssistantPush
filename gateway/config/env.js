// Use getters to dynamically access process.env at runtime
// This ensures we get the values AFTER dotenv has loaded them
export const env = {
  get ANTHROPIC_API_KEY() {
    return process.env.ANTHROPIC_API_KEY || process.env.CLAUDE_API_KEY || '';
  },
  get OPENAI_API_KEY() {
    return process.env.OPENAI_API_KEY || '';
  },
  get AI_DEFAULT_PROVIDER() {
    return process.env.AI_DEFAULT_PROVIDER || 'claude';
  },
  get AI_TIMEOUT_MS() {
    return Math.max(3000, Math.min(60000, parseInt(process.env.AI_TIMEOUT_MS || '20000', 10)));
  },
  get AI_TIMEOUT_MS_MAX() {
    return Math.max(5000, Math.min(120000, parseInt(process.env.AI_TIMEOUT_MS_MAX || '30000', 10)));
  },
  get AI_MAX_TOKENS() {
    return Math.max(128, Math.min(8192, parseInt(process.env.AI_MAX_TOKENS || '1024', 10)));
  },
  get AI_RETRY_MAX_ATTEMPTS() {
    return Math.max(0, Math.min(5, parseInt(process.env.AI_RETRY_MAX_ATTEMPTS || '3', 10)));
  },
  get AI_RETRY_BASE_MS() {
    return Math.max(100, Math.min(5000, parseInt(process.env.AI_RETRY_BASE_MS || '500', 10)));
  },
  get AI_RPM() {
    return Math.max(1, parseInt(process.env.AI_RPM || '60', 10));
  }
};

export function ensureConfigured(provider) {
  // DEBUG LOGGING
  console.log(`[DEBUG] ensureConfigured check for provider: ${provider}`);
  console.log(`[DEBUG] SUPABASE_URL present: ${!!process.env.SUPABASE_URL}`);
  console.log(`[DEBUG] SUPABASE_SERVICE_ROLE_KEY present: ${!!process.env.SUPABASE_SERVICE_ROLE_KEY}`);

  // Check for Supabase Edge Functions (Golden Drive approach)
  // If Supabase is configured, all providers (claude, gemini, tts) work via proxies
  if (process.env.SUPABASE_URL && process.env.SUPABASE_SERVICE_ROLE_KEY) {
    console.log('[DEBUG] Supabase keys found. Provider available via proxy.');
    return true;
  }

  console.log('[DEBUG] Supabase keys missing. Checking legacy local keys...');
  // Fallback to direct API keys (legacy approach)
  if (provider === 'claude' && !env.ANTHROPIC_API_KEY) {
    console.log('[DEBUG] Legacy ANTHROPIC_API_KEY missing.');
    return false;
  }
  if (provider === 'gpt' && !env.OPENAI_API_KEY) return false;
  if (provider === 'gemini' && !process.env.GOOGLE_API_KEY) {
    console.log('[DEBUG] Legacy GOOGLE_API_KEY missing.');
    return false;
  }
  return true;
}

export function clamp(v, lo, hi) {
  const n = Number.isFinite(v) ? v : lo;
  return Math.max(lo, Math.min(hi, n));
}

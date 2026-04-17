import express from 'express';
import { env } from '../config/env.js';

const router = express.Router();

function normalizeProvider(provider) {
  const p = String(provider || '').toLowerCase().trim();
  if (p === 'openai') return 'gpt';
  if (p === 'google') return 'gemini';
  if (p === 'anthropic') return 'claude';
  return p || 'claude';
}

function resolveConfiguredProviders() {
  const supabaseProxy = Boolean(process.env.SUPABASE_URL && process.env.SUPABASE_SERVICE_ROLE_KEY);
  return {
    proxy: supabaseProxy,
    claude: supabaseProxy || Boolean(env.ANTHROPIC_API_KEY),
    gpt: supabaseProxy || Boolean(env.OPENAI_API_KEY),
    gemini: supabaseProxy || Boolean(process.env.GOOGLE_API_KEY)
  };
}

function resolveActiveProvider(defaultProvider, configured) {
  const normalizedDefault = normalizeProvider(defaultProvider);
  if (configured[normalizedDefault]) return normalizedDefault;
  if (configured.gemini) return 'gemini';
  if (configured.claude) return 'claude';
  if (configured.gpt) return 'gpt';
  return normalizedDefault;
}

function resolveModel(provider) {
  if (provider === 'gemini') return process.env.GEMINI_MODEL || 'gemini-2.5-flash';
  if (provider === 'gpt') return process.env.OPENAI_MODEL || 'gpt-4o-mini';
  return process.env.ANTHROPIC_MODEL || 'claude-3-7-sonnet-latest';
}

router.get('/', (_req, res) => {
  const configured = resolveConfiguredProviders();
  const defaultProvider = normalizeProvider(env.AI_DEFAULT_PROVIDER);
  const activeProvider = resolveActiveProvider(defaultProvider, configured);
  const activeModel = resolveModel(activeProvider);

  res.json({
    provider_default: defaultProvider,
    provider_active: activeProvider,
    model_active: activeModel,
    providers: {
      claude: {
        configured: configured.claude,
        model: resolveModel('claude')
      },
      gpt: {
        configured: configured.gpt,
        model: resolveModel('gpt')
      },
      gemini: {
        configured: configured.gemini,
        model: resolveModel('gemini')
      }
    },
    proxy: {
      supabase_configured: configured.proxy
    }
  });
});

export default router;

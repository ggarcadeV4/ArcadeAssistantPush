/**
 * LaunchBox LoRa AI Chat Route
 * Created: 2025-10-06
 *
 * Dedicated AI endpoint for LaunchBox panel with tool integration.
 * Handles conversational queries about games and executes tool calls.
 */

import express from 'express';
import { fetchWithRetry } from '../lib/http.js';
import { launchboxToolDefinitions, launchboxTools, setFastapiUrl, setClientContext } from '../tools/launchbox.js';
import { sendTelemetry } from '../services/supabase_client.js';
import { parseRefinementText, applyRefinement } from '../utils/refinementParser.js';
import { sessionStore as supabaseSessionStore, SessionState, SESSION_TTL_MS, PENDING_SELECTION_TTL_MS, invoke as gemInvoke, executeToolCallingLoop } from '../gems/aa-lora/index.js';
// Gem-Agent Refactor: Extracted modules from launchboxAI.js
import { buildSystemPrompt } from '../gems/aa-lora/system_prompt.js';
import {
  extractGameName,
  isRelaunchRequest,
  resolveGame,
  launchGame,
  handleRelaunch,
  processFastPathLaunch
} from '../gems/aa-lora/fast_path.js';
import {
  normalize,
  normalizeTitleForMatch,
  parseRequestedGame,
  formatCandidateList,
  stringifyCandidates,
  PLATFORM_ALIASES,
  SORTED_PLATFORM_ALIASES
} from '../gems/aa-lora/parsers.js';

const router = express.Router();

const ANTHROPIC_API = 'https://api.anthropic.com/v1/messages';

/**
 * GET /api/launchbox/ai/health
 * Aggregated health for LoRa panel: AI provider, backend AI, and plugin status.
 */
router.get('/ai/health', async (req, res) => {
  try {
    setFastapiUrl(req.app.locals.fastapiUrl);
    const fastapi = req.app.locals.fastapiUrl;

    // Provider configured at gateway level (direct key OR Supabase proxy)
    const providerConfigured = Boolean(
      process.env.ANTHROPIC_API_KEY ||
      process.env.CLAUDE_API_KEY ||
      (process.env.SUPABASE_URL && process.env.SUPABASE_SERVICE_ROLE_KEY)
    );

    // Backend AI health (tolerant): OK if backend reports OK OR provider configured at gateway
    let backendAi = { ok: false };
    try {
      const aiResp = await fetchWithRetry(`${fastapi}/api/ai/health`, { method: 'GET' });
      if (aiResp.ok) {
        backendAi = await aiResp.json();
        backendAi.ok = true;
      }
    } catch (_) { }
    // If gateway provider is configured, treat AI as available even if backend lacks /api/ai/health
    if (providerConfigured && !backendAi.ok) backendAi.ok = true;

    // Plugin status (optional)
    let plugin = { available: false };
    try {
      const plugResp = await fetchWithRetry(`${fastapi}/api/launchbox/plugin-status`, { method: 'GET' });
      if (plugResp.ok) plugin = await plugResp.json();
    } catch (_) { }

    res.json({
      success: true,
      provider: { configured: providerConfigured },
      backend: { url: fastapi, ai: backendAi },
      plugin
    });
  } catch (error) {
    res.status(500).json({ success: false, error: error.message });
  }
});

// Session persistence migrated to Supabase via gems/aa-lora/session_store.js
// The sessionStore is now backed by Supabase aa_lora_sessions table.
// See: GEMS_PIVOT_VIGILANCE.md for architecture details.
// SESSION_TTL_MS and PENDING_SELECTION_TTL_MS are imported from gems/aa-lora/index.js

let platformAliasesCache = null;
let platformAliasesCacheAt = 0;
async function getPlatformAliasesCached(backendUrl) {
  const now = Date.now();
  if (platformAliasesCache && (now - platformAliasesCacheAt) < (60 * 60 * 1000)) {
    return platformAliasesCache;
  }
  try {
    const resp = await fetchWithRetry(`${backendUrl}/api/launchbox/platform-aliases`, { method: 'GET' });
    if (resp.ok) {
      const data = await resp.json().catch(() => null);
      if (data && typeof data === 'object') {
        platformAliasesCache = data;
        platformAliasesCacheAt = now;
        return platformAliasesCache;
      }
    }
  } catch (_) {
  }
  return platformAliasesCache || {};
}

function sessionKey(req) {
  return (req.headers['x-device-id'] || req.ip || 'anon').toString();
}

/**
 * Get session for a request (async, Supabase-backed)
 * Migrated from in-memory Map to Supabase persistence.
 * @param {import('express').Request} req
 * @returns {Promise<object>} Session object
 */
async function getSession(req) {
  const key = sessionKey(req);
  const now = Date.now();

  // Fetch from Supabase-backed SessionStore (with local cache)
  const sess = await supabaseSessionStore.get(key);

  // Check TTL - if session is stale, reset history to prevent echo
  if (sess.lastAccess && (now - sess.lastAccess) > SESSION_TTL_MS) {
    console.log(`[LoRa] Session ${key} expired, clearing history`);
    sess.history = [];
    sess.lastCandidates = [];
    sess.pendingLaunch = null;
    sess.lastLaunchedGameId = null;
    sess.lastLaunchedTitle = null;
    sess.lastLaunchedAt = null;
    sess.chatState = SessionState.IDLE;
  }

  sess.lastAccess = now;
  return sess;
}

/**
 * Save session state to Supabase (fire-and-forget for performance)
 * @param {import('express').Request} req
 * @param {object} sess
 */
function saveSession(req, sess) {
  const key = sessionKey(req);
  // Fire-and-forget - don't await to avoid blocking response
  supabaseSessionStore.set(key, sess).catch(err => {
    console.error('[LoRa] Session save error:', err.message);
  });
}

// NOTE: normalize, normalizeTitleForMatch, PLATFORM_ALIASES, parseRequestedGame,
// stringifyCandidates, formatCandidateList are now imported from '../gems/aa-lora/parsers.js'

/**
 * POST /api/launchbox/ai/clear-session
 * Clear conversation history to stop echo issues
 */
router.post('/ai/clear-session', async (req, res) => {
  const key = sessionKey(req);
  try {
    // Clear session via Supabase-backed SessionStore
    await supabaseSessionStore.clear(key);
    console.log(`[LoRa] Session ${key} manually cleared (Supabase)`);
    res.json({ success: true, message: 'Session cleared' });
  } catch (error) {
    console.error(`[LoRa] Session clear error:`, error.message);
    res.json({ success: true, message: 'Session cleared (local only)' });
  }
});

/**
 * POST /api/launchbox/chat (and /api/launchbox/ai/chat)
 * Chat with LoRa AI assistant about games (chat-only, no speech).
 */
async function handleLoRaChat(req, res) {
  try {
    const { message, context = {} } = req.body || {};

    if (!message || typeof message !== 'string') {
      return res.status(400).json({
        error: 'Invalid request',
        message: 'Message field is required'
      });
    }

    // Set FastAPI URL and client context for tool execution
    setFastapiUrl(req.app.locals.fastapiUrl);
    setClientContext({
      deviceId: req.headers['x-device-id'] || 'unknown',
      panel: 'launchbox'
    });

    // Sticky context for follow-ups (now async, Supabase-backed)
    const sess = await getSession(req);

    const now = Date.now();
    const pendingFresh = sess.chatState === 'PENDING_SELECTION' && sess.pendingLaunch && (now - (sess.pendingLaunch.createdAt || 0)) < PENDING_SELECTION_TTL_MS;
    if (sess.chatState === 'PENDING_SELECTION' && !pendingFresh) {
      sess.chatState = 'IDLE';
      sess.pendingLaunch = null;
    }

    const msgRaw = (message || '').toString();
    const msg = msgRaw.trim().toLowerCase();

    if (sess.chatState === 'PENDING_SELECTION' && sess.pendingLaunch && pendingFresh) {
      sess.pendingLaunch.createdAt = now;
      const refinement = parseRefinementText(msgRaw);

      if (refinement && refinement.cancel) {
        sess.chatState = 'IDLE';
        sess.pendingLaunch = null;
        return res.json({
          success: true,
          response: 'Okay, cancelled.',
          rounds: 0,
          game_launched: false
        });
      }

      const choice = msg.match(/^\s*(\d{1,2})\s*$/);
      if (choice && Array.isArray(sess.pendingLaunch.candidates)) {
        const idx = Number(choice[1]) - 1;
        const cand = sess.pendingLaunch.candidates[idx];
        if (cand && cand.id) {
          try {
            const backendUrl = req.app.locals.fastapiUrl;
            const launchResp = await fetch(`${backendUrl}/api/launchbox/launch/${cand.id}`, {
              method: 'POST',
              headers: {
                'Content-Type': 'application/json',
                'x-panel': 'launchbox',
                'x-device-id': req.headers['x-device-id'] || 'unknown'
              }
            });
            const launchData = await launchResp.json().catch(() => ({}));
            if (launchData.success) {
              sess.chatState = 'IDLE';
              sess.pendingLaunch = null;
              sess.lastCandidates = [];
              sess.lastLaunchedGameId = cand.id;
              sess.lastLaunchedTitle = cand.title || launchData.game_title || sess.lastLaunchedTitle;
              sess.lastLaunchedAt = Date.now();
              return res.json({
                success: true,
                response: `🎮 Launching ${cand.title}!`,
                rounds: 0,
                game_launched: true
              });
            }
          } catch (_) {
          }
        }
      }

      const backendUrl = req.app.locals.fastapiUrl;
      const platformAliases = await getPlatformAliasesCached(backendUrl);
      const originalCandidates = Array.isArray(sess.pendingLaunch.originalCandidates)
        ? sess.pendingLaunch.originalCandidates
        : (Array.isArray(sess.pendingLaunch.candidates) ? sess.pendingLaunch.candidates : []);
      const baseCandidates = originalCandidates;

      const applied = applyRefinement({
        candidates: baseCandidates,
        originalCandidates,
        refinement,
        platformAliases
      });

      if (applied && Array.isArray(applied.candidates) && applied.candidates.length === 1) {
        const cand = applied.candidates[0];
        if (cand && cand.id) {
          try {
            const launchResp = await fetch(`${backendUrl}/api/launchbox/launch/${cand.id}`, {
              method: 'POST',
              headers: {
                'Content-Type': 'application/json',
                'x-panel': 'launchbox',
                'x-device-id': req.headers['x-device-id'] || 'unknown'
              }
            });
            const launchData = await launchResp.json().catch(() => ({}));
            if (launchData.success) {
              sess.chatState = 'IDLE';
              sess.pendingLaunch = null;
              sess.lastCandidates = [];
              sess.lastLaunchedGameId = cand.id;
              sess.lastLaunchedTitle = cand.title || launchData.game_title || sess.lastLaunchedTitle;
              sess.lastLaunchedAt = Date.now();
              return res.json({
                success: true,
                response: `🎮 Launching ${cand.title} (${cand.platform || 'Unknown'})...`,
                rounds: 0,
                game_launched: true
              });
            }
          } catch (_) {
          }
        }
      }

      if (applied && Array.isArray(applied.candidates) && applied.candidates.length > 1) {
        sess.pendingLaunch.candidates = applied.candidates.slice(0, 5);
        sess.pendingLaunch.originalCandidates = applied.candidates;
        sess.pendingLaunch.createdAt = now;
        const preview = formatCandidateList(applied.candidates, 5);
        return res.json({
          success: true,
          response: `Reply with the number to launch:\n${preview}`,
          rounds: 0,
          game_launched: false
        });
      }

      if (applied && Array.isArray(applied.candidates) && applied.candidates.length === 0) {
        const preview = formatCandidateList(originalCandidates, 5);
        return res.json({
          success: true,
          response: `No matches for that refinement. Here are the original options:\n${preview}`,
          rounds: 0,
          game_launched: false
        });
      }

      const preview = formatCandidateList(originalCandidates, 5);
      return res.json({
        success: true,
        response: `You have a pending game selection. Pick a number (1-5), refine (e.g., "the arcade version"), or say "cancel" to exit.\n${preview}`,
        rounds: 0,
        game_launched: false
      });
    }

    // Fast path: pattern matching for simple launch commands
    // Bypasses AI for ~70% of requests, saving ~$0.001 per launch
    // Extract game name from conversational voice input
    let gameName = null;
    let platformHint = null;
    let yearHint = null;

    const wantsRelaunch = /^(?:re\s*-?launch|launch\s+again|play\s+again|start\s+again)\s*(?:please)?\s*$/.test(msg);
    if (wantsRelaunch) {
      if (!sess.lastLaunchedGameId) {
        return res.json({
          success: true,
          response: 'Tell me the game title to launch.',
          rounds: 0,
          game_launched: false
        });
      }
      try {
        const backendUrl = req.app.locals.fastapiUrl;
        const launchResp = await fetch(`${backendUrl}/api/launchbox/launch/${sess.lastLaunchedGameId}`, {
          method: 'POST',
          headers: {
            'Content-Type': 'application/json',
            'x-panel': 'launchbox',
            'x-device-id': req.headers['x-device-id'] || 'unknown'
          }
        });
        const launchData = await launchResp.json().catch(() => ({}));
        if (launchData.success) {
          sess.pendingLaunch = null;
          sess.lastCandidates = [];
          sess.lastLaunchedAt = Date.now();
          const title = sess.lastLaunchedTitle || launchData.game_title || 'that game';
          return res.json({
            success: true,
            response: `🎮 Launching ${title}!`,
            rounds: 0,
            game_launched: true
          });
        }
      } catch (_) {
        // fall through
      }
    }

    // Pattern 1: Direct commands
    const directMatch = msg.match(/(?:can you |please |could you |would you )?(?:launch|play|start|run)\s+(.+?)(?:\s+please)?$/i);
    if (directMatch) {
      gameName = directMatch[1].trim();
    }

    // Pattern 2: "I want to play X"
    if (!gameName) {
      const wantMatch = msg.match(/(?:i want to|i'd like to|let's|how about)\s+(?:play|launch|start)?\s*(.+?)(?:\s+please)?$/i);
      if (wantMatch) {
        gameName = wantMatch[1].trim();
      }
    }

    // Pattern 3: Conversational "X can you help" or "how about X"
    if (!gameName) {
      const helpMatch = msg.match(/(.+?)\s+(?:can you help|please|thanks)$/i);
      if (helpMatch) {
        const candidate = helpMatch[1].replace(/^(?:i want to play|i went to play|how about)\s+/i, '').trim();
        if (candidate && !candidate.includes('show') && !candidate.includes('find')) {
          gameName = candidate;
        }
      }
    }

    // Pattern 4: "how about X" at the start
    if (!gameName) {
      const howAboutMatch = msg.match(/^(?:how about|what about)\s+(.+?)(?:\s+please)?$/i);
      if (howAboutMatch) {
        gameName = howAboutMatch[1].trim();
      }
    }

    // Clean up common filler words from game name
    if (gameName) {
      const parsed = parseRequestedGame(gameName);
      gameName = parsed.title;
      platformHint = parsed.platform;
      yearHint = parsed.year;
      gameName = gameName
        .replace(/^(?:the|a|an)\s+/i, '')
        .replace(/\s+(?:game|please|thanks|thank you|again)$/i, '')
        .trim();

      // Skip if it looks like a complex query (not a game name)
      if (gameName.includes('?') || gameName.includes('show me') || gameName.includes('find me') ||
        gameName.includes('what') || gameName.includes('which') || gameName.length > 60 ||
        gameName.split(' ').length > 8) {
        gameName = null;
      }
    }

    if (gameName) {
      console.log(`[LaunchBox AI] Fast path: Direct launch for "${gameName}"`);

      if (sess.pendingLaunch && normalizeTitleForMatch(sess.pendingLaunch.requestedTitle) !== normalizeTitleForMatch(gameName)) {
        sess.pendingLaunch = null;
      }

      try {
        const backendUrl = req.app.locals.fastapiUrl;

        // SUPER OPTIMIZATION: Check user's favorite games first (instant match, no search needed)
        // This gives ~5x speed boost for frequently played games
        let game = null;
        const profileId = req.headers['x-user-profile'] || req.headers['x-profile-id'];

        if (profileId) {
          try {
            // Try to load user's tendencies (top games)
            const tendenciesResp = await fetch(`${req.protocol}://${req.get('host')}/profiles/${profileId}/tendencies.json`);
            if (tendenciesResp.ok) {
              const tendencies = await tendenciesResp.json();
              const topGames = tendencies.top_3_games || tendencies.top_10_games || [];

              // Check if requested game matches any favorite (fuzzy match)
              const gameNameLower = gameName.toLowerCase();
              const favoriteMatch = topGames.find(fav =>
                fav.toLowerCase().includes(gameNameLower) ||
                gameNameLower.includes(fav.toLowerCase())
              );

              if (favoriteMatch) {
                console.log(`[LaunchBox AI] ⚡ SUPER FAST: Found "${favoriteMatch}" in ${profileId}'s favorites!`);
                // Use the exact favorite name for better match
                gameName = favoriteMatch;
              }
            }
          } catch (err) {
            // Silently fail - just means we don't have tendencies, use normal path
          }
        }

        // Step 1: Resolve game name to ID
        const resolveResp = await fetchWithRetry(`${backendUrl}/api/launchbox/resolve`, {
          method: 'POST',
          headers: {
            'Content-Type': 'application/json',
            'x-panel': 'launchbox',
            'x-device-id': req.headers['x-device-id'] || 'unknown',
            'x-user-profile': req.headers['x-user-profile'] || '',
            'x-user-name': req.headers['x-user-name'] || '',
            'x-session-owner': req.headers['x-session-owner'] || ''
          },
          body: JSON.stringify({
            title: gameName,
            platform: platformHint || undefined,
            year: Number.isFinite(yearHint) ? yearHint : undefined,
            limit: 25
          })
        });

        const resolveData = await resolveResp.json().catch(() => ({}));
        const requestedNorm = normalizeTitleForMatch(gameName);

        if (resolveData && Array.isArray(resolveData.candidates) && resolveData.candidates.length > 0) {
          sess.chatState = 'PENDING_SELECTION';
          const pool = resolveData.candidates;
          const shown = pool.slice(0, 5);
          sess.pendingLaunch = {
            requestedTitle: gameName,
            candidates: shown,
            originalCandidates: pool,
            createdAt: Date.now()
          };
          const preview = formatCandidateList(pool, 5);
          return res.json({
            success: true,
            response: `I found a few matches for "${gameName}". Reply with the number to launch:\n${preview}`,
            rounds: 0,
            game_launched: false
          });
        }

        if (Array.isArray(resolveData) && resolveData.length > 0) {
          sess.chatState = 'PENDING_SELECTION';
          const pool = resolveData;
          const shown = pool.slice(0, 5);
          sess.pendingLaunch = {
            requestedTitle: gameName,
            candidates: shown,
            originalCandidates: pool,
            createdAt: Date.now()
          };
          const preview = formatCandidateList(pool, 5);
          return res.json({
            success: true,
            response: `I found a few matches for "${gameName}". Reply with the number to launch:\n${preview}`,
            rounds: 0,
            game_launched: false
          });
        }

        if (resolveData && resolveData.status === 'resolved' && resolveData.game) {
          const resolved = resolveData.game;
          const resolvedNorm = normalizeTitleForMatch(resolved.title);

          // Auto-launch when resolver indicates a deterministic/safe match.
          const trustedResolveSources = new Set([
            'cache_exact',
            'cache_fuzzy_strict_title',
            'cache_fuzzy_score_leader',
            'cache_fuzzy_canonical_default'
          ]);
          const confidence = Number(resolved.confidence || 0);
          const shouldAutoLaunch =
            trustedResolveSources.has(resolveData.source) ||
            requestedNorm === resolvedNorm ||
            confidence >= 0.97;

          if (shouldAutoLaunch) {
            const launchResp = await fetch(`${backendUrl}/api/launchbox/launch/${resolved.id}`, {
              method: 'POST',
              headers: {
                'Content-Type': 'application/json',
                'x-panel': 'launchbox',
                'x-device-id': req.headers['x-device-id'] || 'unknown',
                'x-user-profile': req.headers['x-user-profile'] || '',
                'x-user-name': req.headers['x-user-name'] || '',
                'x-session-owner': req.headers['x-session-owner'] || ''
              }
            });
            const launchData = await launchResp.json().catch(() => ({}));
            if (launchData.success) {
              sess.pendingLaunch = null;
              sess.lastLaunchedGameId = resolved.id;
              sess.lastLaunchedTitle = resolved.title || launchData.game_title || sess.lastLaunchedTitle;
              sess.lastLaunchedAt = Date.now();
              return res.json({
                success: true,
                response: `🎮 Launching ${resolved.title}!`,
                rounds: 0,
                game_launched: true
              });
            }
          }

          // Resolved but not exact: ask for confirmation instead of launching
          sess.chatState = 'PENDING_SELECTION';
          sess.pendingLaunch = {
            requestedTitle: gameName,
            candidates: [resolved],
            originalCandidates: [resolved],
            createdAt: Date.now()
          };
          return res.json({
            success: true,
            response: `I found "${resolved.title}" for "${gameName}". Reply "1" to launch, or refine (e.g., "the arcade version").`,
            rounds: 0,
            game_launched: false
          });
        }

        if (resolveData && resolveData.status === 'multiple_matches' && Array.isArray(resolveData.suggestions)) {
          sess.chatState = 'PENDING_SELECTION';
          const pool = resolveData.suggestions;
          const shown = pool.slice(0, 5);
          sess.pendingLaunch = {
            requestedTitle: gameName,
            candidates: shown,
            originalCandidates: pool,
            createdAt: Date.now()
          };
          const preview = formatCandidateList(pool, 5);
          return res.json({
            success: true,
            response: `I found a few matches for "${gameName}". Reply with the number to launch:\n${preview}`,
            rounds: 0,
            game_launched: false
          });
        }

        // Handle platform disambiguation - game not on requested platform but exists on others
        if (resolveData && resolveData.status === 'platform_disambiguation') {
          sess.chatState = 'PENDING_SELECTION';

          // Flatten all suggestions into a numbered list for selection, dedupe, and cap display length.
          const dedupe = new Set();
          const allOptions = [];
          for (const group of resolveData.suggestions || []) {
            for (const game of group.games || []) {
              const option = {
                ...game,
                platform: group.platform
              };
              const key = `${normalizeTitleForMatch(option.title || '')}::${(option.platform || '').toLowerCase()}::${option.year || ''}`;
              if (dedupe.has(key)) continue;
              dedupe.add(key);
              allOptions.push(option);
            }
          }

          const shownOptions = allOptions.slice(0, 8);
          sess.pendingLaunch = {
            requestedTitle: gameName,
            candidates: shownOptions,
            originalCandidates: allOptions,
            createdAt: Date.now()
          };

          if (shownOptions.length === 0) {
            return res.json({
              success: true,
              response: `I could not find a confident match for "${gameName}" on ${resolveData.requested_platform}. Try adding platform or year.`,
              rounds: 0,
              game_launched: false
            });
          }

          // Format the clarifying question
          const platformList = (resolveData.available_on || []).join(', ');
          const optionText = shownOptions
            .map((g, idx) => `${idx + 1}) ${g.title} - ${g.platform}`)
            .join('\n');
          const overflowCount = Math.max(0, allOptions.length - shownOptions.length);
          const overflowNote = overflowCount > 0
            ? `\n...and ${overflowCount} more. You can also reply with platform/year.`
            : '';

          return res.json({
            success: true,
            response: `I could not find "${gameName}" on ${resolveData.requested_platform}, but I found close matches on ${platformList}:\n${optionText}${overflowNote}\n\nReply with the number you want.`,
            rounds: 0,
            game_launched: false
          });
        }

        if (resolveData && resolveData.status === 'not_found') {
          sess.chatState = 'IDLE';
          sess.pendingLaunch = null;
          return res.json({
            success: true,
            response: `I couldn't find "${gameName}". Try the exact title, or include a platform/year.`,
            rounds: 0,
            game_launched: false
          });
        }

        sess.chatState = 'IDLE';
        sess.pendingLaunch = null;
        return res.json({
          success: true,
          response: `I couldn't safely resolve "${gameName}". Please include the platform or year, or try a more exact title.`,
          rounds: 0,
          game_launched: false
        });
      } catch (error) {
        sess.chatState = 'IDLE';
        sess.pendingLaunch = null;
        return res.json({
          success: true,
          response: `I couldn't safely resolve "${gameName}" right now. Please try again with a platform or year.`,
          rounds: 0,
          game_launched: false
        });
      }
    }

    // Extract profile from headers (sent by frontend)
    const userProfile = req.headers['x-user-profile'] || null;
    // Sanitize username: strip any parenthetical suffix like "(Vicky)" for clean AI greeting
    const rawUserName = req.headers['x-user-name'] || null;
    const userName = rawUserName ? rawUserName.replace(/\s*\([^)]*\)\s*$/, '').trim() : null;

    // Sticky context: rewrite follow-ups for shader workflow and a few common patterns
    let userMessage = normalize(message);
    const lower = userMessage.toLowerCase();
    const isAffirm = /^(yes|yeah|yep|sure|please do|go ahead|do it)\b/i.test(userMessage);
    const wantsLaunchNow = /(now\s+launch|launch\s+it|start\s+it)\b/i.test(lower);
    const platformMatch = userMessage.match(/the one from (the )?(.+)/i);

    // If a shader preview is pending, treat "yes" as apply+launch for that exact game/emulator
    if (isAffirm && sess.pendingShader && sess.pendingShader.game_id) {
      const p = sess.pendingShader;
      userMessage = `Apply shader ${p.shader_name} using ${p.emulator} to game ${p.game_id} then launch`;
    } else if (wantsLaunchNow && sess.readyToLaunchGameId) {
      // If user said "now launch it" after an apply, use the exact game id we just applied to
      userMessage = `Launch game id ${sess.readyToLaunchGameId}`;
    } else if (platformMatch && sess.lastTitle) {
      const plat = platformMatch[2].trim();
      userMessage = `Launch ${sess.lastTitle} on ${plat}`;
    }

    // Build system prompt with context and profile
    const systemPrompt = buildSystemPrompt(context, userName);

    console.log('[LaunchBox AI] User message:', message);

    // Seed conversation with prior history for this device
    const sessHistory = Array.isArray(sess.history) ? [...sess.history] : [];
    const seedMessages = [
      ...sessHistory,
      { role: 'user', content: [{ type: 'text', text: userMessage }] }
    ];

    // Debug: log seed history
    try {
      console.log('[LoRa Debug] Seed history length:', seedMessages.length);
      console.log('[LoRa Debug] Seed last 3:', seedMessages.slice(-3).map(m => ({ role: m.role, types: (Array.isArray(m.content) ? m.content.map(c => c.type) : typeof m.content) })));
    } catch (_) { }

    // Execute tool calling loop with seeded history
    const result = await executeToolCallingLoop(systemPrompt, seedMessages, {
      backendUrl: req.app.locals.fastapiUrl,
      headers: {
        'x-device-id': req.headers['x-device-id'] || 'unknown',
        'x-panel': 'launchbox',
        'x-user-profile': req.headers['x-user-profile'] || '',
        'x-user-name': req.headers['x-user-name'] || '',
        'x-session-owner': req.headers['x-session-owner'] || ''
      },
      tools: launchboxTools,
      callAI: callClaudeAPI
    });

    // Update sticky session based on tool calls
    try {
      if (Array.isArray(result.toolCallsMade)) {
        for (const tc of result.toolCallsMade) {
          if (tc && tc.name && tc.result) {
            if (tc.name === 'search_games' || tc.name === 'filter_games') {
              const games = tc.result.games || [];
              if (Array.isArray(games) && games.length > 0) {
                sess.lastCandidates = games;
                sess.lastTitle = games[0].title || sess.lastTitle;
                sess.lastPlatform = games[0].platform || sess.lastPlatform;
              }
            }
            if (tc.name === 'get_random_game' && tc.result.game) {
              const g = tc.result.game;
              sess.lastCandidates = [g];
              sess.lastTitle = g.title || sess.lastTitle;
              sess.lastPlatform = g.platform || sess.lastPlatform;
            }
            if (tc.name === 'launch_game' && tc.result.success) {
              // Clear candidates after a successful launch
              sess.lastCandidates = [];
              sess.pendingShader = null;
              sess.readyToLaunchGameId = null;
              sess.pendingLaunch = null;
              if (tc.result.game_id) {
                sess.lastLaunchedGameId = tc.result.game_id;
                sess.lastLaunchedTitle = tc.result.game_title || sess.lastLaunchedTitle;
                sess.lastLaunchedAt = Date.now();
              }
            }
            // Track shader workflow state explicitly
            if (tc.name === 'manage_shader') {
              try {
                const input = tc.input || {};
                const result = tc.result || {};
                if ((result.status === 'preview_ready' || result.status === 'preview') && input.game_id) {
                  sess.pendingShader = {
                    game_id: input.game_id,
                    emulator: input.emulator,
                    shader_name: input.shader_name
                  };
                }
                if ((result.status === 'applied' || result.success === true) && input.game_id) {
                  sess.readyToLaunchGameId = input.game_id;
                  // Once applied, preview is no longer pending
                  sess.pendingShader = null;
                }
                if (result.status === 'removed' && input.game_id) {
                  // Clear pending if user removed instead
                  if (sess.readyToLaunchGameId === input.game_id) sess.readyToLaunchGameId = null;
                  if (sess.pendingShader?.game_id === input.game_id) sess.pendingShader = null;
                }
              } catch (_) { }
            }
          }
        }
      }
    } catch (_) { }

    // Persist trimmed history back to session (ONLY text exchanges, no tool blocks)
    try {
      const MAX_MESSAGES = 10; // smaller window to prevent echo buildup
      const rawHist = Array.isArray(result?.messages) ? result.messages : seedMessages;

      // Filter out tool_use and tool_result blocks to prevent echo
      const cleanHist = rawHist.filter(msg => {
        if (!Array.isArray(msg.content)) return true; // keep simple text
        // Check if this is a tool_result message (user role with tool_result content)
        const hasToolResult = msg.content.some(b => b.type === 'tool_result');
        if (hasToolResult) return false; // drop tool results
        // Check if assistant message has ONLY tool_use (no text)
        if (msg.role === 'assistant') {
          const hasText = msg.content.some(b => b.type === 'text' && b.text?.trim());
          const hasToolUse = msg.content.some(b => b.type === 'tool_use');
          if (hasToolUse && !hasText) return false; // drop tool-only assistant msgs
        }
        return true;
      }).map(msg => {
        // Strip tool_use blocks from assistant messages that also have text
        if (msg.role === 'assistant' && Array.isArray(msg.content)) {
          const textOnly = msg.content.filter(b => b.type === 'text');
          if (textOnly.length > 0) {
            return { role: msg.role, content: textOnly };
          }
        }
        return msg;
      });

      // Keep only last N messages
      while (cleanHist.length > MAX_MESSAGES) cleanHist.shift();
      sess.history = cleanHist;
      console.log('[LoRa Debug] Persisted clean history length:', sess.history.length);
    } catch (_) { }

    // Send AI telemetry to Supabase (fire-and-forget for performance)
    const cabinetId = req.headers['x-device-id'] || process.env.AA_DEVICE_ID;
    if (cabinetId) {
      const toolNames = (result.toolCallsMade || []).map(t => t.name);
      sendTelemetry(
        cabinetId,
        'INFO',
        'AI_CALL',
        `LoRa: ${result.rounds} round(s), ${toolNames.length} tool(s)`,
        {
          panel: 'launchbox',
          provider: result.provider || 'gemini',
          model: result.model || 'gemini-2.0-flash',
          rounds: result.rounds,
          tool_calls: toolNames,
          game_launched: result.gameLaunched || false,
          latency_ms: result.latencyMs || null,
          input_tokens: result.usage?.prompt_tokens || null,
          output_tokens: result.usage?.completion_tokens || null
        },
        'launchbox'
      ).catch(err => console.warn('[LoRa] Telemetry send failed:', err.message));
    }

    res.json({
      success: true,
      response: result.finalText,
      tool_calls_made: result.toolCallsMade,
      rounds: result.rounds,
      game_launched: result.gameLaunched
    });

  } catch (error) {
    console.error('[LaunchBox AI] Error:', error);

    res.status(500).json({
      success: false,
      error: error.message,
      hint: 'Check that ANTHROPIC_API_KEY is set in .env'
    });
  }
}

// Primary LoRa chat route
router.post('/chat', handleLoRaChat);

// Compatibility alias some builds expect: /api/launchbox/ai/chat
router.post('/ai/chat', handleLoRaChat);

// NOTE: buildSystemPrompt is now imported from '../gems/aa-lora/system_prompt.js'

// NOTE: executeToolCallingLoop is now imported from '../gems/aa-lora/index.js'
//       which delegates to tool_loop.js with shader_handler.js for manage_shader


/**
 * Call AI API with messages (Gemini PRIMARY, Claude fallback for Golden Drive)
 * Gemini 2.0 Flash is used by default for speed and cost efficiency.
 * Set LAUNCHBOX_FORCE_CLAUDE=true to use Claude instead.
 */
async function callClaudeAPI(systemPrompt, messages) {
  const supabaseConfigured = Boolean(process.env.SUPABASE_URL && process.env.SUPABASE_SERVICE_ROLE_KEY);
  const forceClaude = ['1', 'true', 'yes', 'on'].includes(String(process.env.LAUNCHBOX_FORCE_CLAUDE || '').trim().toLowerCase());
  const directKey = process.env.ANTHROPIC_API_KEY || process.env.CLAUDE_API_KEY;

  // Golden Drive: Gemini is PRIMARY when Supabase is configured (unless Claude is forced)
  if (supabaseConfigured && !forceClaude) {
    console.log('[LaunchBox AI] Golden Drive: Using Gemini 2.0 Flash (PRIMARY)');
    try {
      return await callGeminiAPI(systemPrompt, messages);
    } catch (geminiError) {
      console.warn('[LaunchBox AI] Gemini failed, falling back to Claude:', geminiError.message);
      // Fall through to Claude fallback
    }
  }

  // Claude fallback section (only reached if Gemini fails or Claude is forced)
  const modelToUse = process.env.ANTHROPIC_MODEL || 'claude-3-5-haiku-20241022';
  const forceDirect = ['1', 'true', 'yes', 'on'].includes(String(process.env.LAUNCHBOX_FORCE_DIRECT || '').trim().toLowerCase());

  console.log('[LaunchBox AI] Claude fallback - Using model:', modelToUse);

  // Prefer direct key when available (or forced), otherwise fall back to Supabase Edge Function proxy
  if (directKey && (forceDirect || !supabaseConfigured)) {
    const response = await fetchWithRetry(ANTHROPIC_API, {
      method: 'POST',
      headers: {
        'content-type': 'application/json',
        'x-api-key': directKey,
        'anthropic-version': '2023-06-01',
      },
      body: JSON.stringify({
        model: modelToUse,
        max_tokens: 512,
        system: systemPrompt,
        tools: launchboxToolDefinitions,
        messages: messages
      })
    });

    if (!response.ok) {
      const errorText = await response.text();
      throw new Error(`Anthropic API error ${response.status}: ${errorText}`);
    }
    const data = await response.json();
    // Add telemetry metadata
    return { ...data, provider: 'anthropic', model: modelToUse };
  }

  if (supabaseConfigured) {
    // Anthropic proxy has been retired — use Gemini proxy as the sole fallback
    console.log('[LaunchBox AI] Claude fallback: routing through Gemini proxy (anthropic-proxy retired)');
    return await callGeminiAPI(systemPrompt, messages);
  }

  // Neither direct key nor Supabase proxy configured
  throw new Error('LaunchBox AI not configured: set ANTHROPIC_API_KEY or SUPABASE_URL + SUPABASE_SERVICE_ROLE_KEY');
}

/**
 * Call Gemini API via Supabase proxy (Golden Drive PRIMARY)
 * Gemini 2.0 Flash with full function calling support for LoRa tools.
 */
async function callGeminiAPI(systemPrompt, messages) {
  const geminiModel = process.env.GEMINI_MODEL || 'gemini-2.0-flash';

  if (!process.env.SUPABASE_URL || !process.env.SUPABASE_SERVICE_ROLE_KEY) {
    throw new Error('Gemini requires SUPABASE_URL + SUPABASE_SERVICE_ROLE_KEY');
  }

  console.log('[LaunchBox AI] Using Gemini model:', geminiModel);

  const proxyUrl = `${process.env.SUPABASE_URL}/functions/v1/gemini-proxy`;
  const response = await fetchWithRetry(proxyUrl, {
    method: 'POST',
    headers: {
      'content-type': 'application/json',
      'Authorization': `Bearer ${process.env.SUPABASE_SERVICE_ROLE_KEY}`
    },
    body: JSON.stringify({
      model: geminiModel,
      max_tokens: 1024,
      system: systemPrompt,
      tools: launchboxToolDefinitions,  // Pass tools for function calling!
      messages: messages
    })
  });

  if (!response.ok) {
    const errorText = await response.text();
    throw new Error(`Gemini proxy error ${response.status}: ${errorText}`);
  }

  const data = await response.json();
  // Add telemetry metadata
  return { ...data, provider: 'gemini', model: geminiModel };
}

export default router;

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

// Minimal sticky session state per device to make follow-ups like "yes" or
// "the NES one" work without frontend passing full history. Also stores
// conversation history so Claude retains context across requests.
const sessionStore = new Map();
const SESSION_TTL_MS = 10 * 60 * 1000; // 10 minute TTL to prevent stale echo buildup
const PENDING_SELECTION_TTL_MS = 3 * 60 * 1000;

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

function getSession(req) {
  const key = sessionKey(req);
  const now = Date.now();

  if (sessionStore.has(key)) {
    const sess = sessionStore.get(key);
    // Check TTL - if session is stale, reset history to prevent echo
    if (sess.lastAccess && (now - sess.lastAccess) > SESSION_TTL_MS) {
      console.log(`[LoRa] Session ${key} expired, clearing history`);
      sess.history = [];
      sess.lastCandidates = [];
      sess.pendingLaunch = null;
      sess.lastLaunchedGameId = null;
      sess.lastLaunchedTitle = null;
      sess.lastLaunchedAt = null;
    }
    sess.lastAccess = now;
    return sess;
  }

  const newSess = {
    lastCandidates: [],
    lastTitle: null,
    lastPlatform: null,
    history: [],
    lastAccess: now,
    pendingLaunch: null,
    chatState: 'IDLE',
    lastLaunchedGameId: null,
    lastLaunchedTitle: null,
    lastLaunchedAt: null
  };
  sessionStore.set(key, newSess);
  return newSess;
}

function normalize(str) { return (str || '').toString().trim(); }

function normalizeTitleForMatch(str) {
  return normalize(str)
    .toLowerCase()
    .replace(/['’]/g, '')
    .replace(/[^a-z0-9]+/g, ' ')
    .replace(/\s+/g, ' ')
    .trim();
}

// Platform alias map: short form -> full LaunchBox platform name
// Moved to module level for performance (created once at load, not per call)
const PLATFORM_ALIASES = {
  'nes': 'Nintendo Entertainment System',
  'famicom': 'Nintendo Entertainment System',
  'snes': 'Super Nintendo Entertainment System',
  'super nintendo': 'Super Nintendo Entertainment System',
  'genesis': 'Sega Genesis',
  'mega drive': 'Sega Genesis',
  'megadrive': 'Sega Genesis',
  'arcade': 'Arcade',
  'mame': 'Arcade',
  'n64': 'Nintendo 64',
  'nintendo 64': 'Nintendo 64',
  'ps1': 'Sony Playstation',
  'psx': 'Sony Playstation',
  'playstation 1': 'Sony Playstation',
  'ps2': 'Sony Playstation 2',
  'playstation 2': 'Sony Playstation 2',
  'gamecube': 'Nintendo GameCube',
  'gc': 'Nintendo GameCube',
  'wii': 'Nintendo Wii',
  'gameboy': 'Nintendo Game Boy',
  'game boy': 'Nintendo Game Boy',
  'gba': 'Nintendo Game Boy Advance',
  'game boy advance': 'Nintendo Game Boy Advance',
  'ds': 'Nintendo DS',
  'dreamcast': 'Sega Dreamcast',
  'saturn': 'Sega Saturn',
  'master system': 'Sega Master System',
  'atari 2600': 'Atari 2600',
  'atari': 'Atari 2600',
  'turbografx': 'TurboGrafx-16',
  'tg16': 'TurboGrafx-16',
  'pc engine': 'TurboGrafx-16',
  'neo geo': 'SNK Neo Geo AES',
  'neogeo': 'SNK Neo Geo AES',
};

// Pre-sorted by length (longest first) for correct matching priority
const SORTED_PLATFORM_ALIASES = Object.keys(PLATFORM_ALIASES).sort((a, b) => b.length - a.length);

function parseRequestedGame(str) {
  const raw = normalize(str);
  const lower = raw.toLowerCase();

  let platform = null;
  let platformMatch = null;

  // Check for platform aliases (prefer longer matches first)
  for (const alias of SORTED_PLATFORM_ALIASES) {
    // Match as word boundary (at start, end, or surrounded by spaces)
    const pattern = new RegExp(`(^|\\s)${alias.replace(/[.*+?^${}()|[\]\\]/g, '\\$&')}(\\s|$)`, 'i');
    if (pattern.test(lower)) {
      platform = PLATFORM_ALIASES[alias];
      platformMatch = alias;
      break;
    }
  }

  let year = null;
  const cuedYearMatch = lower.match(/\b(?:from|released|release|in|year)\s+(19\d{2}|20\d{2})\b/);
  const trailingYearMatch = raw.match(/^(.+?)\s+(19\d{2}|20\d{2})\b\s*$/);
  if (cuedYearMatch) {
    year = Number(cuedYearMatch[1]);
  } else if (trailingYearMatch) {
    year = Number(trailingYearMatch[2]);
  }

  let title = raw
    .replace(/[\s\.,!?;:]+$/g, '')
    .replace(/\bplease\b/gi, ' ')
    .replace(/\b(?:from|released|release|in|year)\s+(19\d{2}|20\d{2})\b/gi, ' ')
    .replace(/^(.+?)\s+(19\d{2}|20\d{2})\b\s*$/i, (m, p1) => p1);

  // Remove matched platform from title
  if (platformMatch) {
    const platformPattern = new RegExp(`(^|\\s)${platformMatch.replace(/[.*+?^${}()|[\]\\]/g, '\\$&')}(\\s+version)?\\s*`, 'gi');
    title = title.replace(platformPattern, ' ');
  }

  title = title
    .replace(/\s+version\s*$/i, ' ')
    .replace(/\s+/g, ' ')
    .trim();

  return { title, platform, year };
}


function stringifyCandidates(candidates, limit = 5) {
  const items = Array.isArray(candidates) ? candidates.slice(0, limit) : [];
  return items
    .map((g, idx) => {
      const year = g.year ? `, ${g.year}` : '';
      const platform = g.platform ? ` — ${g.platform}` : '';
      return `${idx + 1}) ${g.title || 'Unknown'}${year}${platform}`;
    })
    .join('\n');
}

function formatCandidateList(candidates, limit = 5) {
  const total = Array.isArray(candidates) ? candidates.length : 0;
  const preview = stringifyCandidates(candidates, limit);
  if (total > limit) {
    return `${preview}\nShowing ${limit} of ${total} matches. Refine your request (e.g., "the arcade version") to narrow results.`;
  }
  return preview;
}

/**
 * POST /api/launchbox/ai/clear-session
 * Clear conversation history to stop echo issues
 */
router.post('/ai/clear-session', (req, res) => {
  const key = sessionKey(req);
  if (sessionStore.has(key)) {
    const sess = sessionStore.get(key);
    sess.history = [];
    sess.lastCandidates = [];
    sess.pendingShader = null;
    sess.readyToLaunchGameId = null;
    sess.pendingLaunch = null;
    sess.lastLaunchedGameId = null;
    sess.lastLaunchedTitle = null;
    sess.lastLaunchedAt = null;
    console.log(`[LoRa] Session ${key} manually cleared`);
  }
  res.json({ success: true, message: 'Session cleared' });
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

    // Sticky context for follow-ups
    const sess = getSession(req);

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

          // Only auto-launch on a clear exact match (protect against wrong-title launches)
          if (resolveData.source === 'cache_exact' || requestedNorm === resolvedNorm) {
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

          // Flatten all suggestions into a numbered list for selection
          const allOptions = [];
          for (const group of resolveData.suggestions || []) {
            for (const game of group.games || []) {
              allOptions.push({
                ...game,
                platform: group.platform
              });
            }
          }

          sess.pendingLaunch = {
            requestedTitle: gameName,
            candidates: allOptions,
            originalCandidates: allOptions,
            createdAt: Date.now()
          };

          // Format the clarifying question
          const platformList = (resolveData.available_on || []).join(', ');
          let optionText = allOptions
            .map((g, idx) => `${idx + 1}) ${g.title} — ${g.platform}`)
            .join('\n');

          return res.json({
            success: true,
            response: `I couldn't find "${gameName}" on ${resolveData.requested_platform}, but I found similar games on other platforms:\n${optionText}\n\nWhich one did you mean? Reply with the number.`,
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
      }
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

/**
 * Build system prompt with current context and user profile
 */
function buildSystemPrompt(context, userName = null) {
  const { currentFilters = {}, availableGames = 0, stats = {}, directLaunch = {} } = context;
  const statsSafe = (stats && typeof stats === 'object') ? stats : {};
  const directRetroArchEnabled = directLaunch?.directRetroArchEnabled;
  const allowRetroArch = directLaunch?.allowRetroArch;

  // Profile-aware greeting
  const userGreeting = userName ? `You are speaking with ${userName}.` : `You are speaking with a guest user.`;
  const nameReminder = userName
    ? `If the user asks for their name or identity, confidently remind them they are ${userName}.`
    : `If the user asks for their name, let them know no profile name has been saved yet.`;

  let prompt = `You are LoRa, the LaunchBox AI assistant for an arcade cabinet game library.

CRITICAL: YOU ARE A FUNCTION-CALLING AGENT.
- You have access to tools (functions) that you MUST use to accomplish tasks.
- To search for games, you MUST call the search_games function.
- To launch a game, you MUST call the launch_game function with the game_id.
- NEVER just describe what you would do - actually call the functions!
- When the user selects a game (e.g., "1", "the first one", "Galaga 1981"), use the game_id from your previous search results to call launch_game.

${userGreeting}

YOUR ROLE: You help users discover, browse, filter, and launch games from their retro gaming collection.

WHAT YOU DO:
- Browse and search the game library (10,000+ retro titles)
- Filter by genre, platform, decade, or keyword
- Provide game recommendations based on user preferences
- Launch games directly (requires game_id from search)
- Share gaming knowledge and history
- Answer questions about specific games, franchises, or platforms
- Get random game suggestions for discovery

WHAT YOU DON'T DO:
- Voice/microphone setup (handled by the VickyVoice module)
- Controller configuration or button mapping (that's Chuck's job)
- LED lighting or cabinet themes (that's Blinky's job)
- Tournament setup or scoring (that's Sam's job)
- Light gun calibration (that's Gunner's job)
- System diagnostics or health monitoring (that's Doc's job)

ROUTING: If someone asks about voice setup, controllers, LEDs, tournaments, calibration, or system health, politely tell them "That's not my specialty - let me connect you with [Assistant Name] who handles that!" Then suggest they visit the appropriate panel.

PERSONALITY & TONE:
- You're warm, friendly, and genuinely excited about retro games - like a friend who runs a game store
- Use casual language: "Oh nice choice!", "That's a classic!", "Good call!"
- Share brief fun facts or memories: "Ah, Super Mario Bros! The game that saved the industry. NES version?"
- When listing options, add personality: "Here's what we've got:" instead of clinical lists
- Use gaming emojis naturally: 🎮 🕹️ 🔥 ✨
- Keep responses conversational - 2-3 sentences max before asking a follow-up
- If you find multiple matches, be helpful: "I found a few versions - which era are you feeling?"
- Sound like a friend, not a database query

LARGE LISTS - BE CONVERSATIONAL:
- NEVER dump 50 game titles at once! That's overwhelming and not conversational.
- If someone asks "what PS2 games do we have?" or similar broad questions:
  - First, share the count enthusiastically: "Oh we've got 88 PS2 games! That's a solid collection. 🎮"
  - Then ASK what they're in the mood for: "What kind of games are you feeling? Action? RPG? Sports? Or I can suggest some classics!"
  - Only show 5-8 games at a time, with personality
- Example response to "what PS2 games do we have?":
  "We've got 88 PS2 titles! 🔥 Some absolute bangers in there. What genre are you feeling? We've got classics like God of War and Kingdom Hearts for action, or Final Fantasy for RPGs. Want me to narrow it down?"

${nameReminder}

CURRENT LIBRARY STATUS:
- Total Games: ${statsSafe.total_games || 0}
- Platforms: ${statsSafe.platforms_count || 0}
- Genres: ${statsSafe.genres_count || 0}
- Data Source: ${statsSafe.is_mock_data ? 'Mock Data (Development)' : 'A: Drive LaunchBox'}`;

  if (directRetroArchEnabled === true) {
    prompt += `\n- RetroArch Direct Launch: ENABLED (fallback available when plugin is offline)`;
  } else if (directRetroArchEnabled === false) {
    prompt += `\n- RetroArch Direct Launch: DISABLED`;
  }
  if (allowRetroArch === false) {
    prompt += `\n- User Preference: Avoid RetroArch fallback unless explicitly requested`;
  }

  if (availableGames > 0) {
    prompt += `\n- Currently Showing: ${availableGames} games`;
  }

  if (currentFilters.genre && currentFilters.genre !== 'All') {
    prompt += `\n- Active Filter: Genre = ${currentFilters.genre}`;
  }

  if (currentFilters.decade && currentFilters.decade !== 'All') {
    prompt += `\n- Active Filter: Decade = ${currentFilters.decade}`;
  }

  prompt += `

  AVAILABLE TOOLS:
  - filter_games: Filter by genre, decade, or platform
  - search_games: Search by game title
  - get_random_game: Get a random game suggestion
  - launch_game: Launch a game (requires game_id from search/filter results)
  - get_library_stats: Get current library statistics
  - get_available_genres: List all genres
  - get_available_platforms: List all platforms
  - manage_shader: Preview/apply/remove shaders for a specific game (e.g., CRT scanlines)
  - get_marquee_game: Get info about the game currently shown on the marquee (for "what game is this?")
  - find_similar_games: Find games similar to the current marquee game (for "show me games like this")

  MARQUEE AWARENESS:
  - The cabinet has a marquee display showing the currently selected game
  - When users ask "what game is this?", "tell me about this game", or "what am I looking at?", use get_marquee_game
  - When users ask "find more like this", "similar games", or "what else is like this?", use find_similar_games
  - You can describe games shown on the marquee with trivia, history, and recommendations

  SHADER MANAGEMENT:
  - You can manage visual shader presets for games using the manage_shader tool
  - Common shaders:
    - MAME: lcd-grid (LCD matrix), sharp-bilinear (crisp pixels), crt-geom (curved CRT)
    - RetroArch: crt-royale (CRT scanlines + phosphor glow), crt-easy (light scanlines), sharp (pixel-perfect)

  CRITICAL WORKFLOW RULES:
  1) When user asks to "launch [game] with [shader]":
     - FIRST: Call manage_shader with action=preview
     - WAIT: Do NOT launch yet. Ask for confirmation
     - SECOND: On clear approval (e.g., "yes"), call manage_shader with action=apply
     - THIRD: Inform: "Shader applied! Launching [game] in 3 seconds..."
     - FOURTH: Call launch_game
     - NEVER launch before shader is confirmed and applied.
  2) When user says "apply it" or "yes" after a preview, it means: apply the shader THEN launch the game (in that order).
  3) Always explain visually what the shader does before applying.
  4) After applying, remind the user a brief moment is needed before launch.

  Example correct workflow:
  User: "Launch Ms. Pac-Man with CRT shader"
  You: [manage_shader preview]
       "I'll apply crt-royale which adds CRT scanlines and phosphor glow. Ready to apply and launch?"
  User: "Yes"
  You: [manage_shader apply]
       "Shader applied successfully! Launching Ms. Pac-Man now..."
  You: [launch_game]

  IMPORTANT GUIDELINES:
  1. When users ask to launch a game, ALWAYS search for it first to get the game_id
  1a. For shader changes: First use search_games to resolve the exact game (and platform) to get the game_id. Then call manage_shader with action="preview"; show the diff and ask for approval. Only on clear approval call manage_shader with action="apply".
  1b. Use emulator hints when the user specifies platform/emulator (e.g., MAME vs RetroArch). If unclear, ask which emulator they mean.
2. **PLATFORM HINTS**: When users mention a platform (e.g., "Galaga arcade", "Mario NES", "Sonic Genesis"), ALWAYS pass the platform filter to search_games:
   - "arcade" or "MAME" = platform: "Arcade MAME"
   - "NES" or "Nintendo" = platform: "Nintendo Entertainment System"
   - "SNES" = platform: "Super Nintendo Entertainment System"
   - "Genesis" = platform: "Sega Genesis"
   - This should narrow results to ONE game in most cases - if so, launch it immediately!
3. **DISAMBIGUATION**: ONLY ask for clarification if there are genuinely MULTIPLE different games after applying platform filter:
   - "Street Fighter" alone = shows II, Alpha, III (different games) - ask which one
   - "Galaga arcade" = only ONE Galaga on Arcade MAME - launch it directly!
   - If the user says something like "the original" or "the classic" or "1981", that's the oldest version - launch it
4. **SINGLE MATCH**: If only ONE game matches (after platform filter), you MUST call launch_game with the game_id BEFORE responding. Then confirm: "Found it! [Title] ([Platform], [Year]). Launching now! 🎮"
5. **FALLBACK SEARCH - CRITICAL**: When search returns NO results:
   - IMMEDIATELY search again WITHOUT the platform filter to find similar games
   - Example: If "Street Fighter 2 arcade" finds nothing, search just "Street Fighter" to find all Street Fighter games
   - Present the closest matches: "I couldn't find 'Street Fighter 2' exactly on MAME, but here are the Street Fighter games we have: [list]. Which one did you mean?"
   - NEVER just say "I can't find it" without offering alternatives from the library!
   - The user expects you to be HELPFUL - always suggest what IS available
6. **TITLE VARIATIONS**: Many games have Roman numerals (II, III, IV) instead of Arabic numbers (2, 3, 4):
   - "Street Fighter 2" = "Street Fighter II"
   - "Final Fantasy 7" = "Final Fantasy VII"
   - If user says a number, also check the Roman numeral version
7. Provide specific game recommendations with year and genre
8. If a filter is active, acknowledge it in your response
9. Suggest related games when appropriate
10. Keep responses warm and concise (2-3 sentences plus game details)
11. Never mention Anthropic, Claude, or the underlying model—respond only as LoRa

CRITICAL - NEVER HALLUCINATE LAUNCHES:
- You MUST call the launch_game tool to actually start a game. Saying "launching" without calling the tool does NOTHING.
- ALWAYS use the launch_game tool with the game_id when the user wants to play a game.
- If you say "launching" or "starting" a game, you MUST have called launch_game in the same turn.
- The user will not see the game start unless you execute the launch_game tool.

EXAMPLE INTERACTIONS:
User: "Show me fighting games"
You: Use filter_games with genre="Fighting", then say something like "Oh you want to throw hands? 🥊 We've got some great fighters - Street Fighter II, Tekken 3, Mortal Kombat... What style are you feeling?"

User: "Launch Street Fighter"
You: Use search_games, see multiple matches, then: "Street Fighter! Classic choice. We've got a few versions - II Turbo, Alpha 3, Third Strike... Which era are you feeling?"

User: "The arcade one"
You: Find the arcade version, call launch_game, then: "Street Fighter II arcade - let's go! 🔥 Get ready for some hadoukens!"

User: "What should I play?" or "What do you recommend?"
You: Use get_random_game OR filter by platform if specified, then give an enthusiastic pitch: "Ooh, how about Castlevania: Symphony of the Night? It's a masterpiece - gorgeous pixel art, epic soundtrack, and you get to flip the whole castle upside down halfway through. Absolute banger. Want me to fire it up?"

User: "What would you recommend for PS2?" or "What's good on PS2?"
You: DO NOT just search for "recommend" or "ps2"! Instead, use filter_games with platform="Sony Playstation 2", then give a personalized recommendation: "PS2? You're in for a treat! 🎮 Some heavy hitters: God of War if you want action, Kingdom Hearts for adventure, or Final Fantasy X for an epic RPG. What genre sounds good right now?"

User: "Something fun"
You: Use get_random_game, then sell it: "How about Burnout 3: Takedown? Nothing says fun like causing massive pileups at 150mph. Pure chaos. 🔥"

REMEMBER: You're the fun friend who knows every game, not a search engine!`;

  return prompt;
}

/**
 * Execute the tool calling loop until Claude stops requesting tools
 *
 * This implements the Anthropic tool calling pattern:
 * 1. Call Claude with user message
 * 2. If stop_reason === 'tool_use':
 *    - Execute tools
 *    - Build tool_result messages
 *    - Call Claude again with results
 * 3. Repeat until stop_reason !== 'tool_use'
 * 4. Return final text response
 */
async function executeToolCallingLoop(systemPrompt, messages, toolEnv = {}) {
  const apiKey = process.env.ANTHROPIC_API_KEY || process.env.CLAUDE_API_KEY;
  const supabaseConfigured = Boolean(process.env.SUPABASE_URL && process.env.SUPABASE_SERVICE_ROLE_KEY);

  // Allow either direct API key OR Supabase proxy
  if (!apiKey && !supabaseConfigured) {
    throw new Error('AI not configured: set ANTHROPIC_API_KEY or SUPABASE_URL + SUPABASE_SERVICE_ROLE_KEY');
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
  let lastModel = 'gemini-2.0-flash';
  let totalInputTokens = 0;
  let totalOutputTokens = 0;

  // Main tool calling loop
  while (continueLoop && rounds < maxRounds) {
    rounds++;
    console.log(`[LaunchBox AI] Round ${rounds}: Calling Claude...`);
    try {
      console.log('[LoRa Debug] Pre-call history length:', messages.length);
      console.log('[LoRa Debug] Pre-call last 2:', messages.slice(-2).map(m => ({ role: m.role, types: (Array.isArray(m.content) ? m.content.map(c => c.type) : typeof m.content) })));
    } catch (_) { }

    // Call Claude API
    const response = await callClaudeAPI(systemPrompt, messages);

    // Track provider/model/usage for telemetry
    if (response.provider) lastProvider = response.provider;
    if (response.model) lastModel = response.model;
    if (response.usage) {
      totalInputTokens += response.usage.prompt_tokens || response.usage.input_tokens || 0;
      totalOutputTokens += response.usage.completion_tokens || response.usage.output_tokens || 0;
    }

    console.log(`[LaunchBox AI] Round ${rounds} stop_reason:`, response.stop_reason);

    // Extract text content from this response
    const textBlocks = response.content.filter(b => b.type === 'text');
    const currentText = textBlocks.map(b => b.text).join('\n');
    if (currentText) {
      finalText = currentText; // Keep the latest text
    }

    // Check if Claude wants to use tools
    if (response.stop_reason === 'tool_use') {
      // Extract tool use blocks
      const toolUseBlocks = response.content.filter(b => b.type === 'tool_use');

      console.log(`[LaunchBox AI] Round ${rounds}: ${toolUseBlocks.length} tool(s) requested`);

      // Add assistant's response to conversation (must include ALL content blocks)
      messages.push({
        role: 'assistant',
        content: response.content
      });
      try { console.log('[LoRa Debug] After assistant tool_use, history length:', messages.length); } catch (_) { }

      // Execute all tools and build tool_result blocks
      const toolResultBlocks = [];
      // Workflow guard flags
      const hasShaderPreview = toolUseBlocks.some(b => b.name === 'manage_shader' && (b.input?.action === 'preview'));
      let shaderAppliedThisRound = false;

      for (const toolUse of toolUseBlocks) {
        console.log(`[LaunchBox AI] Executing tool: ${toolUse.name}`, toolUse.input);

        // Special-case: manage_shader tool inline to control headers and result shape
        if (toolUse.name === 'manage_shader') {
          const BACKEND_URL = toolEnv.backendUrl;
          const args = toolUse.input || {};
          const { action, game_id, shader_name, emulator } = args;
          try {
            if (action === 'get_current') {
              const response = await fetch(`${BACKEND_URL}/api/launchbox/shaders/game/${encodeURIComponent(game_id)}`, {
                headers: {
                  'x-scope': 'state',
                  'x-device-id': (toolEnv.headers && toolEnv.headers['x-device-id']) || 'unknown',
                  'x-panel': 'launchbox'
                }
              });
              const currentShader = await response.json().catch(() => ({}));
              toolResultBlocks.push({
                type: 'tool_result',
                tool_use_id: toolUse.id,
                content: JSON.stringify({
                  status: 'current_shader',
                  game_id,
                  shader: currentShader?.shader ?? currentShader?.shader_name ?? 'none',
                  data: currentShader
                })
              });
              toolCallsMade.push({ name: 'manage_shader', input: args, result: { status: 'current_shader', data: currentShader } });
              continue;
            }

            if (action === 'preview') {
              if (!shader_name || !emulator) {
                toolResultBlocks.push({
                  type: 'tool_result',
                  tool_use_id: toolUse.id,
                  content: JSON.stringify({ status: 'error', message: 'shader_name and emulator required for preview action' })
                });
                toolCallsMade.push({ name: 'manage_shader', input: args, result: { status: 'error' } });
                continue;
              }
              const response = await fetch(`${BACKEND_URL}/api/launchbox/shaders/preview`, {
                method: 'POST',
                headers: {
                  'Content-Type': 'application/json',
                  'x-scope': 'state',
                  'x-device-id': (toolEnv.headers && toolEnv.headers['x-device-id']) || 'unknown',
                  'x-panel': 'launchbox'
                },
                body: JSON.stringify({ game_id, shader_name, emulator })
              });
              let preview = await response.json().catch(() => ({}));

              // Fallback: if shader not found for requested emulator, try alternate emulator based on catalog
              if (preview?.error && /not found/i.test(preview.error)) {
                try {
                  const catResp = await fetch(`${BACKEND_URL}/api/launchbox/shaders/available`, {
                    headers: { 'x-scope': 'state', 'x-panel': 'launchbox', 'x-device-id': (toolEnv.headers && toolEnv.headers['x-device-id']) || 'unknown' }
                  });
                  const catalog = await catResp.json().catch(() => ({}));
                  const inRA = Array.isArray(catalog?.retroarch) && catalog.retroarch.some(s => s?.name === shader_name);
                  const inMame = Array.isArray(catalog?.mame) && catalog.mame.some(s => s?.name === shader_name);
                  let effectiveEmulator = emulator;
                  if (inRA && emulator !== 'retroarch') effectiveEmulator = 'retroarch';
                  else if (inMame && emulator !== 'mame') effectiveEmulator = 'mame';
                  if (effectiveEmulator !== emulator) {
                    const retry = await fetch(`${BACKEND_URL}/api/launchbox/shaders/preview`, {
                      method: 'POST',
                      headers: {
                        'Content-Type': 'application/json',
                        'x-scope': 'state',
                        'x-device-id': (toolEnv.headers && toolEnv.headers['x-device-id']) || 'unknown',
                        'x-panel': 'launchbox'
                      },
                      body: JSON.stringify({ game_id, shader_name, emulator: effectiveEmulator })
                    });
                    const retryBody = await retry.json().catch(() => ({}));
                    if (retry.ok && (retryBody?.diff || retryBody?.new)) {
                      preview = retryBody;
                      // update emulator for the preview result
                      args.emulator = effectiveEmulator;
                    }
                  }
                  // If still failing on mame, try a sensible chain like 'crt-geom'
                  if ((!preview || preview?.error) && (effectiveEmulator === 'mame' || emulator === 'mame')) {
                    const mameList = Array.isArray(catalog?.mame) ? catalog.mame : [];
                    const crtCandidate = mameList.find(s => /crt/i.test(s?.name)) || mameList.find(Boolean);
                    if (crtCandidate?.name) {
                      const retry2 = await fetch(`${BACKEND_URL}/api/launchbox/shaders/preview`, {
                        method: 'POST',
                        headers: {
                          'Content-Type': 'application/json',
                          'x-scope': 'state',
                          'x-device-id': (toolEnv.headers && toolEnv.headers['x-device-id']) || 'unknown',
                          'x-panel': 'launchbox'
                        },
                        body: JSON.stringify({ game_id, shader_name: crtCandidate.name, emulator: 'mame' })
                      });
                      const retryBody2 = await retry2.json().catch(() => ({}));
                      if (retry2.ok && (retryBody2?.diff || retryBody2?.new)) {
                        preview = retryBody2;
                        args.emulator = 'mame';
                        args.shader_name = crtCandidate.name;
                      }
                    }
                  }
                } catch (_) { /* ignore fallback failures */ }
              }

              // Build tool result (success or error)
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

              toolResultBlocks.push({
                type: 'tool_result',
                tool_use_id: toolUse.id,
                content: JSON.stringify(contentPayload)
              });
              toolCallsMade.push({ name: 'manage_shader', input: args, result: preview });
              continue;
            }

            if (action === 'apply') {
              if (!shader_name || !emulator) {
                toolResultBlocks.push({
                  type: 'tool_result',
                  tool_use_id: toolUse.id,
                  content: JSON.stringify({ status: 'error', message: 'shader_name and emulator required for apply action' })
                });
                toolCallsMade.push({ name: 'manage_shader', input: args, result: { status: 'error' } });
                continue;
              }
              const response = await fetch(`${BACKEND_URL}/api/launchbox/shaders/apply`, {
                method: 'POST',
                headers: {
                  'Content-Type': 'application/json',
                  'x-scope': 'config',
                  'x-device-id': (toolEnv.headers && toolEnv.headers['x-device-id']) || 'unknown',
                  'x-panel': 'launchbox'
                },
                body: JSON.stringify({ game_id, shader_name, emulator })
              });
              let result = await response.json().catch(() => ({}));
              let success = Boolean(result?.success);
              // Fallback: if not found, try alternate emulator once based on catalog
              if (!success && result?.error && /not found/i.test(result.error)) {
                try {
                  const catResp = await fetch(`${BACKEND_URL}/api/launchbox/shaders/available`, {
                    headers: { 'x-scope': 'state', 'x-panel': 'launchbox', 'x-device-id': (toolEnv.headers && toolEnv.headers['x-device-id']) || 'unknown' }
                  });
                  const catalog = await catResp.json().catch(() => ({}));
                  const inRA = Array.isArray(catalog?.retroarch) && catalog.retroarch.some(s => s?.name === shader_name);
                  const inMame = Array.isArray(catalog?.mame) && catalog.mame.some(s => s?.name === shader_name);
                  let alt = null;
                  if (inRA && emulator !== 'retroarch') alt = 'retroarch';
                  else if (inMame && emulator !== 'mame') alt = 'mame';
                  if (alt) {
                    const retryResp = await fetch(`${BACKEND_URL}/api/launchbox/shaders/apply`, {
                      method: 'POST',
                      headers: {
                        'Content-Type': 'application/json',
                        'x-scope': 'config',
                        'x-device-id': (toolEnv.headers && toolEnv.headers['x-device-id']) || 'unknown',
                        'x-panel': 'launchbox'
                      },
                      body: JSON.stringify({ game_id, shader_name, emulator: alt })
                    });
                    const retryBody = await retryResp.json().catch(() => ({}));
                    if (retryResp.ok && retryBody?.success) {
                      result = retryBody;
                      success = true;
                      args.emulator = alt;
                    }
                  }
                  // If still failing on mame, try a sensible chain such as 'crt-geom'
                  if (!success && (alt === 'mame' || emulator === 'mame')) {
                    const mameList = Array.isArray(catalog?.mame) ? catalog.mame : [];
                    const crtCandidate = mameList.find(s => /crt/i.test(s?.name)) || mameList.find(Boolean);
                    if (crtCandidate?.name) {
                      const retry2 = await fetch(`${BACKEND_URL}/api/launchbox/shaders/apply`, {
                        method: 'POST',
                        headers: {
                          'Content-Type': 'application/json',
                          'x-scope': 'config',
                          'x-device-id': (toolEnv.headers && toolEnv.headers['x-device-id']) || 'unknown',
                          'x-panel': 'launchbox'
                        },
                        body: JSON.stringify({ game_id, shader_name: crtCandidate.name, emulator: 'mame' })
                      });
                      const retryBody2 = await retry2.json().catch(() => ({}));
                      if (retry2.ok && retryBody2?.success) {
                        result = retryBody2;
                        success = true;
                        args.emulator = 'mame';
                        args.shader_name = crtCandidate.name;
                      }
                    }
                  }
                } catch (_) { /* ignore fallback failures */ }
              }
              const msg = success
                ? `Shader '${shader_name}' applied successfully. Backup: ${result?.backup_path || 'none'}`
                : `Failed to apply shader: ${result?.error || 'unknown error'}`;
              toolResultBlocks.push({
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
              });
              toolCallsMade.push({ name: 'manage_shader', input: args, result });
              if (success) shaderAppliedThisRound = true;
              continue;
            }

            if (action === 'remove') {
              const qs = new URLSearchParams();
              if (emulator) qs.append('emulator', emulator);
              const url = `${BACKEND_URL}/api/launchbox/shaders/game/${encodeURIComponent(game_id)}${qs.toString() ? `?${qs.toString()}` : ''}`;
              const response = await fetch(url, {
                method: 'DELETE',
                headers: {
                  'x-scope': 'config',
                  'x-device-id': (toolEnv.headers && toolEnv.headers['x-device-id']) || 'unknown',
                  'x-panel': 'launchbox'
                }
              });
              const result = await response.json().catch(() => ({}));
              const success = Boolean(result?.success);
              const removedCount = Number(result?.removed_count || 0);
              const msg = success
                ? `Removed ${removedCount} shader binding(s) for ${game_id}`
                : `Failed to remove shader: ${result?.error || 'unknown error'}`;
              toolResultBlocks.push({
                type: 'tool_result',
                tool_use_id: toolUse.id,
                content: JSON.stringify({
                  status: success ? 'removed' : 'error',
                  game_id,
                  removed_count: removedCount,
                  message: msg
                })
              });
              toolCallsMade.push({ name: 'manage_shader', input: args, result });
              continue;
            }

            // Unknown action
            toolResultBlocks.push({
              type: 'tool_result',
              tool_use_id: toolUse.id,
              content: JSON.stringify({ status: 'error', message: `Unknown action: ${action}` })
            });
            toolCallsMade.push({ name: 'manage_shader', input: args, result: { status: 'error' } });
            continue;

          } catch (e) {
            toolResultBlocks.push({
              type: 'tool_result',
              tool_use_id: toolUse.id,
              content: JSON.stringify({ status: 'error', message: e.message })
            });
            toolCallsMade.push({ name: 'manage_shader', input: args, result: { status: 'error', message: e.message } });
            continue;
          }
        }

        // Execute the tool via shared module
        const toolFunction = launchboxTools[toolUse.name];
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

      // Continue loop - Claude will process tool results
      continueLoop = true;

    } else {
      // Claude finished (stop_reason is 'end_turn' or 'max_tokens')
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
    // Try Anthropic proxy first
    try {
      const proxyUrl = `${process.env.SUPABASE_URL}/functions/v1/anthropic-proxy`;
      const response = await fetchWithRetry(proxyUrl, {
        method: 'POST',
        headers: {
          'content-type': 'application/json',
          'Authorization': `Bearer ${process.env.SUPABASE_SERVICE_ROLE_KEY}`
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
        console.warn(`[LaunchBox AI] Anthropic proxy failed (${response.status}), trying Gemini fallback...`);
        // Fall through to Gemini
        return await callGeminiAPI(systemPrompt, messages);
      }
      const data = await response.json();
      // Add telemetry metadata
      return { ...data, provider: 'anthropic', model: modelToUse };
    } catch (anthropicError) {
      console.warn('[LaunchBox AI] Anthropic proxy error, trying Gemini fallback:', anthropicError.message);
      return await callGeminiAPI(systemPrompt, messages);
    }
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

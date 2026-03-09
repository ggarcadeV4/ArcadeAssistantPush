/**
 * LaunchBox LoRa AI Tools
 * Created: 2025-10-06
 *
 * Tool functions that the AI can call to interact with the LaunchBox game library.
 * Each tool maps to backend API endpoints.
 */

/**
 * Get the FastAPI URL from app.locals (injected at runtime)
 */
let fastapiUrl = null;
let clientContext = { deviceId: 'unknown', panel: 'launchbox' };
import fs from 'fs';
import path from 'path';

// Simple circuit breaker for plugin-backed calls
const pluginBreaker = {
  failureCount: 0,
  openedUntil: 0,
  threshold: 3,      // failures before opening breaker
  cooldownMs: 60_000 // cool-down period
};

function nowMs() { return Date.now(); }
function breakerOpen() { return nowMs() < pluginBreaker.openedUntil; }
function recordFailure() {
  pluginBreaker.failureCount += 1;
  if (pluginBreaker.failureCount >= pluginBreaker.threshold) {
    pluginBreaker.openedUntil = nowMs() + pluginBreaker.cooldownMs;
  }
}
function recordSuccess() {
  pluginBreaker.failureCount = 0;
  pluginBreaker.openedUntil = 0;
}

export function setFastapiUrl(url) {
  fastapiUrl = url;
}

export function setClientContext(ctx = {}) {
  clientContext.deviceId = ctx.deviceId || clientContext.deviceId || 'unknown';
  clientContext.panel = ctx.panel || clientContext.panel || 'launchbox';
}

// -------------------- Query Normalization Helpers --------------------
const platformSynonyms = {
  'nes': 'Nintendo Entertainment System',
  'nintendo entertainment system': 'Nintendo Entertainment System',
  'snes': 'Super Nintendo Entertainment System',
  'super nintendo': 'Super Nintendo Entertainment System',
  'genesis': 'Sega Genesis',
  'mega drive': 'Sega Genesis',
  'master system': 'Sega Master System',
  'game gear': 'Sega Game Gear',
  'ps1': 'Sony Playstation',
  'playstation 1': 'Sony Playstation',
  'playstation': 'Sony Playstation',
  'psx': 'Sony Playstation',
  'ps2': 'Sony Playstation 2',
  'ps3': 'Sony Playstation 3',
  'ps 3': 'Sony Playstation 3',
  'playstation 3': 'Sony Playstation 3',
  'sony playstation 3': 'Sony Playstation 3',
  'rpcs3': 'Sony Playstation 3',
  'teknoparrot': 'TeknoParrot',
  'tekno parrot': 'TeknoParrot',
  'daphne': 'Daphne',
  'hypseus': 'Daphne',
  'laserdisc': 'Daphne',
  'laser disc': 'Daphne',
  'american laser games': 'American Laser Games',
  'alg': 'American Laser Games',
  'gamecube': 'Nintendo GameCube',
  'gc': 'Nintendo GameCube',
  'wii': 'Nintendo Wii',
  'dreamcast': 'Sega Dreamcast',
  'arcade': 'Arcade'
};

function normalizePlatformName(p) {
  if (!p) return undefined;
  const key = String(p).trim().toLowerCase();
  return platformSynonyms[key] || p;
}

let aliasCache = null;
function loadTitleAliases() {
  if (aliasCache) return aliasCache;
  try {
    const drive = process.env.AA_DRIVE_ROOT || process.cwd();
    const p = path.join(drive, 'configs', 'title_aliases.json');
    if (fs.existsSync(p)) {
      const data = JSON.parse(fs.readFileSync(p, 'utf8'));
      aliasCache = (data && data.aliases) || {};
    } else {
      aliasCache = {};
    }
  } catch (_) {
    aliasCache = {};
  }
  return aliasCache;
}

function extractGamesList(payload) {
  if (Array.isArray(payload)) return payload;
  if (payload && Array.isArray(payload.games)) return payload.games;
  return [];
}

function applyTitleAlias(title) {
  try {
    const builtins = {
      'miss pac-man': 'ms. pac-man',
      'miss pacman': 'ms. pac-man',
      'ms pacman': 'ms. pac-man',
      'mspacman': 'ms. pac-man',
      'ms pac-man': 'ms. pac-man',
    };
    const aliases = { ...(loadTitleAliases() || {}), ...builtins };
    const key = String(title || '').trim().toLowerCase();
    // exact alias match
    if (aliases[key]) return aliases[key];
    return title;
  } catch { return title; }
}

function extractPlatformFromQuery(q) {
  if (!q) return { cleanedTitle: q, platformHint: undefined };
  const s = String(q).trim();
  // common verbs
  let t = s.replace(/^\s*(please\s*)?(can you|could you|would you|please|kindly)?\s*(launch|play|start|open)\s*/i, '').trim();
  // capture platform with "on|for|from <platform>"
  const m = t.match(/\s+(?:on|for|from|in)\s+(?:the\s+)?([^,.;]+)$/i);
  let platformHint;
  if (m && m[1]) {
    platformHint = normalizePlatformName(m[1]);
    t = t.slice(0, m.index).trim();
  }
  // strip trailing polite words
  t = t
    .replace(/\s+(?:arcade|mame)\s+(?:version|edition)\s*$/i, '')
    .replace(/\s+(?:version|edition|release)\s*$/i, '')
    .replace(/\s*(please|thanks)\.?$/i, '')
    .trim();
  return { cleanedTitle: t, platformHint };
}

/**
 * Tool Definitions for Claude API
 * These are passed to the AI so it knows what functions it can call
 */
export const launchboxToolDefinitions = [
  {
    name: 'filter_games',
    description: 'Filter the game library by genre, decade, or platform. Returns a list of matching games.',
    input_schema: {
      type: 'object',
      properties: {
        genre: {
          type: 'string',
          description: 'Filter by genre (e.g., "Fighting", "Maze", "Shooter", "Platformer")'
        },
        decade: {
          type: 'integer',
          description: 'Filter by decade (e.g., 1980, 1990, 2000)'
        },
        platform: {
          type: 'string',
          description: 'Filter by platform (e.g., "Arcade", "NES", "SNES")'
        },
        sort_by: {
          type: 'string',
          enum: ['year_asc', 'year_desc', 'title_asc', 'title_desc'],
          description: 'Sort order: year_asc (oldest first), year_desc (newest first), title_asc, title_desc'
        },
        limit: {
          type: 'integer',
          description: 'Maximum number of games to return (default: 50)',
          default: 50
        }
      }
    }
  },
  {
    name: 'search_games',
    description: 'Search for games by title. Supports partial matches and semantic filtering for "original", "first", "classic", or "base" qualifiers to prioritize base games over variants.',
    input_schema: {
      type: 'object',
      properties: {
        query: {
          type: 'string',
          description: 'Search query (e.g., "Street Fighter", "original Pac-Man", "first Donkey Kong"). Include qualifiers like "original", "first", "classic" to filter out sequels and variants.'
        },
        platform: {
          type: 'string',
          description: 'Optional platform filter (e.g., "Atari 2600", "NES")'
        }
      },
      required: ['query']
    }
  },
  {
    name: 'get_random_game',
    description: 'Get a random game suggestion, optionally filtered by genre or platform.',
    input_schema: {
      type: 'object',
      properties: {
        genre: {
          type: 'string',
          description: 'Optional genre filter'
        },
        platform: {
          type: 'string',
          description: 'Optional platform filter'
        }
      }
    }
  },
  {
    name: 'launch_game',
    description: 'Launch a game by its ID. Use this after getting game details from filter_games or search_games.',
    input_schema: {
      type: 'object',
      properties: {
        game_id: {
          type: 'string',
          description: 'The unique ID of the game to launch'
        }
      },
      required: ['game_id']
    }
  },
  {
    name: 'get_library_stats',
    description: 'Get statistics about the game library (total games, platforms, genres).',
    input_schema: {
      type: 'object',
      properties: {}
    }
  },
  {
    name: 'get_available_genres',
    description: 'Get a list of all available genres in the library.',
    input_schema: {
      type: 'object',
      properties: {}
    }
  },
  {
    name: 'get_available_platforms',
    description: 'Get a list of all available platforms in the library.',
    input_schema: {
      type: 'object',
      properties: {}
    }
  },
  {
    name: 'manage_shader',
    description:
      'Apply, preview, or remove visual shader presets for a specific game. Shaders add visual effects like CRT scanlines, LCD grids, sharp pixels, etc.',
    input_schema: {
      type: 'object',
      properties: {
        action: {
          type: 'string',
          enum: ['preview', 'apply', 'remove', 'get_current'],
          description:
            'Action to perform: preview (show diff), apply (save shader), remove (delete shader), get_current (check existing shader)'
        },
        game_id: {
          type: 'string',
          description: "LaunchBox game ID (e.g., 'sf2' for Street Fighter 2)"
        },
        shader_name: {
          type: 'string',
          description: "Shader preset name (e.g., 'crt-royale', 'lcd-grid', 'sharp-bilinear'). Required for preview and apply actions."
        },
        emulator: {
          type: 'string',
          enum: ['mame', 'retroarch'],
          description: 'Target emulator for shader. Required for preview and apply actions.'
        },
        parameters: {
          type: 'object',
          description: 'Optional shader parameters for advanced presets'
        }
      },
      required: ['action', 'game_id']
    }
  },
  {
    name: 'get_marquee_game',
    description: 'Get information about the game currently displayed on the marquee (the game the user is looking at or has selected). Use this when the user asks "what game is this?", "tell me about this game", or "what am I looking at?".',
    input_schema: {
      type: 'object',
      properties: {}
    }
  },
  {
    name: 'find_similar_games',
    description: 'Find games similar to the current marquee game or a specified game. Use this when the user asks "show me games like this", "what else is similar?", or "find more like this".',
    input_schema: {
      type: 'object',
      properties: {
        game_id: {
          type: 'string',
          description: 'Optional game ID to find similar games for. If not provided, uses the current marquee game.'
        },
        limit: {
          type: 'integer',
          description: 'Maximum number of similar games to return (default: 5)',
          default: 5
        }
      }
    }
  }
];

/**
 * Tool Execution Functions
 * These are called when the AI decides to use a tool
 */
export const launchboxTools = {
  /**
   * Filter games by genre, decade, or platform
   */
  filter_games: async (params) => {
    const { genre, decade, platform, sort_by, limit = 50 } = params;

    const queryParams = new URLSearchParams();
    if (genre) queryParams.append('genre', genre);
    if (decade) queryParams.append('decade', decade);
    if (platform) queryParams.append('platform', platform);
    if (params.search) queryParams.append('search', params.search);
    queryParams.append('limit', limit);

    try {
      const response = await fetch(`${fastapiUrl}/api/launchbox/games?${queryParams}`);
      if (!response.ok) throw new Error(`Backend error: ${response.status}`);

      const payload = await response.json();
      let games = extractGamesList(payload);

      // Apply client-side sorting if requested
      if (sort_by) {
        games = [...games].sort((a, b) => {
          switch (sort_by) {
            case 'year_asc':
              return (a.year || 9999) - (b.year || 9999);
            case 'year_desc':
              return (b.year || 0) - (a.year || 0);
            case 'title_asc':
              return (a.title || '').localeCompare(b.title || '');
            case 'title_desc':
              return (b.title || '').localeCompare(a.title || '');
            default:
              return 0;
          }
        });
      }

      return {
        success: true,
        count: games.length,
        total: payload?.total,
        games: games.map(g => ({
          id: g.id,
          title: g.title,
          genre: g.genre,
          platform: g.platform,
          year: g.year,
          play_count: g.play_count || 0
        }))
      };
    } catch (error) {
      return {
        success: false,
        error: error.message
      };
    }
  },

  /**
   * Search games by title using the C# Plugin Bridge (LaunchBox source of truth)
   *
   * This uses /api/launchbox/resolve which queries LaunchBox directly via the plugin.
   * The plugin returns REAL LaunchBox game IDs that can be used for launching.
   */
  search_games: async (params) => {
    const { query } = params;
    // Normalize user query into title + platform
    const { cleanedTitle, platformHint } = extractPlatformFromQuery(query);
    const normalizedTitle = applyTitleAlias(cleanedTitle);
    const platform = normalizePlatformName(params.platform || platformHint);

    // Helper to apply "original" filter heuristic
    const filterOriginals = (list) => {
      const wantsOriginal = /\b(original|first|classic|base)\b/i.test(query);
      if (!wantsOriginal || !Array.isArray(list) || list.length <= 1) return list;
      const variantPrefixPattern = /^(jr\.|super|professor|ms\.|baby|mega|ultra|turbo|new|enhanced|deluxe|special|dx|ex|plus|ii|iii|2|3|4|5|6|7|8|9)/i;
      const variantSuffixPattern = /(championship|edition|collection|remix|remastered|hd|redux|ultimate|gold|platinum)$/i;
      let games = list.filter(g => {
        const title = (g.title || '').toLowerCase();
        return !variantPrefixPattern.test(title) && !variantSuffixPattern.test(title);
      });
      games.sort((a, b) => {
        const lengthDiff = (a.title || '').length - (b.title || '').length;
        if (lengthDiff !== 0) return lengthDiff;
        return (a.year || 9999) - (b.year || 9999);
      });
      return games;
    };

    // First try plugin-backed resolve (source of truth for IDs)
    try {
      if (breakerOpen()) throw new Error('plugin_circuit_open');
      const resolveBody = {
        game_name: normalizedTitle,
        limit: 50
      };
      if (platform) resolveBody.platform = platform;

      const response = await fetch(`${fastapiUrl}/api/launchbox/resolve`, {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
          'x-panel': clientContext.panel || 'launchbox',
          'x-device-id': clientContext.deviceId || 'unknown'
        },
        body: JSON.stringify(resolveBody)
      });
      const payload = await response.json().catch(() => ({}));
      if (!response.ok) throw new Error(payload?.message || `Backend error: ${response.status}`);

      const normalizeMatches = (data) => {
        if (Array.isArray(data)) return data;
        if (data?.status === 'resolved' && data.game) return [data.game];
        if (data?.status === 'multiple_matches' && Array.isArray(data.suggestions)) return data.suggestions;
        return [];
      };

      const games = filterOriginals(normalizeMatches(payload));
      recordSuccess();
      return {
        success: true,
        count: games.length,
        games: games.slice(0, 10).map(g => ({
          id: g.id,
          title: g.title,
          genre: g.genre,
          platform: g.platform,
          year: g.year
        }))
      };
    } catch (error) {
      // Open breaker on plugin failures other than HTTP 4xx from fallback
      if (String(error.message || '').indexOf('plugin_circuit_open') === -1) {
        recordFailure();
      }
      // Fallback: local search via backend library if plugin is offline
      try {
        const fallbackParams = new URLSearchParams({ search: normalizedTitle, limit: '50' });
        if (platform) fallbackParams.append('platform', platform);
        const resp = await fetch(`${fastapiUrl}/api/launchbox/games?${fallbackParams.toString()}`);
        if (!resp.ok) throw new Error(`Backend error: ${resp.status}`);
        const gamesRaw = await resp.json();
        const games = filterOriginals(extractGamesList(gamesRaw));
        return {
          success: true,
          count: games.length,
          games: games.slice(0, 10).map(g => ({
            id: g.id,
            title: g.title,
            genre: g.genre,
            platform: g.platform,
            year: g.year
          }))
        };
      } catch (fallbackErr) {
        return {
          success: false,
          error: fallbackErr.message
        };
      }
    }
  },

  /**
   * Get a random game suggestion
   */
  get_random_game: async (params) => {
    const { genre, platform } = params;

    const queryParams = new URLSearchParams();
    if (genre) queryParams.append('genre', genre);
    if (platform) queryParams.append('platform', platform);

    try {
      const response = await fetch(`${fastapiUrl}/api/launchbox/random?${queryParams}`);
      if (!response.ok) throw new Error(`Backend error: ${response.status}`);

      const game = await response.json();

      return {
        success: true,
        game: {
          id: game.id,
          title: game.title,
          genre: game.genre,
          platform: game.platform,
          year: game.year,
          developer: game.developer,
          publisher: game.publisher
        }
      };
    } catch (error) {
      return {
        success: false,
        error: error.message
      };
    }
  },

  /**
   * Launch a game by ID
   */
  launch_game: async (params) => {
    const { game_id } = params;

    try {
      // Side-effect operation — do NOT use fetchWithRetry (spawns emulator)
      const response = await fetch(`${fastapiUrl}/api/launchbox/launch/${game_id}`, {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
          'x-panel': 'launchbox',
          'x-device-id': clientContext.deviceId || 'unknown',
          'x-corr-id': `${Date.now()}-${Math.random().toString(36).slice(2)}`
        }
      });

      if (!response.ok) throw new Error(`Backend error: ${response.status}`);

      const result = await response.json();

      return {
        game_id: result.game_id,
        game_title: result.game_title,
        success: result.success,
        method_used: result.method_used,
        message: result.message,
        command: result.command
      };
    } catch (error) {
      return {
        success: false,
        error: error.message
      };
    }
  },

  /**
   * Get library statistics
   */
  get_library_stats: async () => {
    try {
      const response = await fetch(`${fastapiUrl}/api/launchbox/stats`);
      if (!response.ok) throw new Error(`Backend error: ${response.status}`);

      const stats = await response.json();

      return {
        success: true,
        stats: {
          total_games: stats.total_games,
          platforms_count: stats.platforms_count,
          genres_count: stats.genres_count,
          is_mock_data: stats.is_mock_data,
          a_drive_status: stats.a_drive_status
        }
      };
    } catch (error) {
      return {
        success: false,
        error: error.message
      };
    }
  },

  /**
   * Get available genres
   */
  get_available_genres: async () => {
    try {
      const response = await fetch(`${fastapiUrl}/api/launchbox/genres`);
      if (!response.ok) throw new Error(`Backend error: ${response.status}`);

      const genres = await response.json();

      return {
        success: true,
        genres
      };
    } catch (error) {
      return {
        success: false,
        error: error.message
      };
    }
  },

  /**
   * Get available platforms
   */
  get_available_platforms: async () => {
    try {
      const response = await fetch(`${fastapiUrl}/api/launchbox/platforms`);
      if (!response.ok) throw new Error(`Backend error: ${response.status}`);

      const platforms = await response.json();

      return {
        success: true,
        platforms
      };
    } catch (error) {
      return {
        success: false,
        error: error.message
      };
    }
  },

  /**
   * Manage per-game shaders: preview/apply/remove/get_current
   */
  manage_shader: async (params) => {
    const { action, game_id, shader_name, emulator, parameters } = params || {};

    if (!action || !game_id) {
      return { success: false, error: 'action and game_id are required' };
    }

    try {
      if (action === 'get_current') {
        const resp = await fetch(`${fastapiUrl}/api/launchbox/shaders/game/${encodeURIComponent(game_id)}`, {
          method: 'GET',
          headers: {
            'x-scope': 'state',
            'x-panel': clientContext.panel || 'launchbox',
            'x-device-id': clientContext.deviceId || 'unknown'
          }
        });
        const body = await resp.json().catch(() => ({}));
        if (!resp.ok) throw new Error(body?.error || `Backend error: ${resp.status}`);
        return {
          status: 'current_shader',
          game_id,
          shader: body?.shader ?? body?.shader_name ?? 'none',
          data: body
        };
      }

      if (action === 'preview') {
        if (!shader_name || !emulator) {
          return { success: false, error: 'shader_name and emulator are required for preview' };
        }
        const resp = await fetch(`${fastapiUrl}/api/launchbox/shaders/preview`, {
          method: 'POST',
          headers: {
            'Content-Type': 'application/json',
            'x-scope': 'state',
            'x-panel': clientContext.panel || 'launchbox',
            'x-device-id': clientContext.deviceId || 'unknown'
          },
          body: JSON.stringify({ game_id, shader_name, emulator, parameters })
        });
        const body = await resp.json().catch(() => ({}));
        if (!resp.ok) throw new Error(body?.error || `Backend error: ${resp.status}`);
        return {
          status: 'preview',
          game_id,
          emulator,
          shader_name,
          diff: body?.diff,
          old: body?.old,
          new: body?.new,
          data: body
        };
      }

      if (action === 'apply') {
        if (!shader_name || !emulator) {
          return { success: false, error: 'shader_name and emulator are required for apply' };
        }
        const resp = await fetch(`${fastapiUrl}/api/launchbox/shaders/apply`, {
          method: 'POST',
          headers: {
            'Content-Type': 'application/json',
            'x-scope': 'config',
            'x-panel': clientContext.panel || 'launchbox',
            'x-device-id': clientContext.deviceId || 'unknown'
          },
          body: JSON.stringify({ game_id, shader_name, emulator, parameters })
        });
        const body = await resp.json().catch(() => ({}));
        if (!resp.ok) throw new Error(body?.error || `Backend error: ${resp.status}`);
        return {
          status: 'applied',
          game_id,
          emulator,
          shader_name,
          success: Boolean(body?.success),
          backup_path: body?.backup_path,
          config_path: body?.config_path,
          data: body
        };
      }

      if (action === 'remove') {
        const qs = new URLSearchParams();
        if (emulator) qs.append('emulator', emulator);
        const url = `${fastapiUrl}/api/launchbox/shaders/game/${encodeURIComponent(game_id)}${qs.toString() ? `?${qs.toString()}` : ''}`;
        const resp = await fetch(url, {
          method: 'DELETE',
          headers: {
            'x-scope': 'config',
            'x-panel': clientContext.panel || 'launchbox',
            'x-device-id': clientContext.deviceId || 'unknown'
          }
        });
        const body = await resp.json().catch(() => ({}));
        if (!resp.ok) throw new Error(body?.error || `Backend error: ${resp.status}`);
        return {
          status: 'removed',
          game_id,
          emulator,
          removed_count: body?.removed_count ?? (body?.status === 'removed' ? 1 : 0),
          success: Boolean(body?.success ?? body?.status === 'removed'),
          backup_path: body?.backup_path,
          data: body
        };
      }

      return { success: false, error: `Unknown action: ${action}` };
    } catch (error) {
      return { success: false, error: error.message };
    }
  },

  /**
   * Get the current game displayed on the marquee
   * Used for "what game is this?" queries
   */
  async get_marquee_game() {
    try {
      // Get current preview/marquee state
      const previewResp = await fetch(`${fastapiUrl}/api/local/marquee/preview`, {
        method: 'GET',
        headers: {
          'x-panel': clientContext.panel || 'launchbox',
          'x-device-id': clientContext.deviceId || 'unknown'
        }
      });

      const previewData = await previewResp.json().catch(() => ({}));

      if (!previewData.title || !previewData.game_id) {
        return {
          success: false,
          error: 'No game currently on marquee',
          message: 'There is no game currently displayed on the marquee. Browse to a game first!'
        };
      }

      // Get full game details from LaunchBox
      const gameResp = await fetch(`${fastapiUrl}/api/launchbox/game/${encodeURIComponent(previewData.game_id)}`, {
        method: 'GET',
        headers: {
          'x-panel': clientContext.panel || 'launchbox',
          'x-device-id': clientContext.deviceId || 'unknown'
        }
      });

      let gameDetails = previewData;
      if (gameResp.ok) {
        const fullGame = await gameResp.json().catch(() => null);
        if (fullGame) {
          gameDetails = { ...previewData, ...fullGame };
        }
      }

      return {
        success: true,
        game: {
          id: gameDetails.game_id || gameDetails.id,
          title: gameDetails.title,
          platform: gameDetails.platform,
          year: gameDetails.year || gameDetails.release_year,
          genre: gameDetails.genre,
          developer: gameDetails.developer,
          publisher: gameDetails.publisher,
          description: gameDetails.description || gameDetails.notes,
          players: gameDetails.players || gameDetails.max_players
        }
      };
    } catch (error) {
      return { success: false, error: error.message };
    }
  },

  /**
   * Find games similar to the current marquee game or a specified game
   */
  async find_similar_games({ game_id, limit = 5 } = {}) {
    try {
      let targetGameId = game_id;
      let targetGame = null;

      // If no game_id provided, get current marquee game
      if (!targetGameId) {
        const marqueeResult = await this.get_marquee_game();
        if (!marqueeResult.success || !marqueeResult.game?.id) {
          return {
            success: false,
            error: 'No game specified and no game on marquee',
            message: 'Please specify a game or browse to one first!'
          };
        }
        targetGameId = marqueeResult.game.id;
        targetGame = marqueeResult.game;
      }

      // Get target game details if we don't have them
      if (!targetGame) {
        const gameResp = await fetch(`${fastapiUrl}/api/launchbox/game/${encodeURIComponent(targetGameId)}`, {
          method: 'GET',
          headers: {
            'x-panel': clientContext.panel || 'launchbox',
            'x-device-id': clientContext.deviceId || 'unknown'
          }
        });
        if (gameResp.ok) {
          targetGame = await gameResp.json().catch(() => null);
        }
      }

      if (!targetGame) {
        return { success: false, error: 'Could not find game details' };
      }

      // Find similar games by genre and platform
      const searchParams = new URLSearchParams();
      if (targetGame.genre) searchParams.append('genre', targetGame.genre);
      if (targetGame.platform) searchParams.append('platform', targetGame.platform);
      searchParams.append('limit', String(limit + 1)); // +1 to exclude the target game

      const similarResp = await fetch(`${fastapiUrl}/api/launchbox/games?${searchParams.toString()}`, {
        method: 'GET',
        headers: {
          'x-panel': clientContext.panel || 'launchbox',
          'x-device-id': clientContext.deviceId || 'unknown'
        }
      });

      if (!similarResp.ok) {
        return { success: false, error: 'Failed to search for similar games' };
      }

      const similarData = await similarResp.json().catch(() => ({ games: [] }));
      const games = (similarData.games || similarData || [])
        .filter(g => g.id !== targetGameId) // Exclude the target game
        .slice(0, limit);

      return {
        success: true,
        based_on: {
          id: targetGameId,
          title: targetGame.title,
          genre: targetGame.genre,
          platform: targetGame.platform
        },
        similar_games: games.map(g => ({
          id: g.id,
          title: g.title,
          platform: g.platform,
          year: g.year || g.release_year,
          genre: g.genre
        })),
        count: games.length
      };
    } catch (error) {
      return { success: false, error: error.message };
    }
  }
};

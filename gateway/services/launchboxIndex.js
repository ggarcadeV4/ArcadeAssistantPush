/**
 * launchboxIndex.js — LaunchBox XML Index Service
 *
 * Parses ALL platform XMLs from LaunchBox/Data/Platforms/ at startup.
 * Builds an in-memory Map for O(1) game lookups by normalized title.
 * Resolves image paths deterministically using the canonical <Title> field.
 *
 * Two-layer architecture:
 *   Layer 1: XML → identity, metadata, MissingImage flags
 *   Layer 2: Filesystem → actual media files
 */

import fs from 'fs';
import path from 'path';
import { fileURLToPath } from 'url';

const __filename = fileURLToPath(import.meta.url);
const __dirname = path.dirname(__filename);

// ── Configuration ──────────────────────────────────────────────────────────
const LAUNCHBOX_ROOT = path.join(
  process.env.AA_DRIVE_ROOT || 'W:\\Arcade Assistant Master Build',
  'LaunchBox'
);
const APP_ROOT = path.resolve(__dirname, '..', '..');
const PLATFORMS_DIR = path.join(LAUNCHBOX_ROOT, 'Data', 'Platforms');
const IMAGES_ROOT = path.join(LAUNCHBOX_ROOT, 'Images');
const VIDEOS_ROOT = path.join(LAUNCHBOX_ROOT, 'Videos');
const DEWEY_IMAGE_INDEX_PATH = path.join(APP_ROOT, 'backend', 'data', 'dewey_image_index.json');
const LIBRARY_ROOTS = [
  'Dewey Images Artwork for Arcade Assistant General Questions/',
  'LaunchBox/Images/',
];

// Image types to resolve, in priority order
const IMAGE_TYPES = [
  { folder: 'Box - Front',              label: 'Box Art',   missingFlag: 'missingBoxFront' },
  { folder: 'Arcade - Cabinet',         label: 'Cabinet',   missingFlag: null },
  { folder: 'Arcade - Control Panel',   label: 'Control Panel', missingFlag: null },
  { folder: 'Arcade - Controls Information', label: 'Controls Information', missingFlag: null },
  { folder: 'Clear Logo',               label: 'Logo',      missingFlag: 'missingClearLogo' },
  { folder: 'Arcade - Marquee',         label: 'Marquee',   missingFlag: 'missingMarquee' },
  { folder: 'Advertisement Flyer - Front', label: 'Advertisement Flyer', missingFlag: null },
  { folder: 'Banner',                   label: 'Banner',    missingFlag: 'missingBanner' },
  { folder: 'Screenshot - Gameplay',    label: 'Screenshot', missingFlag: 'missingScreenshot' },
  { folder: 'Screenshot - Game Title',  label: 'Title Screen', missingFlag: null },
  { folder: 'Fanart - Background',      label: 'Fanart',    missingFlag: 'missingBackground' },
];

// File suffixes to try when constructing image paths
const IMAGE_SUFFIXES = ['-01.png', '-02.png', '-01.jpg', '-02.jpg', '.png', '.jpg'];
const VIDEO_SUFFIXES = ['-01.mp4', '-02.mp4', '.mp4', '-01.webm', '.webm', '-01.mkv', '.mkv', '-01.avi', '.avi'];
const VISUAL_INTENT_RE = /\b(show me|show a|can i see|picture|pictures|image|images|photo|photos|look like|what does .* look like|what does it look like|video|gameplay|footage|clip|trailer|screen recording|how it plays|how does it play)\b/i;
const TITLE_SCREEN_RE = /\b(title screen|attract screen|start screen)\b/i;
const CABINET_RE = /\b(cabinet|machine|upright|cocktail cabinet|physical machine)\b/i;
const MARQUEE_RE = /\b(marquee|signage|top signage|top sign)\b/i;
const CONTROLS_RE = /\b(controls information|controls|control panel|buttons|joystick|how to play)\b/i;
const BOX_ART_RE = /\b(box art|cover art|cover)\b/i;
const LOGO_RE = /\b(clear logo|logo|title logo)\b/i;
const FANART_RE = /\b(fan art|fanart|atmosphere|background)\b/i;
const FLYER_RE = /\b(flyer|advertisement|promo art|promotional art)\b/i;

// ── Index Storage ──────────────────────────────────────────────────────────
// Primary index: normalizedTitle → GameRecord
const gameIndex = new Map();
const deweyImageIndex = new Map();
const titleCandidates = new Map();
const platformTitleIndex = new Map();
const platformHintIndex = new Map();
// Platform list for logging
const platformStats = [];
let indexReady = false;

// ── Normalization ──────────────────────────────────────────────────────────

/**
 * Normalize a game title for index lookup.
 * Strips punctuation, collapses whitespace, lowercases.
 * "Pac-Man" and "Pac Man" and "pac man" all → "pac man"
 */
function normalizeKey(title) {
  return (title || '')
    .toLowerCase()
    .replace(/[^a-z0-9\s]/g, '')   // strip all punctuation
    .replace(/\s+/g, ' ')          // collapse whitespace
    .trim();
}

function getPlatformPriority(platform = '') {
  const normalized = platform.toLowerCase().trim();
  if (normalized === 'arcade mame') return 400;
  if (normalized.startsWith('arcade')) return 300;
  if (normalized === 'daphne') return 250;
  if (normalized.includes('mame')) return 200;
  return 100;
}

function shouldReplaceIndexedGame(existingGame, candidateGame) {
  if (!existingGame) return true;
  return getPlatformPriority(candidateGame?.platform) > getPlatformPriority(existingGame?.platform);
}

function normalizePathSlashes(value = '') {
  return String(value || '').replace(/\\/g, '/');
}

function stripLibraryRoot(relativePath = '') {
  const normalized = normalizePathSlashes(relativePath);
  for (const root of LIBRARY_ROOTS) {
    if (normalized.startsWith(root)) {
      return normalized.slice(root.length);
    }
  }
  return normalized;
}

function buildIndexedImageUrl(relativePath = '') {
  const stripped = stripLibraryRoot(relativePath);
  if (!stripped) return '';

  const segments = stripped
    .split('/')
    .filter(Boolean)
    .map(encodeURIComponent)
    .join('/');

  return segments ? `/api/launchbox/image/${segments}` : '';
}

function normalizeMediaBaseName(value = '') {
  const stem = String(value || '').replace(/\.[^.]+$/, '');
  const withoutIndex = stem.replace(/([._-]|\s)\d{1,3}$/i, '');
  const withoutUuid = withoutIndex.replace(/\.[0-9a-f-]{8,}$/i, '');
  return normalizeKey(withoutUuid);
}

function platformLooselyMatches(indexPlatform = '', gamePlatform = '') {
  const indexValue = normalizeKey(indexPlatform);
  const gameValue = normalizeKey(gamePlatform);
  if (!indexValue || !gameValue) return false;
  return indexValue === gameValue || gameValue.includes(indexValue) || indexValue.includes(gameValue);
}

function appendTitleCandidate(titleKey, game) {
  if (!titleKey || !game) return;
  const existing = titleCandidates.get(titleKey) || [];
  const duplicate = existing.some(entry =>
    normalizeKey(entry.title) === normalizeKey(game.title) &&
    normalizeKey(entry.platform) === normalizeKey(game.platform)
  );
  if (!duplicate) {
    existing.push(game);
    titleCandidates.set(titleKey, existing);
  }
}

function registerPlatformTitle(platform = '', titleKey = '', game) {
  const platformKey = normalizeKey(platform);
  if (!platformKey || !titleKey || !game) return;
  const titles = platformTitleIndex.get(platformKey) || new Map();
  if (!titles.has(titleKey)) {
    titles.set(titleKey, game);
  }
  platformTitleIndex.set(platformKey, titles);
}

const PLATFORM_HINT_ALIASES = {
  'arcade mame': ['arcade', 'mame', 'arcade mame'],
  'atari 2600': ['atari 2600', '2600', 'atari vcs'],
  'atari 7800': ['atari 7800', '7800'],
  'colecovision': ['colecovision', 'coleco vision'],
  'nintendo entertainment system': ['nes', 'nintendo entertainment system'],
  'nintendo game boy': ['game boy', 'gameboy', 'gb'],
  'nintendo game boy color': ['game boy color', 'gameboy color', 'gbc'],
  'nintendo game boy advance': ['game boy advance', 'gameboy advance', 'gba'],
  'nintendo 64': ['nintendo 64', 'n64'],
  'sega genesis': ['sega genesis', 'genesis', 'mega drive'],
  'sony playstation': ['playstation', 'ps1', 'psx'],
  'sony playstation 2': ['playstation 2', 'ps2'],
  'sony playstation 3': ['playstation 3', 'ps3'],
};

const QUERY_PLATFORM_PREFERENCES = [
  { patterns: ['arcade mame', 'mame', 'arcade'], platforms: ['Arcade MAME', 'Arcade'] },
  { patterns: ['atari 2600', '2600', 'atari vcs'], platforms: ['Atari 2600'] },
  { patterns: ['atari 7800', '7800'], platforms: ['Atari 7800'] },
  { patterns: ['colecovision', 'coleco vision'], platforms: ['ColecoVision'] },
  { patterns: ['nes', 'nintendo entertainment system'], platforms: ['Nintendo Entertainment System'] },
  { patterns: ['game boy color', 'gameboy color', 'gbc'], platforms: ['Nintendo Game Boy Color'] },
  { patterns: ['game boy advance', 'gameboy advance', 'gba'], platforms: ['Nintendo Game Boy Advance'] },
  { patterns: ['game boy', 'gameboy', 'gb'], platforms: ['Nintendo Game Boy'] },
  { patterns: ['nintendo 64', 'n64'], platforms: ['Nintendo 64'] },
  { patterns: ['sega genesis', 'genesis', 'mega drive'], platforms: ['Sega Genesis'] },
  { patterns: ['playstation 3', 'ps3'], platforms: ['Sony Playstation 3'] },
  { patterns: ['playstation 2', 'ps2'], platforms: ['Sony Playstation 2'] },
  { patterns: ['playstation', 'ps1', 'psx'], platforms: ['Sony Playstation'] },
];

function getPlatformHints(platform = '') {
  const normalized = normalizeKey(platform);
  if (!normalized) return [];

  const hints = new Set([normalized]);
  if (normalized.includes('arcade')) hints.add('arcade');
  if (normalized.includes('mame')) hints.add('mame');
  if (normalized.includes('atari')) hints.add('atari');
  if (normalized.includes('nintendo')) hints.add('nintendo');
  if (normalized.includes('sega')) hints.add('sega');
  if (normalized.includes('playstation')) hints.add('playstation');

  const aliases = PLATFORM_HINT_ALIASES[normalized] || [];
  for (const alias of aliases) hints.add(alias);

  return Array.from(hints).map(normalizeKey).filter(Boolean);
}

function registerPlatformHints(platform = '') {
  const platformKey = normalizeKey(platform);
  if (!platformKey) return;

  for (const hint of getPlatformHints(platform)) {
    const bucket = platformHintIndex.get(hint) || new Set();
    bucket.add(platform);
    platformHintIndex.set(hint, bucket);
  }
}

function scorePlatformHints(platform = '', query = '') {
  const normalizedQuery = normalizeKey(query);
  if (!normalizedQuery) return 0;

  let score = 0;
  for (const hint of getPlatformHints(platform)) {
    if (!hint) continue;
    const exactRe = new RegExp(`(?:^|\\b)${hint.replace(/[.*+?^${}()|[\]\\]/g, '\\$&')}(?:\\b|$)`);
    if (exactRe.test(normalizedQuery)) {
      score = Math.max(score, hint.split(' ').length > 1 ? 500 : 300);
    }
  }
  return score;
}

function selectBestGameCandidate(candidates = [], query = '') {
  if (!candidates.length) return null;
  if (candidates.length === 1) return candidates[0];

  const scored = candidates.map(game => ({
    game,
    score: scorePlatformHints(game.platform, query) + getPlatformPriority(game.platform),
  }));

  scored.sort((a, b) => b.score - a.score);
  return scored[0]?.game || candidates[0];
}

function detectPreferredPlatform(query = '') {
  const normalizedQuery = normalizeKey(query);
  if (!normalizedQuery) return '';

  const matches = [];
  for (const [hint, platforms] of platformHintIndex.entries()) {
    if (!hint) continue;
    const exactRe = new RegExp(`(?:^|\\b)${hint.replace(/[.*+?^${}()|[\]\\]/g, '\\$&')}(?:\\b|$)`);
    if (!exactRe.test(normalizedQuery)) continue;

    for (const platform of platforms) {
      matches.push({
        platform,
        hint,
        score: hint.split(' ').length * 100 + getPlatformPriority(platform),
      });
    }
  }

  matches.sort((a, b) => b.score - a.score);
  return matches[0]?.platform || '';
}

export function getPreferredPlatformsFromQuery(query = '') {
  const normalizedQuery = normalizeKey(query);
  if (!normalizedQuery) return [];

  const preferred = [];
  for (const entry of QUERY_PLATFORM_PREFERENCES) {
    const matched = entry.patterns.some(pattern => {
      const normalizedPattern = normalizeKey(pattern);
      const re = new RegExp(`(?:^|\\b)${normalizedPattern.replace(/[.*+?^${}()|[\]\\]/g, '\\$&')}(?:\\b|$)`);
      return re.test(normalizedQuery);
    });
    if (!matched) continue;

    for (const platform of entry.platforms) {
      if (!preferred.includes(platform)) preferred.push(platform);
    }
  }

  return preferred;
}

function loadDeweyImageIndex() {
  if (!fs.existsSync(DEWEY_IMAGE_INDEX_PATH)) {
    console.warn(`[LaunchBox Index] Dewey image index not found: ${DEWEY_IMAGE_INDEX_PATH}`);
    return;
  }

  try {
    const entries = JSON.parse(fs.readFileSync(DEWEY_IMAGE_INDEX_PATH, 'utf-8'));
    for (const entry of entries) {
      const titleKey = normalizeKey(entry?.game_title);
      if (!titleKey || !entry?.image_type || !entry?.relative_path) continue;

      const bucketKey = `${titleKey}::${entry.image_type}`;
      const bucket = deweyImageIndex.get(bucketKey) || [];
      bucket.push(entry);
      deweyImageIndex.set(bucketKey, bucket);
    }
    console.log(`[LaunchBox Index] Dewey image index ready - ${entries.length.toLocaleString()} entries loaded`);
  } catch (err) {
    console.warn(`[LaunchBox Index] Failed to load Dewey image index: ${err.message}`);
  }
}

// ── Lightweight XML Parser ─────────────────────────────────────────────────
// We use regex-based extraction instead of a full XML parser to keep
// startup fast and avoid adding dependencies for simple tag extraction.

/**
 * Extract text content between <Tag>...</Tag>.
 * Returns empty string if tag is self-closing or missing.
 */
function extractTag(xml, tag) {
  const openTag = `<${tag}>`;
  const closeTag = `</${tag}>`;
  const start = xml.indexOf(openTag);
  if (start === -1) return '';
  const contentStart = start + openTag.length;
  const end = xml.indexOf(closeTag, contentStart);
  if (end === -1) return '';
  return xml.substring(contentStart, end).trim();
}

/**
 * Extract boolean flag (returns true if tag content is "true").
 */
function extractBool(xml, tag) {
  return extractTag(xml, tag).toLowerCase() === 'true';
}

/**
 * Parse a single <Game>...</Game> block into a GameRecord.
 */
function parseGameBlock(block) {
  const title = extractTag(block, 'Title');
  if (!title) return null;

  return {
    title,
    platform: extractTag(block, 'Platform'),
    developer: extractTag(block, 'Developer'),
    publisher: extractTag(block, 'Publisher'),
    genre: extractTag(block, 'Genre'),
    releaseDate: extractTag(block, 'ReleaseDate'),
    notes: extractTag(block, 'Notes'),
    videoUrl: extractTag(block, 'VideoUrl'),
    series: extractTag(block, 'Series'),
    maxPlayers: extractTag(block, 'MaxPlayers'),
    playMode: extractTag(block, 'PlayMode'),
    region: extractTag(block, 'Region'),
    databaseId: extractTag(block, 'DatabaseID'),
    // MissingImage flags — pre-flight skip indicators
    missingBoxFront: extractBool(block, 'MissingBoxFrontImage'),
    missingScreenshot: extractBool(block, 'MissingScreenshotImage'),
    missingMarquee: extractBool(block, 'MissingMarqueeImage'),
    missingClearLogo: extractBool(block, 'MissingClearLogoImage'),
    missingBackground: extractBool(block, 'MissingBackgroundImage'),
    missingBanner: extractBool(block, 'MissingBannerImage'),
    missingVideo: extractBool(block, 'MissingVideo'),
  };
}

/**
 * Parse a platform XML file. Splits on <Game> blocks and extracts each.
 * Returns array of GameRecords.
 */
function parsePlatformXml(filePath) {
  let content;
  try {
    content = fs.readFileSync(filePath, 'utf-8');
  } catch (err) {
    console.warn(`[LaunchBox Index] Failed to read ${filePath}: ${err.message}`);
    return [];
  }

  const games = [];
  const gameOpenTag = '<Game>';
  const gameCloseTag = '</Game>';
  let cursor = 0;

  while (true) {
    const start = content.indexOf(gameOpenTag, cursor);
    if (start === -1) break;
    const end = content.indexOf(gameCloseTag, start);
    if (end === -1) break;

    const block = content.substring(start, end + gameCloseTag.length);
    const record = parseGameBlock(block);
    if (record) {
      games.push(record);
    }
    cursor = end + gameCloseTag.length;
  }

  return games;
}

// ── Index Initialization ───────────────────────────────────────────────────

/**
 * Initialize the LaunchBox index by parsing ALL platform XMLs.
 * Call this once at gateway startup.
 */
export function initIndex() {
  const startTime = Date.now();
  loadDeweyImageIndex();
  console.log('[LaunchBox Index] Initializing — scanning all platform XMLs...');

  if (!fs.existsSync(PLATFORMS_DIR)) {
    console.warn(`[LaunchBox Index] Platforms directory not found: ${PLATFORMS_DIR}`);
    indexReady = true;
    return;
  }

  let xmlFiles;
  try {
    xmlFiles = fs.readdirSync(PLATFORMS_DIR)
      .filter(f => f.endsWith('.xml'))
      .sort();
  } catch (err) {
    console.warn(`[LaunchBox Index] Failed to read platforms directory: ${err.message}`);
    indexReady = true;
    return;
  }

  let totalGames = 0;
  let totalDuplicatesSkipped = 0;

  for (const xmlFile of xmlFiles) {
    const filePath = path.join(PLATFORMS_DIR, xmlFile);
    const games = parsePlatformXml(filePath);
    const platformName = xmlFile.replace('.xml', '');
    let platformCount = 0;

    for (const game of games) {
      if (!game.platform) {
        game.platform = platformName;
      }
      registerPlatformHints(game.platform);

      // Index under normalized key
      const normKey = normalizeKey(game.title);
      if (!normKey) continue;
      appendTitleCandidate(normKey, game);
      registerPlatformTitle(game.platform, normKey, game);

      // Also index under raw lowercase title (for exact match attempts)
      const rawKey = game.title.toLowerCase().trim();

      // Prefer arcade records when the same title exists across multiple platforms.
      if (!gameIndex.has(normKey)) {
        gameIndex.set(normKey, game);
        platformCount++;
      } else if (shouldReplaceIndexedGame(gameIndex.get(normKey), game)) {
        gameIndex.set(normKey, game);
      } else {
        totalDuplicatesSkipped++;
      }

      // Also add raw key as alias if different, using the same platform preference.
      if (rawKey !== normKey) {
        if (!gameIndex.has(rawKey) || shouldReplaceIndexedGame(gameIndex.get(rawKey), game)) {
          gameIndex.set(rawKey, game);
        }
      }
    }

    if (platformCount > 0) {
      platformStats.push({ platform: platformName, count: platformCount });
    }
    totalGames += platformCount;
  }

  const elapsed = Date.now() - startTime;
  indexReady = true;

  console.log(`[LaunchBox Index] ✅ Ready — ${totalGames.toLocaleString()} games indexed from ${xmlFiles.length} platforms in ${elapsed}ms`);
  if (totalDuplicatesSkipped > 0) {
    console.log(`[LaunchBox Index]    (${totalDuplicatesSkipped.toLocaleString()} duplicate/clone entries skipped)`);
  }

  // Log top platforms
  const topPlatforms = platformStats
    .sort((a, b) => b.count - a.count)
    .slice(0, 10);
  for (const { platform, count } of topPlatforms) {
    console.log(`[LaunchBox Index]    ${platform}: ${count.toLocaleString()} games`);
  }

  // Build sorted title list for subject extraction
  buildSortedTitles();
}

// ── Game Lookup ────────────────────────────────────────────────────────────

/**
 * Look up a game by title. Tries normalized key first, then raw lowercase.
 * Returns GameRecord or null.
 */
export function lookupGame(query) {
  if (!indexReady || !query) return null;

  const normKey = normalizeKey(query);
  if (titleCandidates.has(normKey)) {
    return selectBestGameCandidate(titleCandidates.get(normKey), query);
  }
  if (gameIndex.has(normKey)) return gameIndex.get(normKey);

  // Try raw lowercase
  const rawKey = (query || '').toLowerCase().trim();
  if (gameIndex.has(rawKey)) return gameIndex.get(rawKey);

  return null;
}

// ── Subject Extraction (Intent Parser) ─────────────────────────────────────
// Sorted title list for substring matching (longest first to avoid partial hits)
let sortedTitles = []; // populated after initIndex

/**
 * Build the sorted titles list from the index.
 * Called at end of initIndex(). Longest titles first so "Street Fighter II"
 * matches before "Street Fighter".
 */
function buildSortedTitles() {
  const seen = new Set();
  sortedTitles = [];
  for (const [key, game] of gameIndex) {
    const norm = normalizeKey(game.title);
    if (norm.length >= 3 && !seen.has(norm)) {
      seen.add(norm);
      // Pre-compile word-boundary regex for fast matching at query time.
      // normalizeKey output only contains [a-z0-9 ], so \b works correctly.
      const escaped = norm.replace(/[.*+?^${}()|[\]\\]/g, '\\$&');
      const re = new RegExp(`(?:^|\\b)${escaped}(?:\\b|$)`);
      sortedTitles.push({ norm, title: game.title, re });
    }
  }
  // Sort by length descending — longest match wins
  sortedTitles.sort((a, b) => b.norm.length - a.norm.length);
  console.log(`[LaunchBox Index] Subject extraction ready — ${sortedTitles.length} unique titles indexed`);
}

/**
 * Extract a game subject from freeform user text.
 * Scans the user's message against the entire game index.
 * Returns the best-matching GameRecord or null.
 *
 * Uses word-boundary matching to avoid false positives where a short
 * game title appears as a substring of an unrelated word
 * (e.g. "tron" inside "electronic").
 *
 * Example: "show me what Pac-Man looks like" → GameRecord for Pac-Man
 * Example: "tell me about Street Fighter II" → GameRecord for Street Fighter II
 */
export function extractSubject(text) {
  if (!indexReady || !text) return null;

  const norm = normalizeKey(text);
  if (!norm) return null;
  const preferredPlatform = detectPreferredPlatform(text);

  // Strategy 1: Exact index hit (user typed just a game title)
  const exact = lookupGame(text);
  if (exact) return exact;

  // Strategy 2: Word-boundary scan — find the longest game title present in the text.
  // Uses pre-compiled regex from buildSortedTitles() for performance.
  // Sorted longest-first so "Street Fighter II" matches before "Street Fighter".
  for (const entry of sortedTitles) {
    if (entry.re.test(norm)) {
      if (preferredPlatform) {
        const preferredTitles = platformTitleIndex.get(normalizeKey(preferredPlatform));
        const preferredGame = preferredTitles?.get(entry.norm);
        if (preferredGame) {
          console.log(`[LaunchBox Index] extractSubject matched preferred platform: "${entry.norm}" -> "${preferredGame.title}" (${preferredGame.platform})`);
          return preferredGame;
        }
      }

      const candidates = titleCandidates.get(entry.norm) || [];
      const game = selectBestGameCandidate(candidates, text) || gameIndex.get(entry.norm);
      if (game) {
        console.log(`[LaunchBox Index] extractSubject matched: "${entry.norm}" → "${game.title}" (${game.platform})`);
        return game;
      }
    }
  }

  return null;
}

// ── Media Resolution ───────────────────────────────────────────────────────

/**
 * Build a LaunchBox image URL for the static server.
 * The gateway serves images at /api/launchbox/image/{platform}/{imageType}/{filename}
 */
function buildImageUrl(platform, imageType, filename) {
  const segments = [platform, imageType, filename].map(encodeURIComponent).join('/');
  return `/api/launchbox/image/${segments}`;
}

function buildVideoUrl(platform, filename) {
  const segments = [platform, filename].map(encodeURIComponent).join('/');
  return `/api/launchbox/video/${segments}`;
}

/**
 * Try to find an image file for a given game title and image type folder.
 * Checks deterministic paths ({Title}-01.png, etc.) first,
 * then falls back to a directory scan if needed.
 *
 * Also checks region subdirs (North America/, World/, etc.)
 */
function findImageFile(platform, imageTypeFolder, title) {
  const typeDir = path.join(IMAGES_ROOT, platform, imageTypeFolder);

  // Search locations: top-level dir + any region subdirectories
  const searchDirs = [typeDir];
  try {
    if (fs.existsSync(typeDir)) {
      const entries = fs.readdirSync(typeDir, { withFileTypes: true });
      for (const entry of entries) {
        if (entry.isDirectory()) {
          searchDirs.push(path.join(typeDir, entry.name));
        }
      }
    }
  } catch {
    // ignore — directory may not exist
  }

  for (const dir of searchDirs) {
    if (!fs.existsSync(dir)) continue;

    // Strategy 1: Deterministic path — try known suffixes
    for (const suffix of IMAGE_SUFFIXES) {
      const candidate = path.join(dir, `${title}${suffix}`);
      if (fs.existsSync(candidate)) {
        const subPath = dir === typeDir ? null : path.basename(dir);
        const filename = `${title}${suffix}`;
        return subPath
          ? buildImageUrl(platform, imageTypeFolder, `${subPath}/${filename}`)
          : buildImageUrl(platform, imageTypeFolder, filename);
      }
    }

    // Strategy 2: Directory scan fallback — find any file starting with the title
    try {
      const files = fs.readdirSync(dir);
      const titleLower = title.toLowerCase();
      const match = files.find(f => {
        const stem = f.replace(/\.[^.]+$/, '').toLowerCase();
        // Match: exact title, or title followed by separator (-01, .uuid, etc.)
        return stem === titleLower || stem.startsWith(titleLower + '-') || stem.startsWith(titleLower + '.');
      });
      if (match) {
        const subPath = dir === typeDir ? null : path.basename(dir);
        return subPath
          ? buildImageUrl(platform, imageTypeFolder, `${subPath}/${match}`)
          : buildImageUrl(platform, imageTypeFolder, match);
      }
    } catch {
      // ignore scan failures
    }
  }

  return null;
}

function findIndexedImages(game, imageTypeFolder) {
  const titleKey = normalizeKey(game?.title);
  if (!titleKey || !imageTypeFolder) return [];

  const bucketKey = `${titleKey}::${imageTypeFolder}`;
  const matches = deweyImageIndex.get(bucketKey) || [];
  if (!matches.length) return [];

  const platformMatches = matches.filter(entry => platformLooselyMatches(entry.platform, game.platform));
  const candidates = platformMatches.length > 0 ? platformMatches : matches;

  return candidates
    .map(entry => ({
      ...entry,
      url: buildIndexedImageUrl(entry.relative_path),
    }))
    .filter(entry => entry.url);
}

function findVideoFile(platform, title) {
  const typeDir = path.join(VIDEOS_ROOT, platform);
  if (!fs.existsSync(typeDir)) return null;
  const normalizedTitle = normalizeKey(title);

  for (const suffix of VIDEO_SUFFIXES) {
    const candidate = path.join(typeDir, `${title}${suffix}`);
    if (fs.existsSync(candidate)) {
      return buildVideoUrl(platform, `${title}${suffix}`);
    }
  }

  try {
    const files = fs.readdirSync(typeDir);
    const titleLower = title.toLowerCase();
    const match = files.find(f => {
      const stem = f.replace(/\.[^.]+$/, '').toLowerCase();
      const normalizedStem = normalizeMediaBaseName(f);
      return (
        stem === titleLower ||
        stem.startsWith(titleLower + '-') ||
        stem.startsWith(titleLower + '.') ||
        normalizedStem === normalizedTitle
      );
    });
    return match ? buildVideoUrl(platform, match) : null;
  } catch {
    return null;
  }
}

function inferRequestedMedia(query = '') {
  const raw = String(query || '').toLowerCase();
  if (!raw) return null;
  if (TITLE_SCREEN_RE.test(raw)) return { kind: 'image', folder: 'Screenshot - Game Title' };
  if (CABINET_RE.test(raw)) return { kind: 'image', folder: 'Arcade - Cabinet' };
  if (MARQUEE_RE.test(raw)) return { kind: 'image', folder: 'Arcade - Marquee' };
  if (CONTROLS_RE.test(raw)) return { kind: 'image', folder: 'Arcade - Controls Information' };
  if (BOX_ART_RE.test(raw)) return { kind: 'image', folder: 'Box - Front' };
  if (LOGO_RE.test(raw)) return { kind: 'image', folder: 'Clear Logo' };
  if (FANART_RE.test(raw)) return { kind: 'image', folder: 'Fanart - Background' };
  if (FLYER_RE.test(raw)) return { kind: 'image', folder: 'Advertisement Flyer - Front' };
  if (VISUAL_INTENT_RE.test(raw)) return { kind: 'video' };
  return null;
}

/**
 * Resolve all available media for a GameRecord.
 * Returns array of { url, type, source } objects.
 */
export function resolveGameMedia(game) {
  if (!game || !game.platform || !game.title) return [];

  const results = [];

  for (const imageType of IMAGE_TYPES) {
    const indexedImages = findIndexedImages(game, imageType.folder);
    if (indexedImages.length > 0) {
      for (const entry of indexedImages) {
        results.push({
          url: entry.url,
          thumbnail: entry.url,
          source: 'local',
          type: imageType.label,
          folder: imageType.folder,
          platform: entry.platform || game.platform,
          kind: 'image',
        });
      }
      continue;
    }

    // Pre-flight skip: if XML says the image is missing, don't bother looking
    if (imageType.missingFlag && game[imageType.missingFlag]) continue;

    const url = findImageFile(game.platform, imageType.folder, game.title);
    if (url) {
      results.push({
        url,
        thumbnail: url,
        source: 'local',
        type: imageType.label,
        folder: imageType.folder,
        platform: game.platform,
        kind: 'image',
      });
    }
  }

  return results;
}

export function resolveGameVideo(game) {
  if (!game || !game.platform || !game.title || game.missingVideo) return null;

  const url = findVideoFile(game.platform, game.title);
  if (!url) return null;

  return {
    url,
    thumbnail: '',
    source: 'local',
    type: 'Gameplay Video',
    folder: 'LaunchBox Video Snap',
    platform: game.platform,
    kind: 'video',
  };
}

export function resolvePreferredMedia(game, query = '') {
  const preferredPlatforms = getPreferredPlatformsFromQuery(query);
  let resolvedGame = game;
  for (const platform of preferredPlatforms) {
    const preferredTitles = platformTitleIndex.get(normalizeKey(platform));
    const preferredGame = preferredTitles?.get(normalizeKey(game?.title));
    if (preferredGame) {
      resolvedGame = preferredGame;
      break;
    }
  }

  const images = resolveGameMedia(resolvedGame);
  let video = resolveGameVideo(resolvedGame);
  let matchedPreferredVideo = preferredPlatforms.length === 0;
  if (preferredPlatforms.length > 0) {
    for (const platform of preferredPlatforms) {
      const preferredVideoUrl = findVideoFile(platform, resolvedGame?.title || game?.title);
      if (preferredVideoUrl) {
        video = {
          url: preferredVideoUrl,
          thumbnail: '',
          source: 'local',
          type: 'Gameplay Video',
          folder: 'LaunchBox Video Snap',
          platform,
          kind: 'video',
        };
        matchedPreferredVideo = true;
        break;
      }
    }
    if (!matchedPreferredVideo) {
      video = null;
    }
  }
  const requested = inferRequestedMedia(query);

  const preferredPoster =
    images.find(asset =>
      asset.folder === 'Screenshot - Gameplay' &&
      (preferredPlatforms.length === 0 || preferredPlatforms.some(platform => platformLooselyMatches(asset.platform, platform)))
    ) ||
    images.find(asset => asset.folder === 'Screenshot - Gameplay') ||
    images.find(asset => asset.folder === 'Screenshot - Game Title') ||
    images.find(asset => asset.folder === 'Box - Front') ||
    images[0] ||
    null;

  if (requested?.kind === 'image' && requested.folder) {
    const image = images.find(asset => asset.folder === requested.folder) || images[0] || null;
    return { resolvedGame, primaryMedia: image, images, video };
  }

  if (requested?.kind === 'video' && video) {
    return {
      resolvedGame,
      primaryMedia: {
        ...video,
        thumbnail: preferredPoster?.url || '',
        poster: preferredPoster?.url || '',
      },
      images,
      video,
    };
  }

  return {
    resolvedGame,
    primaryMedia:
      (preferredPlatforms.length > 0 && !video && preferredPoster) ?
        preferredPoster :
        (images[0] || (video ? { ...video, thumbnail: preferredPoster?.url || '', poster: preferredPoster?.url || '' } : null)),
    images,
    video,
  };
}

/**
 * Get index stats for health checks.
 */
export function getIndexStats() {
  return {
    ready: indexReady,
    totalEntries: gameIndex.size,
    platforms: platformStats,
  };
}

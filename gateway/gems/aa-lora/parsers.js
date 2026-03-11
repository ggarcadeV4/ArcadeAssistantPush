/**
 * Parsers Module - Text normalization and game request parsing
 * Part of: aa-lora gem (Gem-Agent Refactor)
 *
 * Extracted from launchboxAI.js lines 139-237
 *
 * REDLINES: API contract maintained via createResponse() in index.js
 */

/**
 * Basic string normalization - trim whitespace
 * @param {string} str
 * @returns {string}
 */
export function normalize(str) {
    return (str || '').toString().trim();
}

/**
 * Normalize title for fuzzy matching
 * Removes punctuation, lowercase, single spaces
 * @param {string} str
 * @returns {string}
 */
export function normalizeTitleForMatch(str) {
    return normalize(str)
        .toLowerCase()
        .replace(/['']/g, '')
        .replace(/[^a-z0-9]+/g, ' ')
        .replace(/\s+/g, ' ')
        .trim();
}

/**
 * Platform alias map: short form -> full LaunchBox platform name
 * Moved to module level for performance (created once at load, not per call)
 */
export const PLATFORM_ALIASES = {
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
    'ps3': 'Sony Playstation 3',
    'ps 3': 'Sony Playstation 3',
    'playstation 3': 'Sony Playstation 3',
    'sony playstation 3': 'Sony Playstation 3',
    'rpcs3': 'Sony Playstation 3',
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
    'teknoparrot': 'TeknoParrot',
    'tekno parrot': 'TeknoParrot',
    'daphne': 'Daphne',
    'hypseus': 'Daphne',
    'laserdisc': 'Daphne',
    'laser disc': 'Daphne',
    'american laser games': 'American Laser Games',
    'alg': 'American Laser Games',
};

// Pre-sorted by length (longest first) for correct matching priority
export const SORTED_PLATFORM_ALIASES = Object.keys(PLATFORM_ALIASES).sort((a, b) => b.length - a.length);

/**
 * Parse a game request string to extract title, platform, and year hints
 * @param {string} str - Raw user input (e.g., "Galaga arcade 1981")
 * @returns {{ title: string, platform: string|null, year: number|null }}
 */
export function parseRequestedGame(str) {
    const raw = normalize(str);
    const lower = raw.toLowerCase();

    let platform = null;
    let platformMatch = null;

    // Check for platform aliases (prefer longer matches first)
    for (const alias of SORTED_PLATFORM_ALIASES) {
        // Match as word boundary (at start, end, or surrounded by spaces)
        const pattern = new RegExp(`(^|\\s)${alias.replace(/[.*+?^${}()|[\\]\\]/g, '\\$&')}(\\s|$)`, 'i');
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
        const platformPattern = new RegExp(`(^|\\s)${platformMatch.replace(/[.*+?^${}()|[\\]\\]/g, '\\$&')}(\\s+version)?\\s*`, 'gi');
        title = title.replace(platformPattern, ' ');
    }

    title = title
        .replace(/\s+(?:arcade|mame)\s+(?:version|edition)\s*$/i, ' ')
        .replace(/\s+(?:version|edition|release)\s*$/i, ' ')
        .replace(/\s+for\s+me\s*$/i, ' ')
        .replace(/\s+version\s*$/i, ' ')
        .replace(/\s+/g, ' ')
        .trim();

    return { title, platform, year };
}

/**
 * Format candidates list for display
 * @param {Array} candidates - Array of game candidates
 * @param {number} limit - Max items to show
 * @returns {string}
 */
export function stringifyCandidates(candidates, limit = 5) {
    const items = Array.isArray(candidates) ? candidates.slice(0, limit) : [];
    return items
        .map((g, idx) => {
            const year = g.year ? `, ${g.year}` : '';
            const platform = g.platform ? ` - ${g.platform}` : '';
            return `${idx + 1}) ${g.title || 'Unknown'}${year}${platform}`;
        })
        .join('\n');
}

/**
 * Format candidate list with overflow message
 * @param {Array} candidates
 * @param {number} limit
 * @returns {string}
 */
export function formatCandidateList(candidates, limit = 5) {
    const total = Array.isArray(candidates) ? candidates.length : 0;
    const preview = stringifyCandidates(candidates, limit);
    if (total > limit) {
        return `${preview}\nShowing ${limit} of ${total} matches. Refine your request (e.g., "the arcade version") to narrow results.`;
    }
    return preview;
}

export default {
    normalize,
    normalizeTitleForMatch,
    parseRequestedGame,
    stringifyCandidates,
    formatCandidateList,
    PLATFORM_ALIASES,
    SORTED_PLATFORM_ALIASES
};

/**
 * Genre Profile Service for aa-blinky Gem
 * Part of: Phase 5 Blinky Gem Pivot
 * 
 * Ports the genre profile matching logic from backend/services/genre_profile_service.py
 * Reads config/mappings/genre_profiles.json for LED color schemes
 */

import fs from 'fs';
import path from 'path';
import { requireDriveRoot } from '../../utils/driveDetection.js';

// ============================================================================
// CONFIGURATION
// ============================================================================

const PROFILES_FILENAME = 'genre_profiles.json';

/** @type {object|null} */
let _cachedProfiles = null;
let _cacheLoadTime = 0;
const CACHE_TTL_MS = 60000;  // 1 minute cache

// ============================================================================
// PROFILE LOADING
// ============================================================================

/**
 * Get path to genre_profiles.json
 * @returns {string}
 */
function getProfilesPath() {
    const driveRoot = requireDriveRoot();
    return path.join(driveRoot, 'Arcade Assistant Local', 'config', 'mappings', PROFILES_FILENAME);
}

/**
 * Load genre profiles from JSON file
 * @param {boolean} forceReload - Force reload from disk
 * @returns {object|null} Profiles data
 */
function loadProfiles(forceReload = false) {
    const now = Date.now();

    // Return cached if valid
    if (_cachedProfiles && !forceReload && (now - _cacheLoadTime < CACHE_TTL_MS)) {
        return _cachedProfiles;
    }

    const profilesPath = getProfilesPath();

    try {
        if (!fs.existsSync(profilesPath)) {
            console.error(`[aa-blinky] Genre profiles not found at ${profilesPath}`);
            return null;
        }

        const content = fs.readFileSync(profilesPath, 'utf-8');
        _cachedProfiles = JSON.parse(content);
        _cacheLoadTime = now;

        console.log(`[aa-blinky] Loaded ${Object.keys(_cachedProfiles.profiles || {}).length} genre profiles`);
        return _cachedProfiles;

    } catch (e) {
        console.error('[aa-blinky] Failed to load genre profiles:', e.message);
        return null;
    }
}

/**
 * Force reload profiles from disk
 */
function reloadProfiles() {
    _cachedProfiles = null;
    _cacheLoadTime = 0;
    return loadProfiles(true);
}

// ============================================================================
// PROFILE MATCHING
// ============================================================================

/**
 * List all available profiles
 * @returns {object[]} Array of profile summaries
 */
function listProfiles() {
    const data = loadProfiles();
    if (!data?.profiles) return [];

    return Object.entries(data.profiles).map(([key, profile]) => ({
        key,
        name: profile.name || key,
        description: profile.description || '',
        icon: profile.icon || '🕹️',
        genres: profile.applies_to_genres || []
    }));
}

/**
 * Get a specific profile by key
 * @param {string} profileKey - Profile key (e.g., "fighting", "racing")
 * @returns {object|null} Profile object
 */
function getProfile(profileKey) {
    const data = loadProfiles();
    return data?.profiles?.[profileKey] || null;
}

/**
 * Find the matching profile for a genre name
 * @param {string} genre - Genre name from LaunchBox
 * @returns {[string|null, object|null]} [profileKey, profile] or [null, null]
 */
function getProfileForGenre(genre) {
    const data = loadProfiles();
    if (!data) return [null, null];

    const genreLower = (genre || '').toLowerCase().trim();

    // Check genre_aliases first
    if (data.genre_aliases) {
        for (const [alias, profileKey] of Object.entries(data.genre_aliases)) {
            if (alias.toLowerCase() === genreLower) {
                const profile = data.profiles?.[profileKey];
                if (profile) return [profileKey, profile];
            }
        }
    }

    // Check applies_to_genres in each profile
    for (const [key, profile] of Object.entries(data.profiles || {})) {
        const genres = profile.applies_to_genres || [];
        for (const g of genres) {
            if (g === '*') continue;  // Skip wildcard
            if (g.toLowerCase() === genreLower) {
                return [key, profile];
            }
        }
    }

    // Check for partial matches
    for (const [key, profile] of Object.entries(data.profiles || {})) {
        const genres = profile.applies_to_genres || [];
        for (const g of genres) {
            if (g === '*') continue;
            if (genreLower.includes(g.toLowerCase()) || g.toLowerCase().includes(genreLower)) {
                return [key, profile];
            }
        }
    }

    // Fall back to default profile
    if (data.profiles?.default) {
        return ['default', data.profiles.default];
    }

    return [null, null];
}

/**
 * Get LED profile for a genre
 * @param {string} genre - Genre name
 * @returns {object|null} LED profile mapping {button_id: {color, label}}
 */
function getLEDProfileForGenre(genre) {
    const [, profile] = getProfileForGenre(genre);
    return profile?.led_profile || null;
}

/**
 * Get button layout for a profile
 * @param {string} profileKey - Profile key
 * @returns {object|null} Button layout mapping
 */
function getButtonLayout(profileKey) {
    const profile = getProfile(profileKey);
    return profile?.button_layout || null;
}

/**
 * Get emulator-specific mappings
 * @param {string} profileKey - Profile key
 * @param {string} emulator - Emulator name (mame, teknoparrot, pcsx2, retroarch)
 * @returns {object|null} Emulator mapping
 */
function getEmulatorMapping(profileKey, emulator) {
    const profile = getProfile(profileKey);
    return profile?.emulator_mappings?.[emulator.toLowerCase()] || null;
}

/**
 * Convert LED profile colors to 32-channel brightness array
 * Uses a button-to-port mapping to translate button IDs to LED-Wiz ports
 * 
 * @param {object} ledProfile - LED profile from genre_profiles.json
 * @param {object} buttonToPort - Mapping of button IDs to port numbers
 * @returns {number[]} 32-element array of brightness values (0-48)
 */
function ledProfileToFrame(ledProfile, buttonToPort = {}) {
    const frame = new Array(32).fill(0);

    if (!ledProfile) return frame;

    for (const [buttonId, config] of Object.entries(ledProfile)) {
        const port = buttonToPort[buttonId];
        if (port === undefined || port < 1 || port > 32) continue;

        // Convert color to brightness (simple approach: use max RGB component)
        let brightness = 48;  // Default full brightness

        if (config.color) {
            // Parse hex color like "#FF0000"
            const hex = config.color.replace('#', '');
            if (hex.length === 6) {
                const r = parseInt(hex.substring(0, 2), 16);
                const g = parseInt(hex.substring(2, 4), 16);
                const b = parseInt(hex.substring(4, 6), 16);
                // Map 0-255 to 0-48
                brightness = Math.round(Math.max(r, g, b) / 255 * 48);
            }
        }

        frame[port - 1] = brightness;
    }

    return frame;
}

// ============================================================================
// EXPORTS
// ============================================================================

export {
    loadProfiles,
    reloadProfiles,
    listProfiles,
    getProfile,
    getProfileForGenre,
    getLEDProfileForGenre,
    getButtonLayout,
    getEmulatorMapping,
    ledProfileToFrame,
    getProfilesPath
};

export default {
    loadProfiles,
    reloadProfiles,
    listProfiles,
    getProfile,
    getProfileForGenre,
    getLEDProfileForGenre,
    getButtonLayout,
    getEmulatorMapping,
    ledProfileToFrame,
    getProfilesPath
};

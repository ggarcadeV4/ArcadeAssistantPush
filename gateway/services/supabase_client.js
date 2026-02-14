/**
 * Supabase Client for Gateway (Node.js)
 * Arcade Assistant - Cloud Integration Layer
 */

import { createClient } from '@supabase/supabase-js';

let supabaseClient = null;
let lastHeartbeat = {};

/**
 * Initialize Supabase client (singleton pattern)
 * @returns {import('@supabase/supabase-js').SupabaseClient | null}
 */
function getClient() {
  if (supabaseClient) {
    return supabaseClient;
  }

  const supabaseUrl = process.env.SUPABASE_URL;
  const supabaseKey = process.env.SUPABASE_ANON_KEY;

  if (!supabaseUrl || !supabaseKey) {
    console.warn('Supabase not configured (missing SUPABASE_URL or SUPABASE_ANON_KEY)');
    return null;
  }

  try {
    supabaseClient = createClient(supabaseUrl, supabaseKey, {
      auth: {
        persistSession: false,
        autoRefreshToken: false
      }
    });

    console.log('Supabase client initialized successfully');
    return supabaseClient;
  } catch (error) {
    console.error('Error initializing Supabase client:', error);
    return null;
  }
}

/**
 * Test Supabase connectivity
 * @returns {Promise<boolean>}
 */
async function healthCheck() {
  const client = getClient();
  if (!client) {
    return false;
  }

  try {
    const { data, error } = await client
      .from('cabinet')
      .select('id')
      .limit(1);

    if (error) {
      console.error('Supabase health check failed:', error);
      return false;
    }

    return true;
  } catch (error) {
    console.error('Supabase health check error:', error);
    return false;
  }
}

/**
 * Update device heartbeat (rate-limited to 5 min intervals)
 * @param {string} deviceId - Device UUID
 * @returns {Promise<boolean>}
 */
async function updateHeartbeat(deviceId) {
  const client = getClient();
  if (!client || !deviceId) {
    return false;
  }

  // Rate limiting: only update every 5 minutes
  const now = Date.now();
  const lastUpdate = lastHeartbeat[deviceId] || 0;
  const fiveMinutes = 5 * 60 * 1000;

  if (now - lastUpdate < fiveMinutes) {
    return true; // Skip update, too soon
  }

  try {
    const { error } = await client
      .from('cabinet')
      .update({
        last_seen: new Date().toISOString(),
        status: 'online'
      })
      .eq('id', deviceId);

    if (error) {
      console.error('Error updating heartbeat:', error);
      return false;
    }

    lastHeartbeat[deviceId] = now;
    return true;
  } catch (error) {
    console.error('Heartbeat update error:', error);
    return false;
  }
}

/**
 * Send telemetry log to Supabase
 * @param {string} deviceId - Device UUID
 * @param {string} level - Log level (INFO | WARN | ERROR)
 * @param {string} code - Event code
 * @param {string} message - Log message
 * @param {object} [payload] - Optional additional metadata (model, tokens, latency, etc.)
 * @param {string} [panel] - Panel name (launchbox, controller, led, etc.)
 * @returns {Promise<boolean>}
 */
async function sendTelemetry(deviceId, level, code, message, payload = null, panel = 'system') {
  const client = getClient();
  if (!client || !deviceId) {
    return false;
  }

  try {
    const insertData = {
      cabinet_id: deviceId,
      level: level || 'INFO',
      message: message || '',
      panel: panel,
      occurred_at: new Date().toISOString(),
      payload: {
        code: code || 'UNKNOWN',
        ...(payload || {})
      }
    };

    const { error } = await client
      .from('cabinet_telemetry')
      .insert(insertData);

    if (error) {
      console.error('Error sending telemetry:', error);
      return false;
    }

    return true;
  } catch (error) {
    console.error('Telemetry send error:', error);
    return false;
  }
}


/**
 * Fetch new commands for device
 * @param {string} deviceId - Device UUID
 * @returns {Promise<Array<any> | null>}
 */
async function fetchNewCommands(deviceId) {
  const client = getClient();
  if (!client || !deviceId) {
    return null;
  }

  try {
    const { data, error } = await client
      .from('command_queue')
      .select('*')
      .eq('cabinet_id', deviceId)
      .eq('status', 'pending')
      .order('created_at', { ascending: true });

    if (error) {
      console.error('Error fetching commands:', error);
      return null;
    }

    return data || [];
  } catch (error) {
    console.error('Fetch commands error:', error);
    return null;
  }
}

/**
 * Update command status after execution
 * @param {string} commandId - Command UUID
 * @param {string} status - Status (RUNNING | DONE | ERROR)
 * @param {object} [result] - Execution result
 * @returns {Promise<boolean>}
 */
async function updateCommandStatus(commandId, status, result = null) {
  const client = getClient();
  if (!client || !commandId) {
    return false;
  }

  try {
    const updateData = {
      status,
      executed_at: new Date().toISOString()
    };

    if (result !== null) {
      updateData.result = result;
    }

    const { error } = await client
      .from('command_queue')
      .update(updateData)
      .eq('id', commandId);

    if (error) {
      console.error('Error updating command status:', error);
      return false;
    }

    return true;
  } catch (error) {
    console.error('Command status update error:', error);
    return false;
  }
}

/**
 * Insert tournament score
 * @param {string} deviceId - Device UUID
 * @param {string} gameId - Game identifier
 * @param {string} player - Player name
 * @param {number} score - Score value
 * @param {object} [meta] - Additional metadata
 * @returns {Promise<boolean>}
 */
async function insertScore(deviceId, gameId, player, score, meta = null) {
  const client = getClient();
  if (!client || !deviceId || !gameId || !player) {
    return false;
  }

  try {
    const { error } = await client
      .from('cabinet_game_score')
      .insert({
        cabinet_id: deviceId,
        game_id: gameId,
        player,
        score: parseInt(score, 10),
        meta: meta || {},
        created_at: new Date().toISOString()
      });

    if (error) {
      console.error('Error inserting score:', error);
      return false;
    }

    return true;
  } catch (error) {
    console.error('Score insert error:', error);
    return false;
  }
}

/**
 * Get user tendencies (preferences, favorites, etc.)
 * @param {string} deviceId - Device UUID
 * @param {string} userId - User identifier (guest, dad, mom, etc.)
 * @returns {Promise<object | null>}
 */
async function getUserTendencies(deviceId, userId) {
  const client = getClient();
  if (!client || !deviceId || !userId) {
    return null;
  }

  try {
    const { data, error } = await client
      .from('user_tendencies')
      .select('*')
      .eq('device_id', deviceId)
      .eq('user_id', userId)
      .maybeSingle();

    if (error) {
      console.error('Error fetching user tendencies:', error);
      return null;
    }

    return data;
  } catch (error) {
    console.error('Get user tendencies error:', error);
    return null;
  }
}

/**
 * Save/update user tendencies
 * @param {string} deviceId - Device UUID
 * @param {string} userId - User identifier
 * @param {object} tendencies - User preferences and data
 * @returns {Promise<boolean>}
 */
async function saveUserTendencies(deviceId, userId, tendencies) {
  const client = getClient();
  if (!client || !deviceId || !userId) {
    return false;
  }

  try {
    const { error } = await client
      .from('user_tendencies')
      .upsert({
        device_id: deviceId,
        user_id: userId,
        preferences: tendencies.preferences || {},
        play_history: tendencies.play_history || [],
        favorites: tendencies.favorites || [],
        updated_at: new Date().toISOString()
      }, {
        onConflict: 'device_id,user_id'
      });

    if (error) {
      console.error('Error saving user tendencies:', error);
      return false;
    }

    return true;
  } catch (error) {
    console.error('Save user tendencies error:', error);
    return false;
  }
}

export {
  getClient,
  healthCheck,
  updateHeartbeat,
  sendTelemetry,
  fetchNewCommands,
  updateCommandStatus,
  insertScore,
  getUserTendencies,
  saveUserTendencies
};

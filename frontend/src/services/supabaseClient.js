import { createClient } from '@supabase/supabase-js';

const supabaseUrl = import.meta.env.VITE_SUPABASE_URL;
const supabaseAnonKey = import.meta.env.VITE_SUPABASE_ANON_KEY;

if (!supabaseUrl || !supabaseAnonKey) {
    console.warn('[Supabase] Missing VITE_SUPABASE_URL or VITE_SUPABASE_ANON_KEY. Chat history will not be saved.');
}

export const supabase = (supabaseUrl && supabaseAnonKey)
    ? createClient(supabaseUrl, supabaseAnonKey)
    : null;

/**
 * Logs a chat message to the Supabase 'chat_history' table.
 * @param {Object} params
 * @param {string} params.panel_id - The ID of the panel (e.g., 'controller-chuck')
 * @param {string} params.role - 'user' or 'assistant'
 * @param {string} params.content - The message content
 * @param {Object} [params.metadata] - Optional metadata
 * @param {string} [params.session_id] - Optional session ID to group conversations
 */
export const logChatHistory = async ({ panel_id, role, content, metadata = {}, session_id }) => {
    if (!supabase) return;

    try {
        const { error } = await supabase
            .from('chat_history')
            .insert([
                {
                    panel_id,
                    role,
                    content,
                    metadata,
                    session_id: session_id || undefined // Let DB generate default if null
                }
            ]);

        if (error) {
            console.error('[Supabase] Failed to log chat history:', error);
        }
    } catch (err) {
        console.error('[Supabase] Error logging chat history:', err);
    }
};

/**
 * Subscribe to realtime inserts on the Supabase 'scores' table.
 * Returns the channel so the caller can unsubscribe on cleanup.
 *
 * @param {(payload: object) => void} onInsert - callback fired with the new row
 * @returns {object|null} Supabase RealtimeChannel (call .unsubscribe() to stop)
 */
export const subscribeToScores = (onInsert) => {
    if (!supabase) {
        console.warn('[Supabase] No client — skipping realtime scores subscription');
        return null;
    }

    const channel = supabase
        .channel('public:scores')
        .on(
            'postgres_changes',
            { event: 'INSERT', schema: 'public', table: 'scores' },
            (payload) => {
                console.log('[Supabase] Realtime score insert:', payload.new);
                if (typeof onInsert === 'function') onInsert(payload.new);
            }
        )
        .subscribe((status) => {
            console.log('[Supabase] Realtime scores channel status:', status);
        });

    return channel;
};

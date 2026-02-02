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

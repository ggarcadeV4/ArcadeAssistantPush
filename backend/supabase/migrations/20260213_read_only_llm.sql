-- Create the read_only_llm schema
CREATE SCHEMA IF NOT EXISTS read_only_llm;

-- Grant usage to public/anon (so they can access the schema)
GRANT USAGE ON SCHEMA read_only_llm TO anon;
GRANT USAGE ON SCHEMA read_only_llm TO authenticated;
GRANT USAGE ON SCHEMA read_only_llm TO service_role;

-- Create views for critical tables (selecting non-sensitive columns)
-- Assumption: pinouts table exists in public
CREATE OR REPLACE VIEW read_only_llm.open_pinouts AS
SELECT
    id,
    game_id,
    pin_name,
    pin_function,
    voltage,
    connector_type,
    notes
FROM public.pinouts;

-- Assumption: game_metadata table exists in public
CREATE OR REPLACE VIEW read_only_llm.open_metadata AS
SELECT
    id,
    title,
    manufacturer,
    year,
    genre,
    description
FROM public.game_metadata;

-- Grant SELECT permissions on the views to anon
GRANT SELECT ON read_only_llm.open_pinouts TO anon;
GRANT SELECT ON read_only_llm.open_metadata TO anon;

-- Note: RLS is enforced on the underlying tables in 'public'.
-- Since we are creating views in a new schema, we rely on the view permissions.
-- However, for better security, we ensure the views are owned by a role that has access,
-- and we grant SELECT explicitly.

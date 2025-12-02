-- Simple RPC function for charter operators using existing gtj.operators table
-- This wraps your existing data with pagination and search support

CREATE OR REPLACE FUNCTION public.get_charter_operators(
    p_skip INT DEFAULT 0,
    p_limit INT DEFAULT NULL,
    p_search TEXT DEFAULT NULL
)
RETURNS JSON
LANGUAGE plpgsql
SECURITY DEFINER
AS $$
DECLARE
    result JSON;
    total_count INT;
    query_limit INT;
BEGIN
    -- If no limit specified, use a very high number to get all records
    query_limit := COALESCE(p_limit, 999999);

    -- Get total count (with optional search filter)
    IF p_search IS NOT NULL AND p_search != '' THEN
        SELECT COUNT(*) INTO total_count
        FROM gtj.operators
        WHERE name ILIKE '%' || p_search || '%'
           OR certificate_number ILIKE '%' || p_search || '%';
    ELSE
        SELECT COUNT(*) INTO total_count FROM gtj.operators;
    END IF;

    -- Get data with optional pagination
    SELECT json_build_object(
        'total', total_count,
        'data', COALESCE(json_agg(row_to_json(t)), '[]'::json)
    ) INTO result
    FROM (
        SELECT
            operator_id as charter_operator_id,
            name as company,
            COALESCE(CASE
                WHEN base_airport IS NOT NULL THEN jsonb_build_array(base_airport)
                ELSE '[]'::jsonb
            END, '[]'::jsonb) as locations,
            website as url,
            certificate_number as part135_cert,
            COALESCE(trust_score::INT, 0) as score,
            NULL as faa_data,
            jsonb_build_object(
                'name', name,
                'certifications', jsonb_build_object(
                    'aoc_part135', aoc_part135,
                    'argus_rating', argus_rating,
                    'wyvern_certified', wyvern_rating,
                    'is_bao', is_bao,
                    'acsf_ias', acsf_ias
                ),
                'contact', jsonb_build_object(
                    'telephone', telephone,
                    'email', email,
                    'website', website
                )
            ) as data,
            created_at,
            created_at as updated_at
        FROM gtj.operators
        WHERE (p_search IS NULL OR p_search = ''
            OR name ILIKE '%' || p_search || '%'
            OR certificate_number ILIKE '%' || p_search || '%')
        ORDER BY trust_score DESC NULLS LAST, name
        LIMIT query_limit
        OFFSET p_skip
    ) t;

    RETURN result;
END;
$$;

-- Grant permissions
GRANT EXECUTE ON FUNCTION public.get_charter_operators(INT, INT, TEXT) TO anon, authenticated;

COMMENT ON FUNCTION public.get_charter_operators IS 'Get charter operators from gtj.operators with pagination and search';

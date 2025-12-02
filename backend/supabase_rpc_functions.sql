-- RPC Functions to access gtj.operators table from Supabase REST API
-- Run these in your Supabase SQL Editor

-- 1. Get all charter operators with pagination and search
CREATE OR REPLACE FUNCTION public.get_charter_operators(
    p_skip INT DEFAULT 0,
    p_limit INT DEFAULT 100,
    p_search TEXT DEFAULT NULL
)
RETURNS JSON
LANGUAGE plpgsql
SECURITY DEFINER
AS $$
DECLARE
    result JSON;
    total_count INT;
BEGIN
    -- Get total count
    IF p_search IS NOT NULL THEN
        SELECT COUNT(*) INTO total_count
        FROM gtj.operators
        WHERE name ILIKE '%' || p_search || '%'
           OR certificate_number ILIKE '%' || p_search || '%';
    ELSE
        SELECT COUNT(*) INTO total_count FROM gtj.operators;
    END IF;

    -- Get data with pagination
    SELECT json_build_object(
        'total', total_count,
        'data', json_agg(row_to_json(t))
    ) INTO result
    FROM (
        SELECT
            operator_id as charter_operator_id,
            name as company,
            to_jsonb(ARRAY[COALESCE(faa_city || ', ' || faa_state, base_airport, 'Unknown')]) as locations,
            website as url,
            certificate_number as part135_cert,
            faa_state,
            COALESCE(trust_score::INT, 0) as score,
            json_build_object(
                'faa_operator_name', faa_operator_name,
                'faa_dsgn_code', faa_dsgn_code,
                'faa_ceo', faa_ceo,
                'faa_city', faa_city,
                'faa_state', faa_state,
                'faa_pic_captains', faa_pic_captains
            ) as faa_data,
            json_build_object(
                'certifications', json_build_object(
                    'aoc_part135', aoc_part135,
                    'argus_rating', argus_rating,
                    'wyvern_rating', wyvern_rating,
                    'is_bao', is_bao,
                    'acsf_ias', acsf_ias
                ),
                'contact', json_build_object(
                    'telephone', telephone,
                    'email', email,
                    'website', website
                )
            ) as data,
            created_at,
            CURRENT_TIMESTAMP as updated_at
        FROM gtj.operators
        WHERE (p_search IS NULL
            OR name ILIKE '%' || p_search || '%'
            OR certificate_number ILIKE '%' || p_search || '%')
        ORDER BY trust_score DESC NULLS LAST, name
        LIMIT p_limit
        OFFSET p_skip
    ) t;

    RETURN result;
END;
$$;

-- 2. Get single charter operator by ID
CREATE OR REPLACE FUNCTION public.get_charter_operator(p_operator_id UUID)
RETURNS JSON
LANGUAGE plpgsql
SECURITY DEFINER
AS $$
DECLARE
    result JSON;
BEGIN
    SELECT row_to_json(t) INTO result
    FROM (
        SELECT
            operator_id as charter_operator_id,
            name as company,
            to_jsonb(ARRAY[COALESCE(faa_city || ', ' || faa_state, base_airport, 'Unknown')]) as locations,
            website as url,
            certificate_number as part135_cert,
            faa_state,
            COALESCE(trust_score::INT, 0) as score,
            json_build_object(
                'faa_operator_name', faa_operator_name,
                'faa_dsgn_code', faa_dsgn_code,
                'faa_ceo', faa_ceo,
                'faa_city', faa_city,
                'faa_state', faa_state,
                'faa_pic_captains', faa_pic_captains
            ) as faa_data,
            json_build_object(
                'certifications', json_build_object(
                    'aoc_part135', aoc_part135,
                    'argus_rating', argus_rating,
                    'wyvern_rating', wyvern_rating,
                    'is_bao', is_bao,
                    'acsf_ias', acsf_ias
                ),
                'contact', json_build_object(
                    'telephone', telephone,
                    'email', email,
                    'website', website
                )
            ) as data,
            created_at,
            CURRENT_TIMESTAMP as updated_at
        FROM gtj.operators
        WHERE operator_id = p_operator_id
    ) t;

    RETURN result;
END;
$$;

-- 3. Create charter operator
CREATE OR REPLACE FUNCTION public.create_charter_operator(
    p_company TEXT,
    p_locations JSONB DEFAULT '[]'::jsonb,
    p_url TEXT DEFAULT NULL,
    p_part135_cert TEXT DEFAULT NULL,
    p_score INT DEFAULT 0,
    p_faa_data JSONB DEFAULT NULL,
    p_data JSONB DEFAULT NULL
)
RETURNS JSON
LANGUAGE plpgsql
SECURITY DEFINER
AS $$
DECLARE
    result JSON;
    new_id UUID;
BEGIN
    INSERT INTO gtj.operators (
        name,
        locations,
        url,
        certificate_number,
        trust_score,
        faa_data,
        data,
        regulatory_status
    ) VALUES (
        p_company,
        p_locations,
        p_url,
        p_part135_cert,
        p_score,
        p_faa_data,
        p_data,
        'COMPLIANT'
    )
    RETURNING operator_id INTO new_id;

    -- Return the created operator
    SELECT row_to_json(t) INTO result
    FROM (
        SELECT
            operator_id as charter_operator_id,
            name as company,
            locations,
            url,
            certificate_number as part135_cert,
            trust_score::INT as score,
            faa_data,
            data,
            created_at,
            CURRENT_TIMESTAMP as updated_at
        FROM gtj.operators
        WHERE operator_id = new_id
    ) t;

    RETURN result;
END;
$$;

-- 4. Filter charter operators by certification and score
CREATE OR REPLACE FUNCTION public.filter_charter_operators(
    p_cert_type TEXT DEFAULT NULL,
    p_min_score INT DEFAULT NULL
)
RETURNS JSON
LANGUAGE plpgsql
SECURITY DEFINER
AS $$
DECLARE
    result JSON;
    total_count INT;
BEGIN
    -- Build dynamic query based on filters
    WITH filtered_ops AS (
        SELECT *
        FROM gtj.operators
        WHERE (p_min_score IS NULL OR trust_score >= p_min_score)
          AND (p_cert_type IS NULL OR (
              (p_cert_type ILIKE '%argus%' AND data->'certifications'->>'argus_rating' IS NOT NULL)
              OR (p_cert_type ILIKE '%wyvern%' AND data->'certifications'->>'wyvern_certified' IS NOT NULL)
              OR (p_cert_type ILIKE '%is-bao%' AND data->'certifications'->>'is_bao' IS NOT NULL)
          ))
    )
    SELECT
        json_build_object(
            'total', COUNT(*),
            'data', json_agg(row_to_json(t))
        ) INTO result
    FROM (
        SELECT
            operator_id as charter_operator_id,
            name as company,
            COALESCE(locations, '[]'::jsonb) as locations,
            url,
            certificate_number as part135_cert,
            COALESCE(trust_score::INT, 0) as score,
            faa_data,
            data,
            created_at,
            CURRENT_TIMESTAMP as updated_at
        FROM filtered_ops
        ORDER BY trust_score DESC NULLS LAST, name
        LIMIT 500
    ) t;

    RETURN result;
END;
$$;

-- Grant execute permissions
GRANT EXECUTE ON FUNCTION public.get_charter_operators(INT, INT, TEXT) TO anon, authenticated;
GRANT EXECUTE ON FUNCTION public.get_charter_operator(UUID) TO anon, authenticated;
GRANT EXECUTE ON FUNCTION public.create_charter_operator(TEXT, JSONB, TEXT, TEXT, INT, JSONB, JSONB) TO authenticated;
GRANT EXECUTE ON FUNCTION public.filter_charter_operators(TEXT, INT) TO anon, authenticated;

-- Add comments
COMMENT ON FUNCTION public.get_charter_operators IS 'Get charter operators from gtj schema with pagination and search';
COMMENT ON FUNCTION public.get_charter_operator IS 'Get a single charter operator by ID';
COMMENT ON FUNCTION public.create_charter_operator IS 'Create a new charter operator';
COMMENT ON FUNCTION public.filter_charter_operators IS 'Filter charter operators by certification type and minimum score';

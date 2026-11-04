-- Imports only an already provisioned exact session/CSRF pair; never mints authority.
BEGIN;
SET LOCAL ROLE pf_product_owner;
CREATE FUNCTION pf_product.browser_session(session_digest text, csrf_digest text)
RETURNS TABLE(workspace_id uuid, session_kind text, expires_at timestamptz)
LANGUAGE plpgsql SECURITY DEFINER SET search_path=pg_catalog,pg_temp AS $$
DECLARE w uuid; k text;
BEGIN
    SELECT s.workspace_id INTO w FROM pf_product.sessions s WHERE s.token_hash=session_digest;
    IF NOT FOUND THEN RAISE EXCEPTION 'ACCESS_DENIED'; END IF;
    k:=pf_product.authorize(w,session_digest,csrf_digest,true);
    RETURN QUERY SELECT w,k,s.expires_at FROM pf_product.sessions s WHERE s.token_hash=session_digest;
END;
$$;
REVOKE ALL ON FUNCTION pf_product.browser_session(text,text) FROM PUBLIC;
RESET ROLE;
GRANT EXECUTE ON FUNCTION pf_product.browser_session(text,text) TO pf_product_api;
COMMIT;

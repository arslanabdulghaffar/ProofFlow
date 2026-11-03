-- Product identity/assets only. No jobs, approvals, policy or verdicts.
-- Apply once in the separate product database as migration administrator.
-- No login/password is created; the HTTP role may execute named functions only.
BEGIN;
DO $$ BEGIN
    IF current_database() <> 'proofflow_product' THEN
        RAISE EXCEPTION 'WRONG_PRODUCT_DATABASE';
    END IF;
END $$;
REVOKE ALL ON DATABASE proofflow_product FROM PUBLIC;
REVOKE CREATE ON SCHEMA public FROM PUBLIC;
CREATE ROLE pf_product_owner NOLOGIN;
CREATE ROLE pf_product_api NOLOGIN;
CREATE ROLE pf_product_provisioner NOLOGIN;
CREATE SCHEMA pf_product AUTHORIZATION pf_product_owner;
REVOKE ALL ON SCHEMA pf_product FROM PUBLIC;

CREATE TABLE pf_product.workspaces (
    id uuid PRIMARY KEY,
    kind text NOT NULL CHECK (kind IN ('guest', 'operator')),
    created_at timestamptz NOT NULL DEFAULT clock_timestamp(),
    expires_at timestamptz NOT NULL,
    revoked_at timestamptz,
    CHECK (expires_at > created_at AND expires_at <= created_at + interval '24 hours')
);
CREATE TABLE pf_product.sessions (
    token_hash text PRIMARY KEY CHECK (token_hash ~ '^[0-9a-f]{64}$'),
    workspace_id uuid NOT NULL REFERENCES pf_product.workspaces(id),
    csrf_hash text NOT NULL CHECK (csrf_hash ~ '^[0-9a-f]{64}$' AND csrf_hash <> token_hash),
    created_at timestamptz NOT NULL DEFAULT clock_timestamp(),
    expires_at timestamptz NOT NULL,
    revoked_at timestamptz,
    CHECK (expires_at > created_at AND expires_at <= created_at + interval '12 hours')
);
CREATE INDEX sessions_workspace ON pf_product.sessions(workspace_id);
CREATE TABLE pf_product.assets (
    workspace_id uuid NOT NULL REFERENCES pf_product.workspaces(id),
    id uuid NOT NULL,
    kind text NOT NULL CHECK (kind IN ('pipeline', 'transactions', 'customers', 'contract')),
    sha256 text NOT NULL CHECK (sha256 ~ '^[0-9a-f]{64}$'),
    byte_size integer NOT NULL CHECK (byte_size > 0),
    created_at timestamptz NOT NULL DEFAULT clock_timestamp(),
    PRIMARY KEY (workspace_id, id),
    CHECK ((kind = 'pipeline' AND byte_size <= 16384)
        OR (kind = 'contract' AND byte_size <= 32768)
        OR (kind IN ('transactions', 'customers') AND byte_size <= 5242880))
);
COMMENT ON TABLE pf_product.assets IS
    'Immutable authorized registry, not parser/business validation. Register only after durable byte publication.';

CREATE FUNCTION pf_product.require_transaction() RETURNS void
LANGUAGE plpgsql SECURITY DEFINER SET search_path = pg_catalog, pg_temp AS $$
BEGIN
    IF current_setting('transaction_isolation') <> 'read committed'
       OR current_setting('synchronous_commit') <> 'on' THEN
        RAISE EXCEPTION 'PRODUCT_TRANSACTION_POLICY';
    END IF;
END;
$$;

CREATE FUNCTION pf_product.authorize(workspace uuid, session_digest text, csrf_digest text,
                                    writing boolean) RETURNS text
LANGUAGE plpgsql SECURITY DEFINER SET search_path = pg_catalog, pg_temp AS $$
DECLARE
    w pf_product.workspaces%ROWTYPE;
    s pf_product.sessions%ROWTYPE;
BEGIN
    PERFORM pf_product.require_transaction();
    IF writing IS NULL THEN RAISE EXCEPTION 'ACCESS_DENIED'; END IF;
    -- Workspace first, then session, everywhere. Writers serialize quotas and
    -- revoke with the same row lock; no stale cached authorization commits.
    IF writing THEN
        SELECT * INTO w FROM pf_product.workspaces WHERE id = workspace FOR UPDATE;
    ELSE
        SELECT * INTO w FROM pf_product.workspaces WHERE id = workspace FOR SHARE;
    END IF;
    IF NOT FOUND THEN RAISE EXCEPTION 'ACCESS_DENIED'; END IF;
    SELECT * INTO s FROM pf_product.sessions
        WHERE token_hash = session_digest AND workspace_id = workspace FOR SHARE;
    IF NOT FOUND THEN RAISE EXCEPTION 'ACCESS_DENIED'; END IF;
    IF w.revoked_at IS NOT NULL OR s.revoked_at IS NOT NULL
       OR w.expires_at <= clock_timestamp() OR s.expires_at <= clock_timestamp()
       OR (writing AND s.csrf_hash IS DISTINCT FROM csrf_digest) THEN
        RAISE EXCEPTION 'ACCESS_DENIED';
    END IF;
    RETURN w.kind;
END;
$$;

CREATE FUNCTION pf_product.create_workspace(workspace uuid, workspace_kind text,
                                           expiry timestamptz) RETURNS void
LANGUAGE plpgsql SECURITY DEFINER SET search_path = pg_catalog, pg_temp AS $$
BEGIN
    PERFORM pf_product.require_transaction();
    IF workspace IS NULL OR workspace_kind IS NULL OR workspace_kind NOT IN ('guest','operator')
       OR expiry IS NULL OR expiry <= clock_timestamp()
       OR expiry > clock_timestamp() + interval '24 hours' THEN
        RAISE EXCEPTION 'INVALID_WORKSPACE';
    END IF;
    -- Fixed small private development capacity. Includes expired/revoked rows
    -- until future retention/physical-deletion reconciliation exists.
    PERFORM pg_advisory_xact_lock(604061, 1);
    IF (SELECT count(*) FROM pf_product.workspaces) >= 8 THEN
        RAISE EXCEPTION 'WORKSPACE_CAPACITY';
    END IF;
    INSERT INTO pf_product.workspaces(id,kind,expires_at) VALUES(workspace,workspace_kind,expiry);
END;
$$;

CREATE FUNCTION pf_product.create_session(workspace uuid, session_digest text, csrf_digest text,
                                         expiry timestamptz) RETURNS void
LANGUAGE plpgsql SECURITY DEFINER SET search_path = pg_catalog, pg_temp AS $$
DECLARE w pf_product.workspaces%ROWTYPE;
BEGIN
    PERFORM pf_product.require_transaction();
    SELECT * INTO w FROM pf_product.workspaces WHERE id=workspace FOR UPDATE;
    IF NOT FOUND OR w.revoked_at IS NOT NULL OR w.expires_at <= clock_timestamp() THEN
        RAISE EXCEPTION 'ACCESS_DENIED';
    END IF;
    IF session_digest IS NULL OR session_digest !~ '^[0-9a-f]{64}$'
       OR csrf_digest IS NULL OR csrf_digest !~ '^[0-9a-f]{64}$' OR session_digest=csrf_digest
       OR expiry IS NULL OR expiry <= clock_timestamp() OR expiry > w.expires_at
       OR expiry > clock_timestamp() + (CASE WHEN w.kind='guest' THEN interval '1 hour'
                                            ELSE interval '12 hours' END) THEN
        RAISE EXCEPTION 'INVALID_SESSION';
    END IF;
    IF (SELECT count(*) FROM pf_product.sessions WHERE workspace_id=workspace) >= 32 THEN
        RAISE EXCEPTION 'SESSION_CAPACITY';
    END IF;
    INSERT INTO pf_product.sessions(token_hash,workspace_id,csrf_hash,expires_at)
        VALUES(session_digest,workspace,csrf_digest,expiry);
END;
$$;

CREATE FUNCTION pf_product.session_context(session_digest text)
RETURNS TABLE(workspace_id uuid, session_kind text, expires_at timestamptz)
LANGUAGE plpgsql SECURITY DEFINER SET search_path = pg_catalog, pg_temp AS $$
DECLARE w uuid; role_kind text;
BEGIN
    SELECT s.workspace_id INTO w FROM pf_product.sessions s WHERE s.token_hash=session_digest;
    IF NOT FOUND THEN RAISE EXCEPTION 'ACCESS_DENIED'; END IF;
    role_kind := pf_product.authorize(w,session_digest,NULL,false);
    RETURN QUERY SELECT w,role_kind,s.expires_at FROM pf_product.sessions s
        WHERE s.token_hash=session_digest;
END;
$$;

CREATE FUNCTION pf_product.register_asset(workspace uuid, session_digest text, csrf_digest text,
                                         asset_id uuid, asset_kind text, digest text,
                                         bytes integer) RETURNS boolean
LANGUAGE plpgsql SECURITY DEFINER SET search_path = pg_catalog, pg_temp AS $$
DECLARE existing pf_product.assets%ROWTYPE; total bigint; objects bigint;
BEGIN
    PERFORM pf_product.authorize(workspace,session_digest,csrf_digest,true);
    IF asset_id IS NULL OR asset_kind IS NULL
       OR asset_kind NOT IN ('pipeline','transactions','customers','contract')
       OR digest IS NULL OR digest !~ '^[0-9a-f]{64}$' OR bytes IS NULL OR bytes < 1
       OR bytes > (CASE asset_kind WHEN 'pipeline' THEN 16384 WHEN 'contract' THEN 32768
                                  ELSE 5242880 END) THEN
        RAISE EXCEPTION 'INVALID_ASSET';
    END IF;
    SELECT * INTO existing FROM pf_product.assets WHERE workspace_id=workspace AND id=asset_id;
    IF FOUND THEN
        IF existing.kind <> asset_kind OR existing.sha256 <> digest OR existing.byte_size <> bytes THEN
            RAISE EXCEPTION 'ASSET_IDEMPOTENCY_CONFLICT';
        END IF;
        RETURN false;
    END IF;
    SELECT count(*),COALESCE(sum(byte_size),0) INTO objects,total
        FROM pf_product.assets WHERE workspace_id=workspace;
    IF objects >= 64 OR total + bytes > 134217728 THEN RAISE EXCEPTION 'ASSET_QUOTA'; END IF;
    INSERT INTO pf_product.assets(workspace_id,id,kind,sha256,byte_size)
        VALUES(workspace,asset_id,asset_kind,digest,bytes);
    RETURN true;
END;
$$;

CREATE FUNCTION pf_product.get_asset(workspace uuid, session_digest text, asset_id uuid)
RETURNS TABLE(kind text, sha256 text, byte_size integer)
LANGUAGE plpgsql SECURITY DEFINER SET search_path = pg_catalog, pg_temp AS $$
BEGIN
    PERFORM pf_product.authorize(workspace,session_digest,NULL,false);
    RETURN QUERY SELECT a.kind,a.sha256,a.byte_size FROM pf_product.assets a
        WHERE a.workspace_id=workspace AND a.id=asset_id;
END;
$$;

CREATE FUNCTION pf_product.revoke_session(workspace uuid, session_digest text,
                                         csrf_digest text) RETURNS void
LANGUAGE plpgsql SECURITY DEFINER SET search_path = pg_catalog, pg_temp AS $$
BEGIN
    PERFORM pf_product.authorize(workspace,session_digest,csrf_digest,true);
    UPDATE pf_product.sessions SET revoked_at=clock_timestamp() WHERE token_hash=session_digest;
END;
$$;

CREATE FUNCTION pf_product.revoke_workspace(workspace uuid) RETURNS void
LANGUAGE plpgsql SECURITY DEFINER SET search_path = pg_catalog, pg_temp AS $$
BEGIN
    PERFORM pf_product.require_transaction();
    UPDATE pf_product.workspaces SET revoked_at=COALESCE(revoked_at,clock_timestamp())
        WHERE id=workspace;
END;
$$;

REVOKE ALL ON ALL TABLES IN SCHEMA pf_product FROM PUBLIC;
REVOKE ALL ON ALL FUNCTIONS IN SCHEMA pf_product FROM PUBLIC;
ALTER TABLE pf_product.workspaces OWNER TO pf_product_owner;
ALTER TABLE pf_product.sessions OWNER TO pf_product_owner;
ALTER TABLE pf_product.assets OWNER TO pf_product_owner;
ALTER FUNCTION pf_product.require_transaction() OWNER TO pf_product_owner;
ALTER FUNCTION pf_product.authorize(uuid,text,text,boolean) OWNER TO pf_product_owner;
ALTER FUNCTION pf_product.create_workspace(uuid,text,timestamptz) OWNER TO pf_product_owner;
ALTER FUNCTION pf_product.create_session(uuid,text,text,timestamptz) OWNER TO pf_product_owner;
ALTER FUNCTION pf_product.session_context(text) OWNER TO pf_product_owner;
ALTER FUNCTION pf_product.register_asset(uuid,text,text,uuid,text,text,integer)
    OWNER TO pf_product_owner;
ALTER FUNCTION pf_product.get_asset(uuid,text,uuid) OWNER TO pf_product_owner;
ALTER FUNCTION pf_product.revoke_session(uuid,text,text) OWNER TO pf_product_owner;
ALTER FUNCTION pf_product.revoke_workspace(uuid) OWNER TO pf_product_owner;
ALTER DEFAULT PRIVILEGES FOR ROLE pf_product_owner IN SCHEMA pf_product
    REVOKE EXECUTE ON FUNCTIONS FROM PUBLIC;
GRANT USAGE ON SCHEMA pf_product TO pf_product_api,pf_product_provisioner;
GRANT CONNECT ON DATABASE proofflow_product TO pf_product_api,pf_product_provisioner;
GRANT EXECUTE ON FUNCTION pf_product.create_workspace(uuid,text,timestamptz),
    pf_product.create_session(uuid,text,text,timestamptz),pf_product.revoke_workspace(uuid)
    TO pf_product_provisioner;
GRANT EXECUTE ON FUNCTION pf_product.session_context(text),
    pf_product.register_asset(uuid,text,text,uuid,text,text,integer),
    pf_product.get_asset(uuid,text,uuid),pf_product.revoke_session(uuid,text,text)
    TO pf_product_api;
COMMIT;

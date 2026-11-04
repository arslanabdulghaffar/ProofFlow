-- Revoke first, await terminal cleanup, remove bytes, then erase raw metadata.
-- Existing operator synthetic evidence is retained unless explicitly deleted.
BEGIN;
SET LOCAL ROLE pf_product_owner;
CREATE TABLE pf_product.deletions (
    workspace_id uuid PRIMARY KEY,
    requested_at timestamptz NOT NULL DEFAULT clock_timestamp(),
    reason text NOT NULL CHECK(reason IN ('owner','expiry')),
    manifest_sha256 text,
    completed_at timestamptz
);
CREATE FUNCTION pf_product.no_deleted_workspace_reuse() RETURNS trigger
LANGUAGE plpgsql SECURITY DEFINER SET search_path=pg_catalog,pg_temp AS $$
BEGIN
    IF EXISTS(SELECT 1 FROM pf_product.deletions WHERE workspace_id=NEW.id) THEN
        RAISE EXCEPTION 'WORKSPACE_DELETED';
    END IF;
    RETURN NEW;
END;
$$;
CREATE TRIGGER no_deleted_workspace_reuse BEFORE INSERT ON pf_product.workspaces
FOR EACH ROW EXECUTE FUNCTION pf_product.no_deleted_workspace_reuse();

CREATE FUNCTION pf_product.request_deletion(workspace uuid, session_digest text, csrf_digest text)
RETURNS boolean LANGUAGE plpgsql SECURITY DEFINER SET search_path=pg_catalog,pg_temp AS $$
BEGIN
    PERFORM pf_product.authorize(workspace,session_digest,csrf_digest,true);
    INSERT INTO pf_product.deletions(workspace_id,reason) VALUES(workspace,'owner')
        ON CONFLICT DO NOTHING;
    UPDATE pf_product.workspaces SET revoked_at=COALESCE(revoked_at,clock_timestamp()) WHERE id=workspace;
    RETURN true;
END;
$$;

CREATE FUNCTION pf_product.retention_plan() RETURNS jsonb
LANGUAGE plpgsql SECURITY DEFINER SET search_path=pg_catalog,pg_temp AS $$
DECLARE w pf_product.workspaces%ROWTYPE; plan jsonb; plans jsonb:='[]'; digest text;
BEGIN
    PERFORM pf_product.require_transaction();
    PERFORM pg_advisory_xact_lock(604061,2);
    FOR w IN SELECT * FROM pf_product.workspaces x WHERE
        (x.kind='guest' AND x.expires_at<=clock_timestamp()+interval '5 minutes')
        OR EXISTS(SELECT 1 FROM pf_product.deletions d WHERE d.workspace_id=x.id)
        ORDER BY x.created_at FOR UPDATE
    LOOP
        INSERT INTO pf_product.deletions(workspace_id,reason) VALUES(w.id,'expiry')
            ON CONFLICT DO NOTHING;
        UPDATE pf_product.workspaces SET revoked_at=COALESCE(revoked_at,clock_timestamp()) WHERE id=w.id;
        -- API byte operations finish under filesystem locks. Running execution
        -- is cancelled/reconciled by the normal dispatcher after this revocation.
        IF EXISTS(SELECT 1 FROM pf_product.jobs WHERE workspace_id=w.id AND
            (state NOT IN ('NEEDS_REVIEW','FAILED_INFRA','CANCELLED')
             OR lease_owner IS NOT NULL OR (execution_id IS NOT NULL
                AND worker_receipt->>'cleanup' IS DISTINCT FROM 'confirmed'))) THEN
            CONTINUE;
        END IF;
        SELECT jsonb_build_object('workspace',w.id::text,
            'jobs',COALESCE(jsonb_agg(id::text ORDER BY id) FILTER(WHERE id IS NOT NULL),'[]'::jsonb))
            INTO plan FROM pf_product.jobs WHERE workspace_id=w.id;
        digest:=encode(sha256(convert_to(plan::text,'UTF8')),'hex');
        UPDATE pf_product.deletions SET manifest_sha256=digest WHERE workspace_id=w.id;
        plans:=plans||jsonb_build_array(plan||jsonb_build_object('manifest_sha256',digest));
    END LOOP;
    RETURN plans;
END;
$$;

CREATE FUNCTION pf_product.complete_deletion(workspace uuid, digest text) RETURNS boolean
LANGUAGE plpgsql SECURITY DEFINER SET search_path=pg_catalog,pg_temp AS $$
DECLARE d pf_product.deletions%ROWTYPE;
BEGIN
    PERFORM pf_product.require_transaction();
    PERFORM pg_advisory_xact_lock(604061,2);
    PERFORM 1 FROM pf_product.workspaces WHERE id=workspace FOR UPDATE;
    SELECT * INTO d FROM pf_product.deletions WHERE workspace_id=workspace FOR UPDATE;
    IF NOT FOUND OR digest IS NULL OR d.manifest_sha256 IS DISTINCT FROM digest THEN
        RAISE EXCEPTION 'RETENTION_MANIFEST_MISMATCH';
    END IF;
    IF d.completed_at IS NOT NULL THEN RETURN false; END IF;
    IF EXISTS(SELECT 1 FROM pf_product.jobs WHERE workspace_id=workspace AND
        (state NOT IN ('NEEDS_REVIEW','FAILED_INFRA','CANCELLED') OR lease_owner IS NOT NULL
         OR (execution_id IS NOT NULL AND worker_receipt->>'cleanup' IS DISTINCT FROM 'confirmed'))) THEN
        RAISE EXCEPTION 'CLEANUP_REQUIRED';
    END IF;
    DELETE FROM pf_product.job_events WHERE workspace_id=workspace;
    DELETE FROM pf_product.jobs WHERE workspace_id=workspace;
    DELETE FROM pf_product.contract_approvals WHERE workspace_id=workspace;
    DELETE FROM pf_product.uploads WHERE workspace_id=workspace;
    DELETE FROM pf_product.assets WHERE workspace_id=workspace;
    DELETE FROM pf_product.sessions WHERE workspace_id=workspace;
    DELETE FROM pf_product.workspaces WHERE id=workspace;
    UPDATE pf_product.deletions SET completed_at=clock_timestamp() WHERE workspace_id=workspace;
    RETURN true;
END;
$$;
REVOKE ALL ON pf_product.deletions FROM PUBLIC;
REVOKE ALL ON FUNCTION pf_product.no_deleted_workspace_reuse(),
    pf_product.request_deletion(uuid,text,text),pf_product.retention_plan(),
    pf_product.complete_deletion(uuid,text) FROM PUBLIC;
RESET ROLE;
GRANT EXECUTE ON FUNCTION pf_product.request_deletion(uuid,text,text) TO pf_product_api;
GRANT EXECUTE ON FUNCTION pf_product.retention_plan(),pf_product.complete_deletion(uuid,text)
    TO pf_product_provisioner;
COMMIT;

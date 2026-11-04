-- Repair retention extends the existing revoke/cleanup/erase protocol.
BEGIN;
SET LOCAL ROLE pf_product_owner;
CREATE OR REPLACE FUNCTION pf_product.retention_plan() RETURNS jsonb
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
        IF EXISTS(SELECT 1 FROM pf_product.repairs WHERE workspace_id=w.id AND
            (state IN ('QUEUED','RUNNING','RECONCILING') OR lease_owner IS NOT NULL))
            OR EXISTS(SELECT 1 FROM pf_product.repair_executions WHERE workspace_id=w.id AND result IS NULL)
            THEN CONTINUE; END IF;
        SELECT jsonb_build_object('workspace',w.id::text,
            'jobs',COALESCE(jsonb_agg(id::text ORDER BY id) FILTER(WHERE id IS NOT NULL),'[]'::jsonb))
            INTO plan FROM (SELECT id FROM pf_product.jobs WHERE workspace_id=w.id
                UNION ALL SELECT id FROM pf_product.repairs WHERE workspace_id=w.id) owned;
        digest:=encode(sha256(convert_to(plan::text,'UTF8')),'hex');
        UPDATE pf_product.deletions SET manifest_sha256=digest WHERE workspace_id=w.id;
        plans:=plans||jsonb_build_array(plan||jsonb_build_object('manifest_sha256',digest));
    END LOOP;
    RETURN plans;
END;
$$;

CREATE OR REPLACE FUNCTION pf_product.complete_deletion(workspace uuid, digest text) RETURNS boolean
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
    IF EXISTS(SELECT 1 FROM pf_product.repairs WHERE workspace_id=workspace AND
        (state IN ('QUEUED','RUNNING','RECONCILING') OR lease_owner IS NOT NULL))
        OR EXISTS(SELECT 1 FROM pf_product.repair_executions WHERE workspace_id=workspace AND result IS NULL)
        THEN RAISE EXCEPTION 'CLEANUP_REQUIRED'; END IF;
    DELETE FROM pf_product.repair_executions WHERE workspace_id=workspace;
    DELETE FROM pf_product.repair_calls WHERE workspace_id=workspace;
    DELETE FROM pf_product.repairs WHERE workspace_id=workspace;
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
COMMIT;

-- Add version/batch metadata to revocation-first retirement.
BEGIN;
SET LOCAL ROLE pf_product_owner;
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
    DELETE FROM pf_product.version_events WHERE workspace_id=workspace;
    DELETE FROM pf_product.approval_intents WHERE workspace_id=workspace;
    DELETE FROM pf_product.batches WHERE workspace_id=workspace;
    UPDATE pf_product.pipelines SET active_version=NULL WHERE workspace_id=workspace;
    DELETE FROM pf_product.versions WHERE workspace_id=workspace;
    DELETE FROM pf_product.pipelines WHERE workspace_id=workspace;
    DELETE FROM pf_product.repair_events WHERE workspace_id=workspace;
    DELETE FROM pf_product.repair_executions WHERE workspace_id=workspace;
    DELETE FROM pf_product.repair_candidates WHERE workspace_id=workspace;
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
RESET ROLE;
COMMIT;

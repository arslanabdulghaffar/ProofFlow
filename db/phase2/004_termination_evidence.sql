-- Preserve cleanup evidence atomically with terminal failure/cancellation.
BEGIN;
SET LOCAL ROLE pf_product_owner;
CREATE OR REPLACE FUNCTION pf_product.fail_original(workspace uuid, job uuid, controller uuid,
    fence integer, termination jsonb) RETURNS void
LANGUAGE plpgsql SECURITY DEFINER SET search_path=pg_catalog,pg_temp AS $$
DECLARE j pf_product.jobs%ROWTYPE;
BEGIN
    j := pf_product.guard_job(workspace,job,controller,fence,true);
    IF termination IS NULL OR jsonb_typeof(termination)<>'object'
       OR octet_length(termination::text)>65536 THEN RAISE EXCEPTION 'CLEANUP_REQUIRED'; END IF;
    IF j.execution_id IS NULL THEN
        IF termination IS DISTINCT FROM '{"not_dispatched":true}'::jsonb THEN
            RAISE EXCEPTION 'CLEANUP_REQUIRED';
        END IF;
    ELSIF (termination->>'execution') IS DISTINCT FROM replace(j.execution_id::text,'-','')
       OR (termination->>'job') IS DISTINCT FROM replace(job::text,'-','')
       OR (termination->'generation') IS DISTINCT FROM to_jsonb(j.execution_generation)
       OR (termination->>'manifest') IS DISTINCT FROM j.manifest_sha256
       OR (termination->>'cleanup') IS DISTINCT FROM 'confirmed' THEN
        RAISE EXCEPTION 'CLEANUP_REQUIRED';
    END IF;
    UPDATE pf_product.jobs SET cancel_requested=cancel_requested
        OR NOT EXISTS(SELECT 1 FROM pf_product.execution_policy WHERE enabled AND epoch=j.policy_epoch)
        OR NOT EXISTS(SELECT 1 FROM pf_product.workspaces WHERE id=workspace
                      AND revoked_at IS NULL AND expires_at>clock_timestamp())
        OR NOT EXISTS(SELECT 1 FROM pf_product.contract_approvals WHERE workspace_id=workspace
                      AND asset_id=j.contract_id AND revoked_at IS NULL)
        WHERE workspace_id=workspace AND id=job;
    UPDATE pf_product.jobs SET state=CASE WHEN cancel_requested THEN 'CANCELLED' ELSE 'FAILED_INFRA' END,
        outcome=CASE WHEN cancel_requested THEN 'cancelled' ELSE 'infrastructure_failed' END,
        worker_receipt=termination,
        worker_receipt_sha256=encode(sha256(convert_to(termination::text,'UTF8')),'hex'),
        lease_owner=NULL,lease_until=NULL WHERE workspace_id=workspace AND id=job;
    PERFORM pf_product.job_event(workspace,job,'terminated_cleanup_confirmed');
END;
$$;
COMMIT;

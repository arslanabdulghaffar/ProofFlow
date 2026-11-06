-- Code failure is repairable only after clean termination and source-only diagnosis.
-- This does not grant an output proof, activation, batch completion or external write.
BEGIN;
SET LOCAL ROLE pf_product_owner;
ALTER TABLE pf_product.jobs DROP CONSTRAINT jobs_outcome_check;
ALTER TABLE pf_product.jobs ADD CONSTRAINT jobs_outcome_check CHECK(outcome IN
    ('match','mismatch','held','input_rejected','infrastructure_failed','cancelled','execution_failed'));

CREATE FUNCTION pf_product.review_original_failure(workspace uuid, job uuid, controller uuid,
    fence integer, result jsonb) RETURNS void
LANGUAGE plpgsql SECURITY DEFINER SET search_path=pg_catalog,pg_temp AS $$
DECLARE j pf_product.jobs%ROWTYPE; binding jsonb; source jsonb; receipt jsonb; a record;
BEGIN
    j := pf_product.guard_job(workspace,job,controller,fence,false);
    IF j.state<>'BASELINE_RUNNING' OR j.execution_id IS NULL
       OR result IS NULL OR jsonb_typeof(result)<>'object' OR octet_length(result::text)>131072
       OR result->'semantic' IS DISTINCT FROM 'null'::jsonb THEN
        RAISE EXCEPTION 'ORIGINAL_REPORT_INVALID'; END IF;
    binding := result->'intent'; receipt := result->'worker';
    source := result#>'{source,report,result}';
    IF binding->>'execution' IS DISTINCT FROM replace(j.execution_id::text,'-','')
       OR binding->>'job' IS DISTINCT FROM replace(job::text,'-','')
       OR binding->'generation' IS DISTINCT FROM to_jsonb(j.execution_generation)
       OR binding->>'purpose' IS DISTINCT FROM 'original'
       OR binding->>'manifest_sha256' IS DISTINCT FROM j.manifest_sha256
       OR binding->>'runtime_sha256' IS DISTINCT FROM j.runtime_sha256
       OR binding->>'verifier_rootfs' IS DISTINCT FROM j.verifier_sha256
       OR receipt->>'execution' IS DISTINCT FROM binding->>'execution'
       OR receipt->>'job' IS DISTINCT FROM binding->>'job'
       OR receipt->'generation' IS DISTINCT FROM binding->'generation'
       OR receipt->>'manifest' IS DISTINCT FROM j.manifest_sha256
       OR receipt->>'cleanup' IS DISTINCT FROM 'confirmed'
       OR jsonb_typeof(receipt->'runtime') IS DISTINCT FROM 'object'
       OR octet_length(receipt::text)>65536
       OR receipt ? 'failure_log_preview'
       OR receipt->>'outcome' IS NULL OR receipt->>'outcome' NOT IN ('exited','output_rejected')
       OR receipt->>'runtime_exit_kind' IS DISTINCT FROM '1'
       OR jsonb_typeof(receipt->'runtime_client_exit_code') IS DISTINCT FROM 'number'
       OR receipt->>'runtime_client_exit_code' !~ '^(0|[1-9][0-9]{0,2})$' THEN
        RAISE EXCEPTION 'ORIGINAL_REPORT_BINDING_MISMATCH'; END IF;
    IF (receipt->>'runtime_client_exit_code')::integer>125
       OR receipt->>'runtime_exit_code' IS DISTINCT FROM receipt->>'runtime_client_exit_code'
       OR ((receipt->>'runtime_client_exit_code'<>'0' AND receipt->>'unit_result'='exit-code')
            OR (receipt->>'runtime_client_exit_code'='0' AND receipt->>'unit_result'='success'
                AND receipt->>'outcome'='output_rejected')) IS DISTINCT FROM true
       OR result#>'{source,cleanup_confirmed}' IS DISTINCT FROM 'true'::jsonb
       OR result#>>'{source,rootfs_sha256}' IS DISTINCT FROM j.verifier_sha256
       OR result#>>'{source,report,status}' IS DISTINCT FROM 'processed'
       OR result#>>'{source,report,version}' IS DISTINCT FROM 'proofflow-verifier-v1'
       OR source->>'operation' IS DISTINCT FROM 'source'
       OR jsonb_typeof(source->'blocking_occurrences') IS DISTINCT FROM 'number'
       OR source->>'blocking_occurrences' !~ '^(0|[1-9][0-9]{0,4})$'
       OR source ?| ARRAY['comparison','output_hashes','findings','finding_count'] THEN
        RAISE EXCEPTION 'ORIGINAL_REPORT_BINDING_MISMATCH'; END IF;
    IF (source->>'blocking_occurrences')::integer>10000 THEN
        RAISE EXCEPTION 'ORIGINAL_REPORT_BINDING_MISMATCH'; END IF;
    FOR a IN SELECT kind,sha256 FROM pf_product.assets WHERE workspace_id=workspace
             AND id IN (j.pipeline_id,j.transactions_id,j.customers_id,j.contract_id)
    LOOP
        IF binding->>(CASE a.kind WHEN 'contract' THEN 'contract_raw_sha256'
                       ELSE a.kind||'_sha256' END) IS DISTINCT FROM a.sha256
           OR (a.kind IN ('transactions','customers')
               AND source->>(a.kind||'_sha256') IS DISTINCT FROM a.sha256) THEN
            RAISE EXCEPTION 'ORIGINAL_SOURCE_HASH_MISMATCH'; END IF;
    END LOOP;
    IF source->>'contract_sha256' IS NULL
       OR source->>'contract_sha256' IS DISTINCT FROM binding->>'contract_sha256' THEN
        RAISE EXCEPTION 'ORIGINAL_CONTRACT_HASH_MISMATCH'; END IF;
    UPDATE pf_product.jobs SET state='NEEDS_REVIEW',
        outcome=CASE WHEN (source->>'blocking_occurrences')::integer>0 THEN 'held' ELSE 'execution_failed' END,
        worker_receipt=receipt, worker_receipt_sha256=encode(sha256(convert_to(receipt::text,'UTF8')),'hex'),
        report=result,lease_owner=NULL,lease_until=NULL WHERE workspace_id=workspace AND id=job;
    PERFORM pf_product.job_event(workspace,job,'original_execution_failure_recorded');
END; $$;

CREATE OR REPLACE FUNCTION pf_product.enqueue_repair(w uuid,s text,c text,r uuid,i uuid,parent uuid) RETURNS uuid
LANGUAGE plpgsql SECURITY DEFINER SET search_path=pg_catalog,pg_temp AS $$
DECLARE p pf_product.execution_policy%ROWTYPE; j pf_product.jobs%ROWTYPE; old pf_product.repairs%ROWTYPE;
BEGIN
    PERFORM pf_product.require_transaction();
    SELECT * INTO p FROM pf_product.execution_policy WHERE singleton FOR SHARE;
    IF NOT FOUND OR NOT p.enabled THEN RAISE EXCEPTION 'ADMISSION_CLOSED'; END IF;
    PERFORM pf_product.authorize(w,s,c,true);
    SELECT * INTO old FROM pf_product.repairs WHERE workspace_id=w AND idempotency_key=i;
    IF FOUND THEN
        IF old.parent_id IS DISTINCT FROM parent OR old.policy_epoch<>p.epoch THEN
            RAISE EXCEPTION 'JOB_IDEMPOTENCY_CONFLICT'; END IF;
        RETURN old.id;
    END IF;
    SELECT * INTO j FROM pf_product.jobs WHERE workspace_id=w AND id=parent;
    IF NOT FOUND OR j.state<>'NEEDS_REVIEW' OR j.outcome NOT IN ('mismatch','match','execution_failed')
       OR j.runtime_sha256<>p.runtime_sha256 OR j.verifier_sha256<>p.verifier_sha256
       OR (CASE WHEN j.outcome='execution_failed' THEN j.report#>'{source,report,result,blocking_occurrences}'
                ELSE j.report#>'{semantic,report,result,blocking_occurrences}' END) IS DISTINCT FROM '0'::jsonb
       OR NOT EXISTS(SELECT 1 FROM pf_product.contract_approvals WHERE workspace_id=w
                     AND asset_id=j.contract_id AND revoked_at IS NULL) THEN
        RAISE EXCEPTION 'REPAIR_PARENT_INVALID';
    END IF;
    PERFORM pg_advisory_xact_lock(604061,3);
    IF (SELECT count(*) FROM pf_product.repairs)>=16 THEN RAISE EXCEPTION 'JOB_CAPACITY'; END IF;
    INSERT INTO pf_product.repairs(workspace_id,id,parent_id,idempotency_key,policy_epoch)
        VALUES(w,r,parent,i,p.epoch);
    RETURN r;
END; $$;
REVOKE ALL ON FUNCTION pf_product.review_original_failure(uuid,uuid,uuid,integer,jsonb) FROM PUBLIC;
RESET ROLE;
GRANT EXECUTE ON FUNCTION pf_product.review_original_failure(uuid,uuid,uuid,integer,jsonb) TO pf_product_dispatcher;
COMMIT;

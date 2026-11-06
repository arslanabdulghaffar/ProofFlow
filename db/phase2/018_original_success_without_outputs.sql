-- A stopped successful unit can report exit-kind0. Require observed kernel startup limits,
-- exact client/status0 and success before diagnosing its rejected output. No output proof.
BEGIN;
SET LOCAL ROLE pf_product_owner;
CREATE OR REPLACE FUNCTION pf_product.review_original_failure(workspace uuid, job uuid, controller uuid,
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
       OR receipt#>>'{resource_observation,source}' IS DISTINCT FROM 'host_cgroup_v2'
       OR jsonb_typeof(receipt#>'{resource_observation,samples}') IS DISTINCT FROM 'number'
       OR receipt#>>'{resource_observation,samples}' !~ '^[1-9][0-9]{0,8}$'
       OR receipt#>'{resource_observation,limits}' IS DISTINCT FROM
          '{"cpu_cores":1,"memory_bytes":805306368,"swap_bytes":0,"host_tasks":128}'::jsonb
       OR jsonb_typeof(receipt->'runtime_client_exit_code') IS DISTINCT FROM 'number'
       OR receipt->>'runtime_client_exit_code' !~ '^(0|[1-9][0-9]{0,2})$' THEN
        RAISE EXCEPTION 'ORIGINAL_REPORT_BINDING_MISMATCH'; END IF;
    IF (receipt->>'runtime_client_exit_code')::integer>125
       OR receipt->>'runtime_exit_code' IS DISTINCT FROM receipt->>'runtime_client_exit_code'
       OR ((receipt->>'runtime_client_exit_code'<>'0' AND receipt->>'unit_result'='exit-code'
                AND receipt->>'runtime_exit_kind'='1')
            OR (receipt->>'runtime_client_exit_code'='0' AND receipt->>'unit_result'='success'
                AND receipt->>'runtime_exit_kind' IN ('0','1')
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

RESET ROLE;
COMMIT;

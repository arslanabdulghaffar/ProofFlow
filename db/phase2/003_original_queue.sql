-- Private Phase2 original-run queue; no activation, batch completion or external writes.
BEGIN;
DO $$ BEGIN
    IF current_database()<>'proofflow_product' THEN RAISE EXCEPTION 'WRONG_PRODUCT_DATABASE'; END IF;
END $$;
CREATE ROLE pf_product_dispatcher NOLOGIN;
SET LOCAL ROLE pf_product_owner;
CREATE TABLE pf_product.execution_policy (
    singleton boolean PRIMARY KEY DEFAULT true CHECK(singleton),
    epoch bigint NOT NULL CHECK(epoch>0),
    runtime_sha256 text NOT NULL CHECK(runtime_sha256 ~ '^[0-9a-f]{64}$'),
    verifier_sha256 text NOT NULL CHECK(verifier_sha256 ~ '^[0-9a-f]{64}$'),
    enabled boolean NOT NULL DEFAULT false
);
CREATE TABLE pf_product.contract_approvals (
    workspace_id uuid NOT NULL,
    asset_id uuid NOT NULL,
    sha256 text NOT NULL CHECK(sha256 ~ '^[0-9a-f]{64}$'),
    session_hash text NOT NULL REFERENCES pf_product.sessions(token_hash),
    approved_at timestamptz NOT NULL DEFAULT clock_timestamp(),
    revoked_at timestamptz,
    PRIMARY KEY(workspace_id,asset_id),
    FOREIGN KEY(workspace_id,asset_id) REFERENCES pf_product.assets(workspace_id,id)
);
CREATE TABLE pf_product.jobs (
    workspace_id uuid NOT NULL REFERENCES pf_product.workspaces(id),
    id uuid NOT NULL,
    idempotency_key uuid NOT NULL,
    pipeline_id uuid NOT NULL,
    transactions_id uuid NOT NULL,
    customers_id uuid NOT NULL,
    contract_id uuid NOT NULL,
    policy_epoch bigint NOT NULL,
    runtime_sha256 text NOT NULL CHECK(runtime_sha256 ~ '^[0-9a-f]{64}$'),
    verifier_sha256 text NOT NULL CHECK(verifier_sha256 ~ '^[0-9a-f]{64}$'),
    state text NOT NULL DEFAULT 'QUEUED' CHECK(state IN
        ('QUEUED','BASELINE_RUNNING','BASELINE_VERIFYING','RECONCILING',
         'NEEDS_REVIEW','FAILED_INFRA','CANCELLED')),
    created_at timestamptz NOT NULL DEFAULT clock_timestamp(),
    cancel_requested boolean NOT NULL DEFAULT false,
    generation integer NOT NULL DEFAULT 0 CHECK(generation>=0),
    lease_owner uuid,
    lease_until timestamptz,
    execution_id uuid UNIQUE,
    execution_generation integer,
    manifest_sha256 text CHECK(manifest_sha256 ~ '^[0-9a-f]{64}$'),
    worker_receipt_sha256 text CHECK(worker_receipt_sha256 ~ '^[0-9a-f]{64}$'),
    worker_receipt jsonb CHECK(worker_receipt IS NULL OR octet_length(worker_receipt::text)<=65536),
    report jsonb,
    outcome text CHECK(outcome IN ('match','mismatch','held','input_rejected',
                                  'infrastructure_failed','cancelled')),
    event_sequence bigint NOT NULL DEFAULT 0,
    PRIMARY KEY(workspace_id,id), UNIQUE(workspace_id,idempotency_key),
    FOREIGN KEY(workspace_id,pipeline_id) REFERENCES pf_product.assets(workspace_id,id),
    FOREIGN KEY(workspace_id,transactions_id) REFERENCES pf_product.assets(workspace_id,id),
    FOREIGN KEY(workspace_id,customers_id) REFERENCES pf_product.assets(workspace_id,id),
    FOREIGN KEY(workspace_id,contract_id) REFERENCES pf_product.contract_approvals(workspace_id,asset_id),
    CHECK((execution_id IS NULL)=(execution_generation IS NULL)),
    CHECK((execution_id IS NULL)=(manifest_sha256 IS NULL)),
    CHECK(report IS NULL OR octet_length(report::text)<=131072)
);
CREATE TABLE pf_product.job_events (
    workspace_id uuid NOT NULL, job_id uuid NOT NULL, sequence bigint NOT NULL,
    occurred_at timestamptz NOT NULL DEFAULT clock_timestamp(),
    state text NOT NULL, event text NOT NULL,
    PRIMARY KEY(workspace_id,job_id,sequence),
    FOREIGN KEY(workspace_id,job_id) REFERENCES pf_product.jobs(workspace_id,id)
);

CREATE FUNCTION pf_product.job_event(workspace uuid, job uuid, event_code text) RETURNS void
LANGUAGE plpgsql SECURITY DEFINER SET search_path=pg_catalog,pg_temp AS $$
DECLARE n bigint; stage text;
BEGIN
    UPDATE pf_product.jobs SET event_sequence=event_sequence+1 WHERE workspace_id=workspace AND id=job
        RETURNING event_sequence,state INTO n,stage;
    INSERT INTO pf_product.job_events(workspace_id,job_id,sequence,state,event)
        VALUES(workspace,job,n,stage,event_code);
END;
$$;

CREATE FUNCTION pf_product.configure_execution(runtime_digest text, verifier_digest text,
    admission boolean) RETURNS bigint
LANGUAGE plpgsql SECURITY DEFINER SET search_path=pg_catalog,pg_temp AS $$
DECLARE version bigint;
BEGIN
    PERFORM pf_product.require_transaction();
    IF runtime_digest IS NULL OR runtime_digest !~ '^[0-9a-f]{64}$'
       OR verifier_digest IS NULL OR verifier_digest !~ '^[0-9a-f]{64}$' OR admission IS NULL THEN
        RAISE EXCEPTION 'INVALID_EXECUTION_POLICY';
    END IF;
    INSERT INTO pf_product.execution_policy VALUES(true,1,runtime_digest,verifier_digest,admission)
        ON CONFLICT(singleton) DO UPDATE SET epoch=pf_product.execution_policy.epoch+1,
            runtime_sha256=EXCLUDED.runtime_sha256,verifier_sha256=EXCLUDED.verifier_sha256,
            enabled=EXCLUDED.enabled RETURNING epoch INTO version;
    RETURN version;
END;
$$;

CREATE FUNCTION pf_product.approve_contract(workspace uuid, session_digest text, csrf_digest text,
    asset uuid, expected_sha256 text) RETURNS boolean
LANGUAGE plpgsql SECURITY DEFINER SET search_path=pg_catalog,pg_temp AS $$
DECLARE a pf_product.assets%ROWTYPE; approval pf_product.contract_approvals%ROWTYPE;
BEGIN
    PERFORM pf_product.authorize(workspace,session_digest,csrf_digest,true);
    SELECT * INTO a FROM pf_product.assets WHERE workspace_id=workspace AND id=asset;
    IF NOT FOUND OR a.kind<>'contract' OR a.sha256 IS DISTINCT FROM expected_sha256 THEN
        RAISE EXCEPTION 'EXACT_CONTRACT_REQUIRED';
    END IF;
    SELECT * INTO approval FROM pf_product.contract_approvals
        WHERE workspace_id=workspace AND asset_id=asset;
    IF FOUND THEN
        IF approval.revoked_at IS NOT NULL THEN RAISE EXCEPTION 'CONTRACT_REVOKED'; END IF;
        RETURN false;
    END IF;
    INSERT INTO pf_product.contract_approvals(workspace_id,asset_id,sha256,session_hash)
        VALUES(workspace,asset,a.sha256,session_digest);
    RETURN true;
END;
$$;

CREATE FUNCTION pf_product.revoke_contract(workspace uuid, session_digest text, csrf_digest text,
    asset uuid) RETURNS void
LANGUAGE plpgsql SECURITY DEFINER SET search_path=pg_catalog,pg_temp AS $$
BEGIN
    PERFORM pf_product.authorize(workspace,session_digest,csrf_digest,true);
    UPDATE pf_product.contract_approvals SET revoked_at=COALESCE(revoked_at,clock_timestamp())
        WHERE workspace_id=workspace AND asset_id=asset;
END;
$$;

CREATE FUNCTION pf_product.enqueue_original(workspace uuid, session_digest text, csrf_digest text,
    job uuid, idem uuid, pipeline uuid, transactions uuid, customers uuid, contract uuid) RETURNS uuid
LANGUAGE plpgsql SECURITY DEFINER SET search_path=pg_catalog,pg_temp AS $$
DECLARE policy pf_product.execution_policy%ROWTYPE; old pf_product.jobs%ROWTYPE;
BEGIN
    PERFORM pf_product.require_transaction();
    SELECT * INTO policy FROM pf_product.execution_policy WHERE singleton FOR SHARE;
    IF NOT FOUND OR NOT policy.enabled THEN RAISE EXCEPTION 'ADMISSION_CLOSED'; END IF;
    PERFORM pf_product.authorize(workspace,session_digest,csrf_digest,true);
    IF job IS NULL OR idem IS NULL THEN RAISE EXCEPTION 'INVALID_JOB'; END IF;
    SELECT * INTO old FROM pf_product.jobs WHERE workspace_id=workspace AND idempotency_key=idem;
    IF FOUND THEN
        IF old.pipeline_id IS DISTINCT FROM pipeline OR old.transactions_id IS DISTINCT FROM transactions
           OR old.customers_id IS DISTINCT FROM customers OR old.contract_id IS DISTINCT FROM contract
           OR old.policy_epoch<>policy.epoch THEN RAISE EXCEPTION 'JOB_IDEMPOTENCY_CONFLICT'; END IF;
        RETURN old.id;
    END IF;
    IF NOT EXISTS(SELECT 1 FROM pf_product.assets WHERE workspace_id=workspace AND id=pipeline AND kind='pipeline')
       OR NOT EXISTS(SELECT 1 FROM pf_product.assets WHERE workspace_id=workspace AND id=transactions AND kind='transactions')
       OR NOT EXISTS(SELECT 1 FROM pf_product.assets WHERE workspace_id=workspace AND id=customers AND kind='customers')
       OR NOT EXISTS(SELECT 1 FROM pf_product.contract_approvals WHERE workspace_id=workspace
                     AND asset_id=contract AND revoked_at IS NULL) THEN RAISE EXCEPTION 'JOB_ASSETS_INVALID'; END IF;
    PERFORM pg_advisory_xact_lock(604061,3);
    IF (SELECT count(*) FROM pf_product.jobs)>=16 THEN
        RAISE EXCEPTION 'JOB_CAPACITY';
    END IF;
    INSERT INTO pf_product.jobs(workspace_id,id,idempotency_key,pipeline_id,transactions_id,
                               customers_id,contract_id,policy_epoch,runtime_sha256,verifier_sha256)
        VALUES(workspace,job,idem,pipeline,transactions,customers,contract,policy.epoch,
               policy.runtime_sha256,policy.verifier_sha256);
    PERFORM pf_product.job_event(workspace,job,'enqueued');
    RETURN job;
END;
$$;

CREATE FUNCTION pf_product.get_job(workspace uuid, session_digest text, job uuid) RETURNS jsonb
LANGUAGE plpgsql SECURITY DEFINER SET search_path=pg_catalog,pg_temp AS $$
DECLARE value jsonb;
BEGIN
    PERFORM pf_product.authorize(workspace,session_digest,NULL,false);
    SELECT jsonb_build_object('id',j.id,'state',j.state,'outcome',j.outcome,
        'cancel_requested',j.cancel_requested,'created_at',j.created_at,'sequence',j.event_sequence,
        'report',j.report) INTO value FROM pf_product.jobs j WHERE j.workspace_id=workspace AND j.id=job;
    RETURN value;
END;
$$;

CREATE FUNCTION pf_product.cancel_job(workspace uuid, session_digest text, csrf_digest text,
    job uuid) RETURNS boolean
LANGUAGE plpgsql SECURITY DEFINER SET search_path=pg_catalog,pg_temp AS $$
DECLARE j pf_product.jobs%ROWTYPE;
BEGIN
    PERFORM pf_product.authorize(workspace,session_digest,csrf_digest,true);
    SELECT * INTO j FROM pf_product.jobs WHERE workspace_id=workspace AND id=job FOR UPDATE;
    IF NOT FOUND THEN RAISE EXCEPTION 'JOB_NOT_FOUND'; END IF;
    IF j.state IN ('NEEDS_REVIEW','FAILED_INFRA','CANCELLED') OR j.cancel_requested THEN RETURN false; END IF;
    UPDATE pf_product.jobs SET cancel_requested=true,
        state=CASE WHEN j.state='QUEUED' THEN 'CANCELLED' ELSE j.state END,
        outcome=CASE WHEN j.state='QUEUED' THEN 'cancelled' ELSE outcome END
        WHERE workspace_id=workspace AND id=job;
    PERFORM pf_product.job_event(workspace,job,'cancellation_requested');
    RETURN true;
END;
$$;

CREATE FUNCTION pf_product.claim_original(controller uuid) RETURNS jsonb
LANGUAGE plpgsql SECURITY DEFINER SET search_path=pg_catalog,pg_temp AS $$
DECLARE policy pf_product.execution_policy%ROWTYPE; w pf_product.workspaces%ROWTYPE;
    j pf_product.jobs%ROWTYPE; invalid boolean;
BEGIN
    PERFORM pf_product.require_transaction();
    IF controller IS NULL THEN RAISE EXCEPTION 'INVALID_CONTROLLER'; END IF;
    PERFORM pg_advisory_xact_lock(604061,2);
    SELECT * INTO policy FROM pf_product.execution_policy WHERE singleton FOR SHARE;
    IF NOT FOUND THEN RETURN NULL; END IF;
    -- One designated worker. Lease renewal uses this same short admission lock.
    IF EXISTS(SELECT 1 FROM pf_product.jobs WHERE lease_until>clock_timestamp()
              AND state IN ('BASELINE_RUNNING','BASELINE_VERIFYING','RECONCILING')) THEN
        RETURN NULL;
    END IF;
    FOR w IN SELECT * FROM pf_product.workspaces x WHERE EXISTS(
        SELECT 1 FROM pf_product.jobs y WHERE y.workspace_id=x.id AND (y.state='QUEUED'
        OR (y.state IN ('BASELINE_RUNNING','BASELINE_VERIFYING','RECONCILING')
            AND y.lease_until<=clock_timestamp())))
        ORDER BY EXISTS(SELECT 1 FROM pf_product.jobs z WHERE z.workspace_id=x.id
                        AND z.state IN ('BASELINE_RUNNING','BASELINE_VERIFYING','RECONCILING')) DESC,
                 x.created_at FOR UPDATE SKIP LOCKED
    LOOP
        SELECT * INTO j FROM pf_product.jobs WHERE workspace_id=w.id AND (state='QUEUED'
            OR (state IN ('BASELINE_RUNNING','BASELINE_VERIFYING','RECONCILING')
                AND lease_until<=clock_timestamp()))
            ORDER BY (execution_id IS NOT NULL) DESC,created_at FOR UPDATE SKIP LOCKED LIMIT 1;
        IF NOT FOUND THEN CONTINUE; END IF;
        IF j.generation>=5 THEN
            -- Preserve uncertainty and hold the single worker capacity for operator
            -- reconciliation; never manufacture failure/cleanup or loop forever.
            RETURN NULL;
        END IF;
        invalid := NOT policy.enabled OR j.policy_epoch<>policy.epoch OR j.cancel_requested
            OR w.revoked_at IS NOT NULL OR w.expires_at<=clock_timestamp()
            OR NOT EXISTS(SELECT 1 FROM pf_product.contract_approvals WHERE workspace_id=w.id
                          AND asset_id=j.contract_id AND revoked_at IS NULL);
        IF invalid AND j.execution_id IS NULL THEN
            UPDATE pf_product.jobs SET state='CANCELLED',cancel_requested=true,outcome='cancelled'
                WHERE workspace_id=w.id AND id=j.id;
            PERFORM pf_product.job_event(w.id,j.id,'cancelled_before_dispatch');
            CONTINUE;
        END IF;
        UPDATE pf_product.jobs SET generation=generation+1,lease_owner=controller,
            lease_until=clock_timestamp()+interval '45 seconds', cancel_requested=invalid,
            state=CASE WHEN j.execution_id IS NULL THEN 'BASELINE_RUNNING' ELSE 'RECONCILING' END
            WHERE workspace_id=w.id AND id=j.id RETURNING * INTO j;
        PERFORM pf_product.job_event(w.id,j.id,'lease_claimed');
        RETURN to_jsonb(j);
    END LOOP;
    RETURN NULL;
END;
$$;

CREATE FUNCTION pf_product.guard_job(workspace uuid, job uuid, controller uuid, fence integer,
    allow_cancel boolean) RETURNS pf_product.jobs
LANGUAGE plpgsql SECURITY DEFINER SET search_path=pg_catalog,pg_temp AS $$
DECLARE policy pf_product.execution_policy%ROWTYPE; w pf_product.workspaces%ROWTYPE;
    j pf_product.jobs%ROWTYPE;
BEGIN
    PERFORM pf_product.require_transaction();
    PERFORM pg_advisory_xact_lock(604061,2);
    SELECT * INTO policy FROM pf_product.execution_policy WHERE singleton FOR SHARE;
    SELECT * INTO w FROM pf_product.workspaces WHERE id=workspace FOR UPDATE;
    SELECT * INTO j FROM pf_product.jobs WHERE workspace_id=workspace AND id=job FOR UPDATE;
    IF NOT FOUND OR allow_cancel IS NULL OR j.lease_owner IS DISTINCT FROM controller
       OR j.generation IS DISTINCT FROM fence OR j.lease_until IS NULL
       OR j.lease_until<=clock_timestamp()
       OR j.state NOT IN ('BASELINE_RUNNING','BASELINE_VERIFYING','RECONCILING') THEN
        RAISE EXCEPTION 'STALE_JOB_LEASE';
    END IF;
    IF NOT allow_cancel AND (NOT policy.enabled OR j.policy_epoch<>policy.epoch OR j.cancel_requested
        OR w.revoked_at IS NOT NULL OR w.expires_at<=clock_timestamp()
        OR NOT EXISTS(SELECT 1 FROM pf_product.contract_approvals WHERE workspace_id=workspace
                      AND asset_id=j.contract_id AND revoked_at IS NULL)) THEN
        RAISE EXCEPTION 'JOB_AUTHORITY_REVOKED';
    END IF;
    RETURN j;
END;
$$;

CREATE FUNCTION pf_product.heartbeat_original(workspace uuid, job uuid, controller uuid,
    fence integer) RETURNS void
LANGUAGE plpgsql SECURITY DEFINER SET search_path=pg_catalog,pg_temp AS $$
BEGIN
    PERFORM pf_product.guard_job(workspace,job,controller,fence,false);
    UPDATE pf_product.jobs SET lease_until=clock_timestamp()+interval '45 seconds'
        WHERE workspace_id=workspace AND id=job;
END;
$$;

CREATE FUNCTION pf_product.dispatch_assets(workspace uuid, job uuid, controller uuid,
    fence integer) RETURNS jsonb
LANGUAGE plpgsql SECURITY DEFINER SET search_path=pg_catalog,pg_temp AS $$
DECLARE j pf_product.jobs%ROWTYPE; result jsonb;
BEGIN
    j := pf_product.guard_job(workspace,job,controller,fence,false);
    SELECT jsonb_agg(jsonb_build_object('id',id,'kind',kind,'sha256',sha256,'bytes',byte_size))
        INTO result FROM pf_product.assets WHERE workspace_id=workspace
        AND id IN (j.pipeline_id,j.transactions_id,j.customers_id,j.contract_id);
    RETURN result;
END;
$$;

CREATE FUNCTION pf_product.begin_original(workspace uuid, job uuid, controller uuid,
    fence integer, execution uuid, manifest text) RETURNS void
LANGUAGE plpgsql SECURITY DEFINER SET search_path=pg_catalog,pg_temp AS $$
DECLARE j pf_product.jobs%ROWTYPE;
BEGIN
    j := pf_product.guard_job(workspace,job,controller,fence,false);
    IF j.state<>'BASELINE_RUNNING' OR j.execution_id IS NOT NULL OR execution IS NULL
       OR manifest IS NULL OR manifest !~ '^[0-9a-f]{64}$' THEN
        RAISE EXCEPTION 'EXECUTION_INTENT_CONFLICT';
    END IF;
    UPDATE pf_product.jobs SET execution_id=execution,execution_generation=fence,manifest_sha256=manifest
        WHERE workspace_id=workspace AND id=job;
    PERFORM pf_product.job_event(workspace,job,'original_intent_committed');
END;
$$;

CREATE FUNCTION pf_product.reject_original_input(workspace uuid, job uuid, controller uuid,
    fence integer) RETURNS void
LANGUAGE plpgsql SECURITY DEFINER SET search_path=pg_catalog,pg_temp AS $$
DECLARE j pf_product.jobs%ROWTYPE;
BEGIN
    j := pf_product.guard_job(workspace,job,controller,fence,false);
    IF j.execution_id IS NOT NULL THEN RAISE EXCEPTION 'EXECUTION_INTENT_CONFLICT'; END IF;
    UPDATE pf_product.jobs SET state='NEEDS_REVIEW',outcome='input_rejected',
        report='{"source_error":"SOURCE_PREPARATION_REJECTED"}'::jsonb,
        lease_owner=NULL,lease_until=NULL WHERE workspace_id=workspace AND id=job;
    PERFORM pf_product.job_event(workspace,job,'source_preparation_rejected');
END;
$$;

CREATE FUNCTION pf_product.original_collected(workspace uuid, job uuid, controller uuid,
    fence integer, execution uuid, receipt jsonb) RETURNS void
LANGUAGE plpgsql SECURITY DEFINER SET search_path=pg_catalog,pg_temp AS $$
DECLARE j pf_product.jobs%ROWTYPE;
BEGIN
    j := pf_product.guard_job(workspace,job,controller,fence,false);
    IF j.state<>'BASELINE_RUNNING' OR j.execution_id IS NULL OR j.execution_id IS DISTINCT FROM execution
       OR receipt IS NULL OR jsonb_typeof(receipt)<>'object' OR octet_length(receipt::text)>65536
       OR (receipt->>'execution') IS DISTINCT FROM replace(execution::text,'-','')
       OR (receipt->>'job') IS DISTINCT FROM replace(job::text,'-','')
       OR (receipt->'generation') IS DISTINCT FROM to_jsonb(j.execution_generation)
       OR (receipt->>'manifest') IS DISTINCT FROM j.manifest_sha256
       OR (receipt->'collected') IS DISTINCT FROM 'true'::jsonb
       OR (receipt->>'cleanup') IS DISTINCT FROM 'confirmed'
       OR (receipt->'runtime_client_exit_code') IS DISTINCT FROM '0'::jsonb
       OR (receipt->>'unit_result') IS DISTINCT FROM 'success' THEN
        RAISE EXCEPTION 'COLLECTED_EXECUTION_MISMATCH';
    END IF;
    UPDATE pf_product.jobs SET state='BASELINE_VERIFYING',worker_receipt=receipt,
        worker_receipt_sha256=encode(sha256(convert_to(receipt::text,'UTF8')),'hex')
        WHERE workspace_id=workspace AND id=job;
    PERFORM pf_product.job_event(workspace,job,'original_collected_cleanup_confirmed');
END;
$$;

-- Only failure/cancellation reconciliation is supported after lease loss. A new
-- controller must fence the worker and prove cleanup; never start a replacement.
CREATE FUNCTION pf_product.fail_original(workspace uuid, job uuid, controller uuid,
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
        lease_owner=NULL,lease_until=NULL WHERE workspace_id=workspace AND id=job;
    PERFORM pf_product.job_event(workspace,job,'terminated_cleanup_confirmed');
END;
$$;

CREATE FUNCTION pf_product.finish_original(workspace uuid, job uuid, controller uuid,
    fence integer, result jsonb) RETURNS void
LANGUAGE plpgsql SECURITY DEFINER SET search_path=pg_catalog,pg_temp AS $$
DECLARE j pf_product.jobs%ROWTYPE; semantic jsonb; binding jsonb; a record; disposition text;
    hashes jsonb; files integer; distinct_names integer;
BEGIN
    j := pf_product.guard_job(workspace,job,controller,fence,false);
    IF j.state<>'BASELINE_VERIFYING' OR result IS NULL OR jsonb_typeof(result)<>'object'
       OR octet_length(result::text)>131072 THEN RAISE EXCEPTION 'ORIGINAL_REPORT_INVALID'; END IF;
    binding := result->'intent';
    semantic := result#>'{semantic,report,result}';
    IF (binding->>'execution') IS DISTINCT FROM replace(j.execution_id::text,'-','')
       OR (binding->>'job') IS DISTINCT FROM replace(job::text,'-','')
       OR (binding->'generation') IS DISTINCT FROM to_jsonb(j.execution_generation)
       OR (binding->>'purpose') IS DISTINCT FROM 'original'
       OR (binding->>'manifest_sha256') IS DISTINCT FROM j.manifest_sha256
       OR (binding->>'runtime_sha256') IS DISTINCT FROM j.runtime_sha256
       OR (binding->>'verifier_rootfs') IS DISTINCT FROM j.verifier_sha256
       OR (result->'worker') IS DISTINCT FROM j.worker_receipt
       OR (result#>'{worker,collected}') IS DISTINCT FROM 'true'::jsonb
       OR (result#>>'{worker,cleanup}') IS DISTINCT FROM 'confirmed'
       OR (result#>'{worker,runtime_client_exit_code}') IS DISTINCT FROM '0'::jsonb
       OR (result#>>'{worker,unit_result}') IS DISTINCT FROM 'success'
       OR (result#>'{semantic,cleanup_confirmed}') IS DISTINCT FROM 'true'::jsonb
       OR (result#>>'{semantic,rootfs_sha256}') IS DISTINCT FROM j.verifier_sha256
       OR (result#>>'{semantic,report,status}') IS DISTINCT FROM 'processed'
       OR (result#>>'{semantic,report,version}') IS DISTINCT FROM 'proofflow-verifier-v1'
       OR (semantic->>'operation') IS DISTINCT FROM 'verify'
       OR (semantic->>'comparison') IS NULL OR (semantic->>'comparison') NOT IN ('match','mismatch')
       OR jsonb_typeof(semantic->'blocking_occurrences') IS DISTINCT FROM 'number'
       OR (semantic->>'blocking_occurrences') !~ '^(0|[1-9][0-9]{0,4})$'
       OR (semantic->>'blocking_occurrences')::integer>10000 THEN
        RAISE EXCEPTION 'ORIGINAL_REPORT_BINDING_MISMATCH';
    END IF;
    FOR a IN SELECT kind,sha256 FROM pf_product.assets WHERE workspace_id=workspace
             AND id IN (j.pipeline_id,j.transactions_id,j.customers_id,j.contract_id)
    LOOP
        IF (binding->>(CASE a.kind WHEN 'contract' THEN 'contract_raw_sha256'
                                   ELSE a.kind||'_sha256' END)) IS DISTINCT FROM a.sha256 THEN
            RAISE EXCEPTION 'ORIGINAL_SOURCE_HASH_MISMATCH';
        END IF;
        IF a.kind IN ('transactions','customers')
           AND (semantic->>(a.kind||'_sha256')) IS DISTINCT FROM a.sha256 THEN
            RAISE EXCEPTION 'ORIGINAL_SOURCE_HASH_MISMATCH';
        END IF;
    END LOOP;
    IF (semantic->>'contract_sha256') IS NULL
       OR (semantic->>'contract_sha256') IS DISTINCT FROM (binding->>'contract_sha256') THEN
        RAISE EXCEPTION 'ORIGINAL_CONTRACT_HASH_MISMATCH';
    END IF;
    IF jsonb_typeof(j.worker_receipt->'files') IS DISTINCT FROM 'array'
       OR jsonb_typeof(semantic->'output_hashes') IS DISTINCT FROM 'object'
       OR jsonb_typeof(semantic->'findings') IS DISTINCT FROM 'array'
       OR jsonb_typeof(semantic->'finding_count') IS DISTINCT FROM 'number'
       OR (semantic->>'finding_count') !~ '^(0|[1-9][0-9]{0,5})$' THEN
        RAISE EXCEPTION 'ORIGINAL_OUTPUT_BINDING_MISMATCH';
    END IF;
    SELECT count(*),count(DISTINCT f->>'name'),jsonb_object_agg(f->>'name',f->'sha256')
        INTO files,distinct_names,hashes FROM jsonb_array_elements(j.worker_receipt->'files') f;
    IF files NOT BETWEEN 2 AND 3 OR files<>distinct_names OR hashes IS DISTINCT FROM semantic->'output_hashes'
       OR NOT (hashes ?& ARRAY['ledger.jsonl','unresolved.jsonl'])
       OR EXISTS(SELECT 1 FROM jsonb_object_keys(hashes) k WHERE k NOT IN
                 ('ledger.jsonl','unresolved.jsonl','rollups.jsonl'))
       OR (semantic->>'comparison'='match' AND ((semantic->>'finding_count')::integer<>0
                                              OR jsonb_array_length(semantic->'findings')<>0))
       OR (semantic->>'comparison'='mismatch' AND ((semantic->>'finding_count')::integer<1
                                                 OR jsonb_array_length(semantic->'findings')<1)) THEN
        RAISE EXCEPTION 'ORIGINAL_OUTPUT_BINDING_MISMATCH';
    END IF;
    disposition := CASE WHEN semantic->>'comparison'='mismatch' THEN 'mismatch'
        WHEN (semantic->>'blocking_occurrences')::integer>0 THEN 'held' ELSE 'match' END;
    UPDATE pf_product.jobs SET state='NEEDS_REVIEW',outcome=disposition,report=result,
        lease_owner=NULL,lease_until=NULL WHERE workspace_id=workspace AND id=job;
    PERFORM pf_product.job_event(workspace,job,'original_comparison_recorded');
END;
$$;

REVOKE ALL ON ALL TABLES IN SCHEMA pf_product FROM PUBLIC;
REVOKE ALL ON ALL FUNCTIONS IN SCHEMA pf_product FROM PUBLIC;
RESET ROLE;
GRANT USAGE ON SCHEMA pf_product TO pf_product_dispatcher;
GRANT CONNECT ON DATABASE proofflow_product TO pf_product_dispatcher;
GRANT EXECUTE ON FUNCTION pf_product.configure_execution(text,text,boolean) TO pf_product_provisioner;
GRANT EXECUTE ON FUNCTION pf_product.approve_contract(uuid,text,text,uuid,text),
    pf_product.revoke_contract(uuid,text,text,uuid),
    pf_product.enqueue_original(uuid,text,text,uuid,uuid,uuid,uuid,uuid,uuid),
    pf_product.get_job(uuid,text,uuid),pf_product.cancel_job(uuid,text,text,uuid) TO pf_product_api;
GRANT EXECUTE ON FUNCTION pf_product.claim_original(uuid),
    pf_product.heartbeat_original(uuid,uuid,uuid,integer),
    pf_product.dispatch_assets(uuid,uuid,uuid,integer),
    pf_product.begin_original(uuid,uuid,uuid,integer,uuid,text),
    pf_product.reject_original_input(uuid,uuid,uuid,integer),
    pf_product.original_collected(uuid,uuid,uuid,integer,uuid,jsonb),
    pf_product.finish_original(uuid,uuid,uuid,integer,jsonb),
    pf_product.fail_original(uuid,uuid,uuid,integer,jsonb) TO pf_product_dispatcher;
COMMIT;

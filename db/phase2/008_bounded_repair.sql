-- Additive private repair queue. Passing produces reviewable bytes, never activation.
BEGIN;
SET LOCAL ROLE pf_product_owner;
CREATE TABLE pf_product.repairs (
    workspace_id uuid NOT NULL, id uuid NOT NULL, parent_id uuid NOT NULL,
    idempotency_key uuid NOT NULL, policy_epoch bigint NOT NULL,
    state text NOT NULL DEFAULT 'QUEUED' CHECK(state IN
        ('QUEUED','RUNNING','RECONCILING','AWAITING_APPROVAL','NEEDS_REVIEW','FAILED_INFRA','CANCELLED')),
    outcome text, created_at timestamptz NOT NULL DEFAULT clock_timestamp(),
    deadline timestamptz, generation integer NOT NULL DEFAULT 0,
    lease_owner uuid, lease_until timestamptz, cancel_requested boolean NOT NULL DEFAULT false,
    calls integer NOT NULL DEFAULT 0 CHECK(calls BETWEEN 0 AND 3),
    reserved_micro bigint NOT NULL DEFAULT 0 CHECK(reserved_micro BETWEEN 0 AND 500000),
    input_reserved integer NOT NULL DEFAULT 0 CHECK(input_reserved BETWEEN 0 AND 120000),
    output_reserved integer NOT NULL DEFAULT 0 CHECK(output_reserved BETWEEN 0 AND 32000),
    execution_generation integer NOT NULL DEFAULT 0 CHECK(execution_generation BETWEEN 0 AND 9),
    PRIMARY KEY(workspace_id,id), UNIQUE(workspace_id,idempotency_key),
    FOREIGN KEY(workspace_id,parent_id) REFERENCES pf_product.jobs(workspace_id,id)
);
CREATE TABLE pf_product.repair_allocation (singleton boolean PRIMARY KEY CHECK(singleton),
    reserved_micro bigint NOT NULL CHECK(reserved_micro BETWEEN 0 AND 5000000));
INSERT INTO pf_product.repair_allocation VALUES(true,0);
CREATE TABLE pf_product.repair_calls (
    workspace_id uuid NOT NULL, repair_id uuid NOT NULL, ordinal integer NOT NULL CHECK(ordinal BETWEEN 1 AND 3),
    request_id uuid NOT NULL UNIQUE, request_sha256 text NOT NULL CHECK(request_sha256 ~ '^[a-f0-9]{64}$'),
    payload bytea NOT NULL CHECK(octet_length(payload) BETWEEN 1 AND 102400),
    quote bytea NOT NULL CHECK(octet_length(quote) BETWEEN 1 AND 4096),
    reserved_micro bigint NOT NULL CHECK(reserved_micro BETWEEN 1 AND 500000),
    outcome text CHECK(outcome IN ('PARSED_RESPONSE','OUTCOME_UNKNOWN')),
    response bytea CHECK(octet_length(response)<=262144), http_status integer,
    elapsed_ms integer CHECK(elapsed_ms>=0), proposal jsonb CHECK(octet_length(proposal::text)<=65536),
    PRIMARY KEY(workspace_id,repair_id,ordinal),
    FOREIGN KEY(workspace_id,repair_id) REFERENCES pf_product.repairs(workspace_id,id)
);
CREATE TABLE pf_product.repair_executions (
    workspace_id uuid NOT NULL, repair_id uuid NOT NULL, generation integer NOT NULL,
    attempt integer NOT NULL, execution_id uuid NOT NULL UNIQUE,
    purpose text NOT NULL CHECK(purpose IN ('candidate','canary_ownership','canary_quarantine')),
    intent jsonb NOT NULL CHECK(octet_length(intent::text)<=4096),
    result jsonb CHECK(octet_length(result::text)<=131072),
    PRIMARY KEY(workspace_id,repair_id,generation), UNIQUE(workspace_id,repair_id,attempt,purpose),
    FOREIGN KEY(workspace_id,repair_id,attempt) REFERENCES pf_product.repair_calls(workspace_id,repair_id,ordinal)
);

CREATE FUNCTION pf_product.enqueue_repair(w uuid,s text,c text,r uuid,i uuid,parent uuid) RETURNS uuid
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
    IF NOT FOUND OR j.state<>'NEEDS_REVIEW' OR j.outcome<>'mismatch'
       OR j.runtime_sha256<>p.runtime_sha256 OR j.verifier_sha256<>p.verifier_sha256
       OR j.report#>'{semantic,report,result,blocking_occurrences}' IS DISTINCT FROM '0'::jsonb
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

CREATE FUNCTION pf_product.get_repair(w uuid,s text,r uuid) RETURNS jsonb
LANGUAGE plpgsql SECURITY DEFINER SET search_path=pg_catalog,pg_temp AS $$
DECLARE value jsonb;
BEGIN
    PERFORM pf_product.authorize(w,s,NULL,false);
    SELECT jsonb_build_object('id',id,'parent_id',parent_id,'state',state,'outcome',outcome,
        'calls',calls,'reserved_micro',reserved_micro,'created_at',created_at,'deadline',deadline,
        'attempts',COALESCE((SELECT jsonb_agg(jsonb_build_object('ordinal',ordinal,
            'request_id',request_id,'outcome',outcome,'proposal',proposal) ORDER BY ordinal)
            FROM pf_product.repair_calls WHERE workspace_id=w AND repair_id=r),'[]'::jsonb))
        INTO value FROM pf_product.repairs WHERE workspace_id=w AND id=r;
    RETURN value;
END; $$;

CREATE FUNCTION pf_product.cancel_repair(w uuid,s text,c text,r uuid) RETURNS boolean
LANGUAGE plpgsql SECURITY DEFINER SET search_path=pg_catalog,pg_temp AS $$
BEGIN
    PERFORM pf_product.authorize(w,s,c,true);
    UPDATE pf_product.repairs SET cancel_requested=true,
        state=CASE WHEN state='QUEUED' THEN 'CANCELLED' ELSE state END
        WHERE workspace_id=w AND id=r AND state IN ('QUEUED','RUNNING','RECONCILING');
    RETURN FOUND;
END; $$;

-- Both claimers share the existing single-worker lock. Uncertain repair leases
-- block originals until reconciliation, including when their lease has expired.
ALTER FUNCTION pf_product.claim_original(uuid) RENAME TO claim_original_without_repair;
REVOKE EXECUTE ON FUNCTION pf_product.claim_original_without_repair(uuid) FROM pf_product_dispatcher;
CREATE FUNCTION pf_product.claim_original(controller uuid) RETURNS jsonb
LANGUAGE plpgsql SECURITY DEFINER SET search_path=pg_catalog,pg_temp AS $$
BEGIN
    PERFORM pf_product.require_transaction();
    PERFORM pg_advisory_xact_lock(604061,2);
    IF EXISTS(SELECT 1 FROM pf_product.repairs WHERE state IN ('RUNNING','RECONCILING')) THEN
        RETURN NULL; END IF;
    RETURN pf_product.claim_original_without_repair(controller);
END; $$;

CREATE FUNCTION pf_product.claim_repair(controller uuid) RETURNS jsonb
LANGUAGE plpgsql SECURITY DEFINER SET search_path=pg_catalog,pg_temp AS $$
DECLARE r pf_product.repairs%ROWTYPE; w pf_product.workspaces%ROWTYPE;
    p pf_product.execution_policy%ROWTYPE; j pf_product.jobs%ROWTYPE; invalid boolean;
BEGIN
    PERFORM pf_product.require_transaction();
    IF controller IS NULL THEN RAISE EXCEPTION 'INVALID_CONTROLLER'; END IF;
    PERFORM pg_advisory_xact_lock(604061,2);
    SELECT * INTO p FROM pf_product.execution_policy WHERE singleton FOR SHARE;
    IF NOT FOUND OR EXISTS(SELECT 1 FROM pf_product.jobs WHERE state IN
        ('BASELINE_RUNNING','BASELINE_VERIFYING','RECONCILING'))
        OR EXISTS(SELECT 1 FROM pf_product.repairs WHERE state IN ('RUNNING','RECONCILING')
                  AND lease_until>clock_timestamp()) THEN RETURN NULL; END IF;
    FOR w IN SELECT * FROM pf_product.workspaces x WHERE EXISTS(
        SELECT 1 FROM pf_product.repairs y WHERE y.workspace_id=x.id AND
            y.state IN ('QUEUED','RUNNING','RECONCILING')) ORDER BY EXISTS(SELECT 1 FROM pf_product.repairs z
            WHERE z.workspace_id=x.id AND z.state IN ('RUNNING','RECONCILING')) DESC,
            x.created_at FOR UPDATE SKIP LOCKED
    LOOP
        SELECT * INTO r FROM pf_product.repairs WHERE workspace_id=w.id AND state IN
            ('QUEUED','RUNNING','RECONCILING') ORDER BY (state<>'QUEUED') DESC,created_at
            FOR UPDATE SKIP LOCKED LIMIT 1;
        IF NOT FOUND THEN CONTINUE; END IF;
        IF r.generation>=5 THEN RETURN NULL; END IF;
        SELECT * INTO j FROM pf_product.jobs WHERE workspace_id=w.id AND id=r.parent_id;
        invalid := NOT p.enabled OR r.policy_epoch<>p.epoch OR r.cancel_requested
            OR w.revoked_at IS NOT NULL OR w.expires_at<=clock_timestamp()
            OR NOT EXISTS(SELECT 1 FROM pf_product.contract_approvals WHERE workspace_id=w.id
                          AND asset_id=j.contract_id AND revoked_at IS NULL);
        IF invalid AND r.state='QUEUED' THEN
            UPDATE pf_product.repairs SET state='CANCELLED',outcome='authority_revoked'
                WHERE workspace_id=w.id AND id=r.id;
            CONTINUE;
        END IF;
        UPDATE pf_product.repairs SET generation=generation+1,lease_owner=controller,
            lease_until=clock_timestamp()+interval '45 seconds',
            deadline=COALESCE(deadline,clock_timestamp()+interval '300 seconds'),
            state=CASE WHEN r.state='QUEUED' THEN 'RUNNING' ELSE 'RECONCILING' END,
            cancel_requested=invalid WHERE workspace_id=w.id AND id=r.id RETURNING * INTO r;
        RETURN to_jsonb(r)||jsonb_build_object('parent',to_jsonb(j),'executions',COALESCE(
            (SELECT jsonb_agg(to_jsonb(e) ORDER BY generation) FROM pf_product.repair_executions e
             WHERE workspace_id=w.id AND repair_id=r.id),'[]'::jsonb));
    END LOOP;
    RETURN NULL;
END; $$;

CREATE FUNCTION pf_product.guard_repair(w uuid,r uuid,o uuid,g integer,cleanup boolean)
RETURNS pf_product.repairs LANGUAGE plpgsql SECURITY DEFINER SET search_path=pg_catalog,pg_temp AS $$
DECLARE value pf_product.repairs%ROWTYPE; p pf_product.execution_policy%ROWTYPE;
    space pf_product.workspaces%ROWTYPE;
BEGIN
    PERFORM pf_product.require_transaction();
    PERFORM pg_advisory_xact_lock(604061,2);
    SELECT * INTO p FROM pf_product.execution_policy WHERE singleton FOR SHARE;
    SELECT * INTO space FROM pf_product.workspaces WHERE id=w FOR UPDATE;
    SELECT * INTO value FROM pf_product.repairs WHERE workspace_id=w AND id=r FOR UPDATE;
    IF NOT FOUND OR cleanup IS NULL OR value.lease_owner IS DISTINCT FROM o
        OR value.generation IS DISTINCT FROM g OR value.lease_until IS NULL
        OR value.lease_until<=clock_timestamp() OR value.state NOT IN ('RUNNING','RECONCILING') THEN
        RAISE EXCEPTION 'STALE_JOB_LEASE'; END IF;
    IF NOT cleanup AND (value.state<>'RUNNING' OR value.cancel_requested
        OR NOT p.enabled OR value.policy_epoch<>p.epoch OR value.deadline<=clock_timestamp()
        OR space.revoked_at IS NOT NULL OR space.expires_at<=clock_timestamp()
        OR NOT EXISTS(SELECT 1 FROM pf_product.jobs j JOIN pf_product.contract_approvals a
            ON a.workspace_id=j.workspace_id AND a.asset_id=j.contract_id
            WHERE j.workspace_id=w AND j.id=value.parent_id AND a.revoked_at IS NULL)) THEN
        RAISE EXCEPTION 'JOB_AUTHORITY_REVOKED'; END IF;
    RETURN value;
END; $$;

CREATE FUNCTION pf_product.heartbeat_repair(w uuid,r uuid,o uuid,g integer,cleanup boolean)
RETURNS void LANGUAGE plpgsql SECURITY DEFINER SET search_path=pg_catalog,pg_temp AS $$
BEGIN
    PERFORM pf_product.guard_repair(w,r,o,g,cleanup);
    UPDATE pf_product.repairs SET lease_until=clock_timestamp()+interval '45 seconds'
        WHERE workspace_id=w AND id=r;
END; $$;

CREATE FUNCTION pf_product.repair_assets(w uuid,r uuid,o uuid,g integer) RETURNS jsonb
LANGUAGE plpgsql SECURITY DEFINER SET search_path=pg_catalog,pg_temp AS $$
DECLARE value pf_product.repairs%ROWTYPE; j pf_product.jobs%ROWTYPE; result jsonb;
BEGIN
    value:=pf_product.guard_repair(w,r,o,g,false);
    SELECT * INTO j FROM pf_product.jobs WHERE workspace_id=w AND id=value.parent_id;
    SELECT jsonb_agg(jsonb_build_object('kind',kind,'sha256',sha256,'bytes',byte_size))
        INTO result FROM pf_product.assets WHERE workspace_id=w AND
        id IN (j.pipeline_id,j.transactions_id,j.customers_id,j.contract_id);
    RETURN result;
END; $$;

CREATE FUNCTION pf_product.prepare_repair_call(w uuid,r uuid,o uuid,g integer,request uuid,
    digest text,payload bytea,quote bytea,amount bigint) RETURNS boolean
LANGUAGE plpgsql SECURITY DEFINER SET search_path=pg_catalog,pg_temp AS $$
DECLARE value pf_product.repairs%ROWTYPE;
BEGIN
    value:=pf_product.guard_repair(w,r,o,g,false);
    IF EXISTS(SELECT 1 FROM pf_product.repair_calls WHERE request_id=request) THEN
        RAISE EXCEPTION 'REPAIR_CALL_ALREADY_PREPARED'; END IF;
    IF value.calls>=3 OR amount IS NULL OR amount<1 OR value.reserved_micro+amount>500000
        OR value.input_reserved+20480>120000 OR value.output_reserved+8192>32000
        OR value.deadline<clock_timestamp()+interval '65 seconds' THEN
        RAISE EXCEPTION 'REPAIR_BUDGET_EXHAUSTED'; END IF;
    IF EXISTS(SELECT 1 FROM pf_product.repair_calls WHERE workspace_id=w AND repair_id=r
              AND (outcome IS DISTINCT FROM 'PARSED_RESPONSE' OR proposal IS NULL))
        OR EXISTS(SELECT 1 FROM pf_product.repair_executions WHERE workspace_id=w AND repair_id=r
                  AND result IS NULL) THEN RAISE EXCEPTION 'REPAIR_OUTCOME_UNCERTAIN'; END IF;
    PERFORM pg_advisory_xact_lock(604061,4);
    IF (SELECT reserved_micro FROM pf_product.repair_allocation WHERE singleton)+amount>5000000 THEN
        RAISE EXCEPTION 'REPAIR_DEVELOPMENT_ALLOCATION'; END IF;
    UPDATE pf_product.repair_allocation SET reserved_micro=reserved_micro+amount WHERE singleton;
    INSERT INTO pf_product.repair_calls(workspace_id,repair_id,ordinal,request_id,request_sha256,
        payload,quote,reserved_micro) VALUES(w,r,value.calls+1,request,digest,payload,quote,amount);
    UPDATE pf_product.repairs SET calls=calls+1,reserved_micro=reserved_micro+amount,
        input_reserved=input_reserved+20480,output_reserved=output_reserved+8192
        WHERE workspace_id=w AND id=r;
    RETURN true;
END; $$;

CREATE FUNCTION pf_product.record_repair_call(w uuid,r uuid,o uuid,g integer,request uuid,
    digest text,outcome text,response bytea,status integer,elapsed integer) RETURNS boolean
LANGUAGE plpgsql SECURITY DEFINER SET search_path=pg_catalog,pg_temp AS $$
BEGIN
    PERFORM pf_product.guard_repair(w,r,o,g,true);
    UPDATE pf_product.repair_calls c SET outcome=record_repair_call.outcome,
        response=record_repair_call.response,http_status=status,elapsed_ms=elapsed
        WHERE workspace_id=w AND repair_id=r AND request_id=request AND request_sha256=digest
        AND c.outcome IS NULL;
    IF NOT FOUND THEN RAISE EXCEPTION 'REPAIR_RECEIPT_CONFLICT'; END IF;
    RETURN true;
END; $$;

CREATE FUNCTION pf_product.repair_proposal(w uuid,r uuid,o uuid,g integer,attempt integer,value jsonb)
RETURNS void LANGUAGE plpgsql SECURITY DEFINER SET search_path=pg_catalog,pg_temp AS $$
BEGIN
    PERFORM pf_product.guard_repair(w,r,o,g,false);
    IF value IS NULL OR jsonb_typeof(value)<>'object' OR value->>'kind' NOT IN
        ('propose_patch','needs_clarification','rejected') THEN RAISE EXCEPTION 'REPAIR_PROPOSAL_INVALID'; END IF;
    UPDATE pf_product.repair_calls SET proposal=value WHERE workspace_id=w AND repair_id=r
        AND ordinal=attempt AND outcome='PARSED_RESPONSE' AND proposal IS NULL;
    IF NOT FOUND THEN RAISE EXCEPTION 'REPAIR_RECEIPT_CONFLICT'; END IF;
END; $$;

CREATE FUNCTION pf_product.begin_repair_execution(w uuid,r uuid,o uuid,g integer,attempt integer,
    execution uuid,intent jsonb) RETURNS void
LANGUAGE plpgsql SECURITY DEFINER SET search_path=pg_catalog,pg_temp AS $$
DECLARE value pf_product.repairs%ROWTYPE; source text; j pf_product.jobs%ROWTYPE; a record;
BEGIN
    value:=pf_product.guard_repair(w,r,o,g,false);
    SELECT proposal->>'candidate_source' INTO source FROM pf_product.repair_calls
        WHERE workspace_id=w AND repair_id=r AND ordinal=attempt AND proposal->>'kind'='propose_patch';
    SELECT * INTO j FROM pf_product.jobs WHERE workspace_id=w AND id=value.parent_id;
    IF attempt IS DISTINCT FROM value.calls
        OR intent IS NULL OR jsonb_typeof(intent)<>'object'
        OR intent->>'runtime_sha256' IS DISTINCT FROM j.runtime_sha256
        OR intent->>'verifier_rootfs' IS DISTINCT FROM j.verifier_sha256
        OR intent->>'manifest_sha256' IS NULL OR intent->>'manifest_sha256' !~ '^[a-f0-9]{64}$'
        OR source IS NULL OR octet_length(source) NOT BETWEEN 1 AND 16384
        OR value.execution_generation>=9 OR value.deadline<clock_timestamp()+interval '120 seconds'
        OR EXISTS(SELECT 1 FROM pf_product.repair_executions WHERE workspace_id=w AND repair_id=r
                  AND result IS NULL)
        OR intent->>'job' IS DISTINCT FROM replace(r::text,'-','')
        OR intent->>'execution' IS DISTINCT FROM replace(execution::text,'-','')
        OR intent->'generation' IS DISTINCT FROM to_jsonb(value.execution_generation+1)
        OR intent->>'pipeline_sha256' IS DISTINCT FROM encode(sha256(convert_to(source,'UTF8')),'hex') THEN
        RAISE EXCEPTION 'EXECUTION_INTENT_CONFLICT'; END IF;
    FOR a IN SELECT kind,sha256 FROM pf_product.assets WHERE workspace_id=w AND
        (id=j.contract_id OR (intent->>'purpose'='candidate' AND id IN (j.transactions_id,j.customers_id)))
    LOOP
        IF intent->>(CASE a.kind WHEN 'contract' THEN 'contract_raw_sha256' ELSE a.kind||'_sha256' END)
            IS DISTINCT FROM a.sha256 THEN RAISE EXCEPTION 'EXECUTION_INTENT_CONFLICT'; END IF;
    END LOOP;
    INSERT INTO pf_product.repair_executions(workspace_id,repair_id,generation,attempt,execution_id,purpose,intent)
        VALUES(w,r,value.execution_generation+1,attempt,execution,intent->>'purpose',intent);
    UPDATE pf_product.repairs SET execution_generation=execution_generation+1 WHERE workspace_id=w AND id=r;
END; $$;

CREATE FUNCTION pf_product.record_repair_execution(w uuid,r uuid,o uuid,g integer,execution uuid,value jsonb)
RETURNS void LANGUAGE plpgsql SECURITY DEFINER SET search_path=pg_catalog,pg_temp AS $$
DECLARE e pf_product.repair_executions%ROWTYPE; semantic jsonb; hashes jsonb; files integer;
BEGIN
    PERFORM pf_product.guard_repair(w,r,o,g,true);
    SELECT * INTO e FROM pf_product.repair_executions WHERE workspace_id=w AND repair_id=r
        AND execution_id=execution FOR UPDATE;
    IF NOT FOUND OR e.result IS NOT NULL OR value->'intent' IS DISTINCT FROM e.intent
        OR value#>>'{worker,execution}' IS DISTINCT FROM replace(execution::text,'-','')
        OR value#>>'{worker,job}' IS DISTINCT FROM replace(r::text,'-','')
        OR value#>'{worker,generation}' IS DISTINCT FROM to_jsonb(e.generation)
        OR value#>>'{worker,manifest}' IS DISTINCT FROM e.intent->>'manifest_sha256'
        OR value#>>'{worker,cleanup}' IS DISTINCT FROM 'confirmed' THEN
        RAISE EXCEPTION 'CLEANUP_REQUIRED'; END IF;
    IF value->'semantic' IS NOT NULL AND value->'semantic'<>'null'::jsonb THEN
        IF value#>>'{semantic,rootfs_sha256}' IS DISTINCT FROM e.intent->>'verifier_rootfs'
            OR value#>'{semantic,cleanup_confirmed}' IS DISTINCT FROM 'true'::jsonb
            OR value#>>'{semantic,report,version}' IS DISTINCT FROM 'proofflow-verifier-v1' THEN
            RAISE EXCEPTION 'REPAIR_PROOF_INCOMPLETE'; END IF;
        IF value#>>'{semantic,report,status}'='processed' THEN
            semantic:=value#>'{semantic,report,result}';
            SELECT count(*),jsonb_object_agg(f->>'name',f->'sha256') INTO files,hashes
                FROM jsonb_array_elements(value#>'{worker,files}') f;
            IF semantic->>'operation' IS DISTINCT FROM 'verify'
                OR semantic->>'contract_sha256' IS DISTINCT FROM e.intent->>'contract_sha256'
                OR semantic->>'transactions_sha256' IS DISTINCT FROM e.intent->>'transactions_sha256'
                OR semantic->>'customers_sha256' IS DISTINCT FROM e.intent->>'customers_sha256'
                OR files NOT BETWEEN 2 AND 3 OR hashes IS DISTINCT FROM semantic->'output_hashes'
                OR NOT hashes ?& ARRAY['ledger.jsonl','unresolved.jsonl']
                OR (SELECT count(*) FROM jsonb_object_keys(hashes))<>files
                OR EXISTS(SELECT 1 FROM jsonb_object_keys(hashes) k WHERE k NOT IN
                    ('ledger.jsonl','unresolved.jsonl','rollups.jsonl'))
                OR (semantic->>'comparison'='match' AND
                    (semantic->'finding_count' IS DISTINCT FROM '0'::jsonb OR
                     semantic->'findings' IS DISTINCT FROM '[]'::jsonb)) THEN
                RAISE EXCEPTION 'REPAIR_PROOF_INCOMPLETE'; END IF;
        END IF;
    END IF;
    UPDATE pf_product.repair_executions SET result=value WHERE workspace_id=w AND repair_id=r
        AND execution_id=execution;
END; $$;

CREATE FUNCTION pf_product.finish_repair(w uuid,r uuid,o uuid,g integer,code text) RETURNS void
LANGUAGE plpgsql SECURITY DEFINER SET search_path=pg_catalog,pg_temp AS $$
DECLARE value pf_product.repairs%ROWTYPE; count_pass integer;
BEGIN
    value:=pf_product.guard_repair(w,r,o,g,code IS DISTINCT FROM 'candidate_passed');
    IF code IS NULL OR code NOT IN ('candidate_passed','needs_clarification','attempts_exhausted',
        'provider_unavailable','input_held','context_limit','budget_exhausted','infrastructure_failed',
        'cancelled','deadline_exceeded','usage_unknown') THEN RAISE EXCEPTION 'REPAIR_OUTCOME_INVALID'; END IF;
    IF EXISTS(SELECT 1 FROM pf_product.repair_executions WHERE workspace_id=w AND repair_id=r
              AND result IS NULL) THEN RAISE EXCEPTION 'CLEANUP_REQUIRED'; END IF;
    IF code='candidate_passed' THEN
        SELECT count(*) INTO count_pass FROM pf_product.repair_executions WHERE workspace_id=w
            AND repair_id=r AND attempt=value.calls AND result#>>'{semantic,report,result,comparison}'='match'
            AND result#>'{semantic,cleanup_confirmed}'='true'::jsonb
            AND result#>>'{semantic,report,status}'='processed'
            AND result#>'{worker,runtime_client_exit_code}'='0'::jsonb
            AND result#>'{worker,collected}'='true'::jsonb
            AND result#>>'{worker,unit_result}'='success'
            AND (purpose<>'candidate' OR result#>'{semantic,report,result,blocking_occurrences}'='0'::jsonb);
        IF count_pass<>3 THEN RAISE EXCEPTION 'REPAIR_PROOF_INCOMPLETE'; END IF;
    END IF;
    UPDATE pf_product.repairs SET state=CASE WHEN code='candidate_passed' THEN 'AWAITING_APPROVAL'
        WHEN code='cancelled' THEN 'CANCELLED' WHEN code='infrastructure_failed' THEN 'FAILED_INFRA'
        ELSE 'NEEDS_REVIEW' END,outcome=code,lease_owner=NULL,lease_until=NULL WHERE workspace_id=w AND id=r;
END; $$;

CREATE FUNCTION pf_product.export_repair(w uuid,s text,r uuid) RETURNS jsonb
LANGUAGE plpgsql SECURITY DEFINER SET search_path=pg_catalog,pg_temp AS $$
DECLARE result jsonb;
BEGIN
    PERFORM pf_product.authorize(w,s,NULL,false);
    SELECT jsonb_build_object('candidate_source',c.proposal->>'candidate_source',
        'original_sha256',a.sha256) INTO result FROM pf_product.repairs x
        JOIN pf_product.jobs j ON j.workspace_id=x.workspace_id AND j.id=x.parent_id
        JOIN pf_product.assets a ON a.workspace_id=j.workspace_id AND a.id=j.pipeline_id
        JOIN pf_product.contract_approvals approval ON approval.workspace_id=j.workspace_id
            AND approval.asset_id=j.contract_id AND approval.revoked_at IS NULL
        JOIN pf_product.repair_calls c ON c.workspace_id=x.workspace_id AND c.repair_id=x.id
            AND c.ordinal=x.calls AND c.proposal->>'kind'='propose_patch'
        WHERE x.workspace_id=w AND x.id=r AND x.state='AWAITING_APPROVAL'
            AND x.outcome='candidate_passed' AND NOT x.cancel_requested;
    RETURN result;
END; $$;

REVOKE ALL ON ALL TABLES IN SCHEMA pf_product FROM PUBLIC;
REVOKE ALL ON ALL FUNCTIONS IN SCHEMA pf_product FROM PUBLIC;
RESET ROLE;
GRANT EXECUTE ON FUNCTION pf_product.enqueue_repair(uuid,text,text,uuid,uuid,uuid),
    pf_product.get_repair(uuid,text,uuid),pf_product.cancel_repair(uuid,text,text,uuid),
    pf_product.export_repair(uuid,text,uuid) TO pf_product_api;
GRANT EXECUTE ON FUNCTION pf_product.claim_original(uuid),pf_product.claim_repair(uuid),
    pf_product.heartbeat_repair(uuid,uuid,uuid,integer,boolean),pf_product.repair_assets(uuid,uuid,uuid,integer),
    pf_product.prepare_repair_call(uuid,uuid,uuid,integer,uuid,text,bytea,bytea,bigint),
    pf_product.record_repair_call(uuid,uuid,uuid,integer,uuid,text,text,bytea,integer,integer),
    pf_product.repair_proposal(uuid,uuid,uuid,integer,integer,jsonb),
    pf_product.begin_repair_execution(uuid,uuid,uuid,integer,integer,uuid,jsonb),
    pf_product.record_repair_execution(uuid,uuid,uuid,integer,uuid,jsonb),
    pf_product.finish_repair(uuid,uuid,uuid,integer,text) TO pf_product_dispatcher;
COMMIT;

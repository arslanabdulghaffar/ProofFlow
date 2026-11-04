-- Already-correct sources and export evidence remain distinct from AI repair.
BEGIN;
SET LOCAL ROLE pf_product_owner;
ALTER TABLE pf_product.repairs ADD COLUMN event_sequence integer NOT NULL DEFAULT 0 CHECK(event_sequence BETWEEN 0 AND 64);
CREATE TABLE pf_product.repair_events (
    workspace_id uuid NOT NULL, repair_id uuid NOT NULL, sequence integer NOT NULL,
    occurred_at timestamptz NOT NULL DEFAULT clock_timestamp(), event text NOT NULL,
    PRIMARY KEY(workspace_id,repair_id,sequence),
    FOREIGN KEY(workspace_id,repair_id) REFERENCES pf_product.repairs(workspace_id,id)
);
CREATE FUNCTION pf_product.record_repair_event() RETURNS trigger
LANGUAGE plpgsql SECURITY DEFINER SET search_path=pg_catalog,pg_temp AS $$
DECLARE repair uuid; event_code text; seq integer;
BEGIN
    IF TG_TABLE_NAME='repairs' THEN
        IF TG_OP='UPDATE' AND NEW.state IS NOT DISTINCT FROM OLD.state THEN RETURN NEW; END IF;
        repair:=NEW.id; event_code:='state_'||lower(NEW.state);
    ELSIF TG_TABLE_NAME='repair_calls' THEN
        repair:=NEW.repair_id;
        event_code:=CASE WHEN TG_OP='INSERT' THEN 'provider_request_committed'
            WHEN NEW.proposal IS DISTINCT FROM OLD.proposal THEN 'proposal_recorded'
            ELSE 'provider_response_recorded' END;
    ELSE
        repair:=NEW.repair_id;
        event_code:=CASE WHEN TG_OP='INSERT' THEN 'execution_intent_committed' ELSE 'execution_result_recorded' END;
    END IF;
    UPDATE pf_product.repairs SET event_sequence=event_sequence+1 WHERE workspace_id=NEW.workspace_id AND id=repair
        RETURNING event_sequence INTO seq;
    INSERT INTO pf_product.repair_events(workspace_id,repair_id,sequence,event)
        VALUES(NEW.workspace_id,repair,seq,event_code);
    RETURN NEW;
END; $$;
CREATE TRIGGER repair_state_events AFTER INSERT OR UPDATE OF state ON pf_product.repairs
    FOR EACH ROW EXECUTE FUNCTION pf_product.record_repair_event();
CREATE TRIGGER repair_call_events AFTER INSERT OR UPDATE OF outcome,proposal ON pf_product.repair_calls
    FOR EACH ROW EXECUTE FUNCTION pf_product.record_repair_event();
CREATE TRIGGER repair_execution_events AFTER INSERT OR UPDATE OF result ON pf_product.repair_executions
    FOR EACH ROW EXECUTE FUNCTION pf_product.record_repair_event();

CREATE TABLE pf_product.repair_candidates (
    workspace_id uuid NOT NULL, repair_id uuid NOT NULL, ordinal integer NOT NULL CHECK(ordinal BETWEEN 0 AND 3),
    source text NOT NULL CHECK(octet_length(source) BETWEEN 1 AND 16384),
    kind text NOT NULL CHECK(kind IN ('original','model')),
    PRIMARY KEY(workspace_id,repair_id,ordinal),
    FOREIGN KEY(workspace_id,repair_id) REFERENCES pf_product.repairs(workspace_id,id)
);
INSERT INTO pf_product.repair_candidates SELECT workspace_id,repair_id,ordinal,
    proposal->>'candidate_source','model' FROM pf_product.repair_calls WHERE proposal->>'kind'='propose_patch';
ALTER TABLE pf_product.repair_executions DROP CONSTRAINT repair_executions_workspace_id_repair_id_attempt_fkey;
ALTER TABLE pf_product.repair_executions ADD FOREIGN KEY(workspace_id,repair_id,attempt)
    REFERENCES pf_product.repair_candidates(workspace_id,repair_id,ordinal);


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
    IF NOT FOUND OR j.state<>'NEEDS_REVIEW' OR j.outcome NOT IN ('mismatch','match')
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

CREATE OR REPLACE FUNCTION pf_product.repair_proposal(w uuid,r uuid,o uuid,g integer,attempt integer,value jsonb)
RETURNS void LANGUAGE plpgsql SECURITY DEFINER SET search_path=pg_catalog,pg_temp AS $$
BEGIN
    PERFORM pf_product.guard_repair(w,r,o,g,false);
    IF value IS NULL OR jsonb_typeof(value)<>'object' OR value->>'kind' NOT IN
        ('propose_patch','needs_clarification','rejected') THEN RAISE EXCEPTION 'REPAIR_PROPOSAL_INVALID'; END IF;
    UPDATE pf_product.repair_calls SET proposal=value WHERE workspace_id=w AND repair_id=r
        AND ordinal=attempt AND outcome='PARSED_RESPONSE' AND proposal IS NULL;
    IF NOT FOUND THEN RAISE EXCEPTION 'REPAIR_RECEIPT_CONFLICT'; END IF;
    IF value->>'kind'='propose_patch' THEN
        INSERT INTO pf_product.repair_candidates VALUES(w,r,attempt,value->>'candidate_source','model');
    END IF;
END; $$;

CREATE FUNCTION pf_product.original_repair_candidate(w uuid,r uuid,o uuid,g integer,source bytea)
RETURNS void LANGUAGE plpgsql SECURITY DEFINER SET search_path=pg_catalog,pg_temp AS $$
DECLARE value pf_product.repairs%ROWTYPE;
BEGIN
    value:=pf_product.guard_repair(w,r,o,g,false);
    IF value.calls<>0 OR NOT EXISTS(SELECT 1 FROM pf_product.jobs j JOIN pf_product.assets a
        ON a.workspace_id=j.workspace_id AND a.id=j.pipeline_id WHERE j.workspace_id=w
        AND j.id=value.parent_id AND j.outcome='match' AND a.sha256=encode(sha256(source),'hex')) THEN
        RAISE EXCEPTION 'REPAIR_PARENT_INVALID'; END IF;
    INSERT INTO pf_product.repair_candidates VALUES(w,r,0,convert_from(source,'UTF8'),'original');
END; $$;

CREATE OR REPLACE FUNCTION pf_product.begin_repair_execution(w uuid,r uuid,o uuid,g integer,attempt integer,
    execution uuid,intent jsonb) RETURNS void
LANGUAGE plpgsql SECURITY DEFINER SET search_path=pg_catalog,pg_temp AS $$
DECLARE value pf_product.repairs%ROWTYPE; source text; j pf_product.jobs%ROWTYPE; a record;
BEGIN
    value:=pf_product.guard_repair(w,r,o,g,false);
    SELECT c.source INTO source FROM pf_product.repair_candidates c
        WHERE workspace_id=w AND repair_id=r AND ordinal=attempt;
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

CREATE OR REPLACE FUNCTION pf_product.export_repair(w uuid,s text,r uuid) RETURNS jsonb
LANGUAGE plpgsql SECURITY DEFINER SET search_path=pg_catalog,pg_temp AS $$
DECLARE result jsonb;
BEGIN
    PERFORM pf_product.authorize(w,s,NULL,false);
    SELECT jsonb_build_object('candidate_source',c.source,
        'original_sha256',a.sha256) INTO result FROM pf_product.repairs x
        JOIN pf_product.jobs j ON j.workspace_id=x.workspace_id AND j.id=x.parent_id
        JOIN pf_product.assets a ON a.workspace_id=j.workspace_id AND a.id=j.pipeline_id
        JOIN pf_product.contract_approvals approval ON approval.workspace_id=j.workspace_id
            AND approval.asset_id=j.contract_id AND approval.revoked_at IS NULL
        JOIN pf_product.repair_candidates c ON c.workspace_id=x.workspace_id AND c.repair_id=x.id
            AND c.ordinal=x.calls
        WHERE x.workspace_id=w AND x.id=r AND x.state='AWAITING_APPROVAL'
            AND x.outcome='candidate_passed' AND NOT x.cancel_requested;
    RETURN result;
END; $$;

CREATE OR REPLACE FUNCTION pf_product.get_repair(w uuid,s text,r uuid) RETURNS jsonb
LANGUAGE plpgsql SECURITY DEFINER SET search_path=pg_catalog,pg_temp AS $$
DECLARE value jsonb;
BEGIN
    PERFORM pf_product.authorize(w,s,NULL,false);
    SELECT jsonb_build_object('id',id,'parent_id',parent_id,'mode',CASE WHEN EXISTS(SELECT 1 FROM pf_product.jobs j
            WHERE j.workspace_id=w AND j.id=parent_id AND j.outcome='match') THEN 'original' ELSE 'ai_repair' END,
        'events',COALESCE((SELECT jsonb_agg(jsonb_build_object('sequence',sequence,'occurred_at',occurred_at,
            'event',event) ORDER BY sequence) FROM pf_product.repair_events WHERE workspace_id=w AND repair_id=r),
            '[]'::jsonb),
        'checks',COALESCE((SELECT jsonb_agg(jsonb_build_object('generation',generation,'attempt',attempt,
            'purpose',purpose,'comparison',result#>>'{semantic,report,result,comparison}',
            'cleanup_confirmed',COALESCE(result#>>'{worker,cleanup}'='confirmed',false)) ORDER BY generation)
            FROM pf_product.repair_executions WHERE workspace_id=w AND repair_id=r),'[]'::jsonb),
        'state',state,'outcome',outcome,
        'calls',calls,'reserved_micro',reserved_micro,'created_at',created_at,'deadline',deadline,
        'attempts',COALESCE((SELECT jsonb_agg(jsonb_build_object('ordinal',ordinal,
            'request_id',request_id,'outcome',outcome,'proposal',proposal) ORDER BY ordinal)
            FROM pf_product.repair_calls WHERE workspace_id=w AND repair_id=r),'[]'::jsonb))
        INTO value FROM pf_product.repairs WHERE workspace_id=w AND id=r;
    RETURN value;
END; $$;

CREATE FUNCTION pf_product.repair_bundle(w uuid,s text,r uuid) RETURNS jsonb
LANGUAGE plpgsql SECURITY DEFINER SET search_path=pg_catalog,pg_temp AS $$
DECLARE x pf_product.repairs%ROWTYPE; j pf_product.jobs%ROWTYPE;
BEGIN
    PERFORM pf_product.authorize(w,s,NULL,false);
    SELECT * INTO x FROM pf_product.repairs WHERE workspace_id=w AND id=r;
    IF NOT FOUND OR x.state IN ('QUEUED','RUNNING','RECONCILING') THEN RETURN NULL; END IF;
    SELECT * INTO j FROM pf_product.jobs WHERE workspace_id=w AND id=x.parent_id;
    RETURN jsonb_build_object('repair',pf_product.get_repair(w,s,r),'original',to_jsonb(j),
        'assets',(SELECT jsonb_agg(jsonb_build_object('kind',kind,'sha256',sha256,'bytes',byte_size))
            FROM pf_product.assets WHERE workspace_id=w AND id IN
            (j.pipeline_id,j.transactions_id,j.customers_id,j.contract_id)),
        'candidates',COALESCE((SELECT jsonb_agg(to_jsonb(c) ORDER BY ordinal) FROM pf_product.repair_candidates c
            WHERE workspace_id=w AND repair_id=r),'[]'::jsonb),
        'executions',COALESCE((SELECT jsonb_agg(to_jsonb(e) ORDER BY generation) FROM pf_product.repair_executions e
            WHERE workspace_id=w AND repair_id=r),'[]'::jsonb),
        'calls',COALESCE((SELECT jsonb_agg(jsonb_build_object('ordinal',ordinal,'request_id',request_id,
            'request_sha256',request_sha256,'payload_sha256',encode(sha256(payload),'hex'),
            'quote_sha256',encode(sha256(quote),'hex'),'response_sha256',encode(sha256(response),'hex'),
            'response_base64',CASE WHEN outcome='PARSED_RESPONSE' THEN encode(response,'base64') ELSE NULL END,
            'elapsed_ms',elapsed_ms,'reserved_micro',reserved_micro,'outcome',outcome) ORDER BY ordinal)
            FROM pf_product.repair_calls WHERE workspace_id=w AND repair_id=r),'[]'::jsonb),
        'original_events',(SELECT jsonb_agg(to_jsonb(e) ORDER BY sequence) FROM pf_product.job_events e
            WHERE workspace_id=w AND job_id=j.id));
END; $$;


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

REVOKE ALL ON pf_product.repair_candidates,pf_product.repair_events FROM PUBLIC;
REVOKE ALL ON FUNCTION pf_product.record_repair_event() FROM PUBLIC;
REVOKE ALL ON FUNCTION pf_product.original_repair_candidate(uuid,uuid,uuid,integer,bytea),
    pf_product.repair_bundle(uuid,text,uuid) FROM PUBLIC;
RESET ROLE;
GRANT EXECUTE ON FUNCTION pf_product.original_repair_candidate(uuid,uuid,uuid,integer,bytea)
    TO pf_product_dispatcher;
GRANT EXECUTE ON FUNCTION pf_product.repair_bundle(uuid,text,uuid) TO pf_product_api;
COMMIT;

-- Exact approvals and fresh batches reuse the proven original worker queue.
BEGIN;
SET LOCAL ROLE pf_product_owner;
ALTER TABLE pf_product.execution_policy ADD COLUMN verification_epoch bigint NOT NULL DEFAULT 1;
ALTER TABLE pf_product.repairs ADD COLUMN verification_epoch bigint NOT NULL DEFAULT 1;
CREATE TABLE pf_product.pipelines (
    workspace_id uuid NOT NULL REFERENCES pf_product.workspaces(id), id uuid NOT NULL,
    active_version uuid, revision bigint NOT NULL DEFAULT 0, revocation_epoch bigint NOT NULL DEFAULT 0,
    PRIMARY KEY(workspace_id,id)
);
CREATE TABLE pf_product.versions (
    workspace_id uuid NOT NULL, id uuid NOT NULL, pipeline_id uuid NOT NULL,
    repair_id uuid NOT NULL, code_asset_id uuid NOT NULL, contract_id uuid NOT NULL,
    code_sha256 text NOT NULL, contract_sha256 text NOT NULL, evidence_sha256 text NOT NULL,
    runtime_sha256 text NOT NULL, verifier_sha256 text NOT NULL, verification_epoch bigint NOT NULL,
    created_at timestamptz NOT NULL DEFAULT clock_timestamp(), revoked_at timestamptz,
    PRIMARY KEY(workspace_id,id), UNIQUE(workspace_id,repair_id),
    FOREIGN KEY(workspace_id,pipeline_id) REFERENCES pf_product.pipelines(workspace_id,id),
    FOREIGN KEY(workspace_id,repair_id) REFERENCES pf_product.repairs(workspace_id,id),
    FOREIGN KEY(workspace_id,code_asset_id) REFERENCES pf_product.assets(workspace_id,id),
    FOREIGN KEY(workspace_id,contract_id) REFERENCES pf_product.contract_approvals(workspace_id,asset_id)
);
ALTER TABLE pf_product.pipelines ADD FOREIGN KEY(workspace_id,active_version)
    REFERENCES pf_product.versions(workspace_id,id);
CREATE TABLE pf_product.approval_intents (
    workspace_id uuid NOT NULL, id uuid NOT NULL, version_id uuid NOT NULL,
    actor text NOT NULL, bundle jsonb NOT NULL, digest text NOT NULL,
    created_at timestamptz NOT NULL DEFAULT clock_timestamp(),
    expires_at timestamptz NOT NULL DEFAULT clock_timestamp()+interval '10 minutes', approved_at timestamptz,
    PRIMARY KEY(workspace_id,id),
    FOREIGN KEY(workspace_id,version_id) REFERENCES pf_product.versions(workspace_id,id)
);
CREATE TABLE pf_product.batches (
    workspace_id uuid NOT NULL, id uuid NOT NULL, pipeline_id uuid NOT NULL, version_id uuid NOT NULL,
    created_at timestamptz NOT NULL DEFAULT clock_timestamp(),
    PRIMARY KEY(workspace_id,id),
    FOREIGN KEY(workspace_id,id) REFERENCES pf_product.jobs(workspace_id,id),
    FOREIGN KEY(workspace_id,pipeline_id) REFERENCES pf_product.pipelines(workspace_id,id),
    FOREIGN KEY(workspace_id,version_id) REFERENCES pf_product.versions(workspace_id,id)
);
CREATE TABLE pf_product.version_events (
    sequence bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY, workspace_id uuid NOT NULL,
    version_id uuid NOT NULL, actor text NOT NULL, event text NOT NULL,
    occurred_at timestamptz NOT NULL DEFAULT clock_timestamp(), intent_id uuid,
    FOREIGN KEY(workspace_id,version_id) REFERENCES pf_product.versions(workspace_id,id)
);

CREATE FUNCTION pf_product.pin_repair_policy() RETURNS trigger
LANGUAGE plpgsql SECURITY DEFINER SET search_path=pg_catalog,pg_temp AS $$
BEGIN
    SELECT verification_epoch INTO NEW.verification_epoch FROM pf_product.execution_policy WHERE singleton;
    RETURN NEW;
END; $$;
CREATE TRIGGER pin_repair_policy BEFORE INSERT ON pf_product.repairs
FOR EACH ROW EXECUTE FUNCTION pf_product.pin_repair_policy();

-- Admission generations still change on every call. Semantic policy generations
-- change only on runtime/verifier changes and never become valid again on rollback.
CREATE OR REPLACE FUNCTION pf_product.configure_execution(runtime_digest text, verifier_digest text,
    admission boolean) RETURNS bigint LANGUAGE plpgsql SECURITY DEFINER
SET search_path=pg_catalog,pg_temp AS $$
DECLARE version bigint; old pf_product.execution_policy%ROWTYPE;
BEGIN
    PERFORM pf_product.require_transaction();
    PERFORM pg_advisory_xact_lock(604061,2);
    IF runtime_digest IS NULL OR runtime_digest !~ '^[0-9a-f]{64}$'
       OR verifier_digest IS NULL OR verifier_digest !~ '^[0-9a-f]{64}$' OR admission IS NULL THEN
        RAISE EXCEPTION 'INVALID_EXECUTION_POLICY'; END IF;
    SELECT * INTO old FROM pf_product.execution_policy WHERE singleton FOR UPDATE;
    INSERT INTO pf_product.execution_policy(singleton,epoch,runtime_sha256,verifier_sha256,enabled)
        VALUES(true,1,runtime_digest,verifier_digest,admission)
        ON CONFLICT(singleton) DO UPDATE SET epoch=pf_product.execution_policy.epoch+1,
        verification_epoch=pf_product.execution_policy.verification_epoch+
            CASE WHEN pf_product.execution_policy.runtime_sha256<>EXCLUDED.runtime_sha256
                OR pf_product.execution_policy.verifier_sha256<>EXCLUDED.verifier_sha256 THEN 1 ELSE 0 END,
        runtime_sha256=EXCLUDED.runtime_sha256,verifier_sha256=EXCLUDED.verifier_sha256,
        enabled=EXCLUDED.enabled RETURNING epoch INTO version;
    IF old.runtime_sha256 IS DISTINCT FROM runtime_digest OR old.verifier_sha256 IS DISTINCT FROM verifier_digest THEN
        UPDATE pf_product.pipelines SET active_version=NULL,revision=revision+1,revocation_epoch=revocation_epoch+1;
    END IF;
    RETURN version;
END; $$;

CREATE FUNCTION pf_product.eligible_version(w uuid,v uuid) RETURNS boolean
LANGUAGE sql SECURITY DEFINER SET search_path=pg_catalog,pg_temp AS $$
    SELECT EXISTS(SELECT 1 FROM pf_product.versions x
        JOIN pf_product.contract_approvals c ON c.workspace_id=x.workspace_id AND c.asset_id=x.contract_id
        CROSS JOIN pf_product.execution_policy p WHERE x.workspace_id=w AND x.id=v
        AND x.revoked_at IS NULL AND c.revoked_at IS NULL AND c.sha256=x.contract_sha256
        AND x.verification_epoch=p.verification_epoch AND x.runtime_sha256=p.runtime_sha256
        AND x.verifier_sha256=p.verifier_sha256);
$$;

CREATE OR REPLACE FUNCTION pf_product.revoke_contract(workspace uuid,session_digest text,csrf_digest text,
    asset uuid) RETURNS void LANGUAGE plpgsql SECURITY DEFINER SET search_path=pg_catalog,pg_temp AS $$
BEGIN
    PERFORM pg_advisory_xact_lock(604061,2);
    PERFORM pf_product.authorize(workspace,session_digest,csrf_digest,true);
    UPDATE pf_product.contract_approvals SET revoked_at=COALESCE(revoked_at,clock_timestamp())
        WHERE workspace_id=workspace AND asset_id=asset;
    UPDATE pf_product.pipelines p SET active_version=NULL,revision=revision+1,revocation_epoch=revocation_epoch+1
        WHERE p.workspace_id=workspace AND EXISTS(SELECT 1 FROM pf_product.versions v
        WHERE v.workspace_id=workspace AND v.id=p.active_version AND v.contract_id=asset);
    UPDATE pf_product.jobs SET cancel_requested=true WHERE workspace_id=workspace AND contract_id=asset
        AND state NOT IN ('NEEDS_REVIEW','FAILED_INFRA','CANCELLED');
END; $$;

CREATE FUNCTION pf_product.prepare_version(w uuid,s text,c text,r uuid,code_asset uuid) RETURNS jsonb
LANGUAGE plpgsql SECURITY DEFINER SET search_path=pg_catalog,pg_temp AS $$
DECLARE x pf_product.repairs%ROWTYPE; j pf_product.jobs%ROWTYPE; candidate bytea;
    pipeline uuid; code_hash text; contract_hash text; evidence text; current_policy bigint;
BEGIN
    PERFORM pg_advisory_xact_lock(604061,2);
    SELECT verification_epoch INTO current_policy FROM pf_product.execution_policy WHERE singleton FOR SHARE;
    PERFORM pf_product.authorize(w,s,c,true);
    SELECT * INTO x FROM pf_product.repairs WHERE workspace_id=w AND id=r;
    IF NOT FOUND OR x.state<>'AWAITING_APPROVAL' OR x.outcome<>'candidate_passed'
        OR x.cancel_requested OR x.verification_epoch<>current_policy THEN
        RAISE EXCEPTION 'VERSION_NOT_ELIGIBLE'; END IF;
    SELECT * INTO j FROM pf_product.jobs WHERE workspace_id=w AND id=x.parent_id;
    SELECT convert_to(source,'UTF8') INTO candidate FROM pf_product.repair_candidates
        WHERE workspace_id=w AND repair_id=r AND ordinal=x.calls;
    code_hash:=encode(sha256(candidate),'hex');
    IF candidate IS NULL OR NOT EXISTS(SELECT 1 FROM pf_product.assets WHERE workspace_id=w
        AND id=code_asset AND kind='pipeline' AND sha256=code_hash AND byte_size=octet_length(candidate))
        THEN RAISE EXCEPTION 'VERSION_ASSET_MISMATCH'; END IF;
    SELECT sha256 INTO contract_hash FROM pf_product.contract_approvals WHERE workspace_id=w
        AND asset_id=j.contract_id AND revoked_at IS NULL;
    IF contract_hash IS NULL OR NOT EXISTS(SELECT 1 FROM pf_product.execution_policy
        WHERE runtime_sha256=j.runtime_sha256 AND verifier_sha256=j.verifier_sha256) THEN
        RAISE EXCEPTION 'VERSION_NOT_ELIGIBLE'; END IF;
    SELECT pipeline_id INTO pipeline FROM pf_product.batches WHERE workspace_id=w AND id=j.id;
    pipeline:=COALESCE(pipeline,j.pipeline_id);
    IF EXISTS(SELECT 1 FROM pf_product.versions WHERE workspace_id=w AND id=r) THEN
        IF NOT EXISTS(SELECT 1 FROM pf_product.versions WHERE workspace_id=w AND id=r
            AND code_asset_id=code_asset) THEN RAISE EXCEPTION 'VERSION_CONFLICT'; END IF;
        RETURN jsonb_build_object('version_id',r,'pipeline_id',pipeline);
    END IF;
    IF (SELECT count(*) FROM pf_product.versions)>=32 THEN RAISE EXCEPTION 'VERSION_CAPACITY'; END IF;
    SELECT encode(sha256(convert_to(jsonb_agg(jsonb_build_object('intent',intent,'result',result)
        ORDER BY generation)::text,'UTF8')),'hex') INTO evidence FROM pf_product.repair_executions
        WHERE workspace_id=w AND repair_id=r AND attempt=x.calls;
    IF evidence IS NULL OR (SELECT count(*) FROM pf_product.repair_executions WHERE workspace_id=w
        AND repair_id=r AND attempt=x.calls AND result#>>'{semantic,report,result,comparison}'='match'
        AND result#>>'{worker,cleanup}'='confirmed')<>3 THEN RAISE EXCEPTION 'VERSION_NOT_ELIGIBLE'; END IF;
    INSERT INTO pf_product.pipelines(workspace_id,id) VALUES(w,pipeline) ON CONFLICT DO NOTHING;
    INSERT INTO pf_product.versions(workspace_id,id,pipeline_id,repair_id,code_asset_id,contract_id,
        code_sha256,contract_sha256,evidence_sha256,runtime_sha256,verifier_sha256,verification_epoch)
        VALUES(w,r,pipeline,r,code_asset,j.contract_id,code_hash,contract_hash,evidence,
            j.runtime_sha256,j.verifier_sha256,current_policy);
    INSERT INTO pf_product.version_events(workspace_id,version_id,actor,event)
        VALUES(w,r,s,'verified_version_prepared');
    RETURN jsonb_build_object('version_id',r,'pipeline_id',pipeline);
END; $$;

CREATE FUNCTION pf_product.version_bundle(w uuid,s text,v uuid,intent uuid,stamp timestamptz) RETURNS jsonb
LANGUAGE sql SECURITY DEFINER SET search_path=pg_catalog,pg_temp AS $$
    SELECT jsonb_build_object('schema_version','proofflow-approval-v1','workspace_id',w,'pipeline_id',x.pipeline_id,
        'version_id',v,'repair_id',x.repair_id,'candidate_sha256',x.code_sha256,'contract_id',x.contract_id,
        'contract_sha256',x.contract_sha256,'evidence_sha256',x.evidence_sha256,
        'runtime_sha256',x.runtime_sha256,'verifier_sha256',x.verifier_sha256,
        'verification_epoch',x.verification_epoch::text,'expected_active_version',p.active_version,
        'pipeline_revision',p.revision::text,'revocation_epoch',p.revocation_epoch::text,
        'actor_sha256',s,'intent_id',intent,'action','activate_exact_version','created_at',stamp)
        FROM pf_product.versions x JOIN pf_product.pipelines p ON p.workspace_id=x.workspace_id
        AND p.id=x.pipeline_id WHERE x.workspace_id=w AND x.id=v;
$$;
CREATE FUNCTION pf_product.preview_version(w uuid,s text,c text,v uuid,intent uuid) RETURNS jsonb
LANGUAGE plpgsql SECURITY DEFINER SET search_path=pg_catalog,pg_temp AS $$
DECLARE a pf_product.approval_intents%ROWTYPE; value jsonb; stamp timestamptz:=clock_timestamp();
BEGIN
    PERFORM pg_advisory_xact_lock(604061,2);
    PERFORM 1 FROM pf_product.execution_policy WHERE singleton FOR SHARE;
    PERFORM pf_product.authorize(w,s,c,true);
    IF NOT pf_product.eligible_version(w,v) THEN RAISE EXCEPTION 'VERSION_NOT_ELIGIBLE'; END IF;
    SELECT * INTO a FROM pf_product.approval_intents WHERE workspace_id=w AND id=intent;
    IF FOUND THEN
        IF a.version_id<>v OR a.actor<>s THEN RAISE EXCEPTION 'VERSION_CONFLICT'; END IF;
    ELSE
        IF (SELECT count(*) FROM pf_product.approval_intents WHERE workspace_id=w)>=64 THEN
            RAISE EXCEPTION 'VERSION_CAPACITY'; END IF;
        value:=pf_product.version_bundle(w,s,v,intent,stamp);
        INSERT INTO pf_product.approval_intents(workspace_id,id,version_id,actor,bundle,digest,created_at)
            VALUES(w,intent,v,s,value,encode(sha256(convert_to(value::text,'UTF8')),'hex'),stamp)
            RETURNING * INTO a;
    END IF;
    RETURN jsonb_build_object('intent_id',a.id,'bundle',a.bundle,'bundle_sha256',a.digest,'expires_at',a.expires_at);
END; $$;

CREATE FUNCTION pf_product.approve_version(w uuid,s text,c text,v uuid,intent uuid,digest text) RETURNS jsonb
LANGUAGE plpgsql SECURITY DEFINER SET search_path=pg_catalog,pg_temp AS $$
DECLARE a pf_product.approval_intents%ROWTYPE; current_bundle jsonb; pipeline uuid;
BEGIN
    PERFORM pg_advisory_xact_lock(604061,2);
    PERFORM 1 FROM pf_product.execution_policy WHERE singleton FOR SHARE;
    PERFORM pf_product.authorize(w,s,c,true);
    SELECT * INTO a FROM pf_product.approval_intents WHERE workspace_id=w AND id=intent FOR UPDATE;
    IF NOT FOUND OR a.actor<>s OR a.version_id<>v OR a.digest IS DISTINCT FROM digest THEN
        RAISE EXCEPTION 'EXACT_VERSION_APPROVAL_REQUIRED'; END IF;
    IF a.approved_at IS NOT NULL THEN
        RETURN jsonb_build_object('version_id',v,'approved',true,'already_applied',true); END IF;
    IF a.expires_at<=clock_timestamp() OR NOT pf_product.eligible_version(w,v) THEN
        RAISE EXCEPTION 'VERSION_NOT_ELIGIBLE'; END IF;
    current_bundle:=pf_product.version_bundle(w,s,v,intent,a.created_at);
    IF current_bundle IS DISTINCT FROM a.bundle THEN RAISE EXCEPTION 'VERSION_CONFLICT'; END IF;
    SELECT pipeline_id INTO pipeline FROM pf_product.versions WHERE workspace_id=w AND id=v;
    UPDATE pf_product.pipelines SET active_version=v,revision=revision+1 WHERE workspace_id=w AND id=pipeline;
    UPDATE pf_product.approval_intents SET approved_at=clock_timestamp() WHERE workspace_id=w AND id=intent;
    INSERT INTO pf_product.version_events(workspace_id,version_id,actor,event,intent_id)
        VALUES(w,v,s,'exact_version_activated',intent);
    RETURN jsonb_build_object('version_id',v,'approved',true,'already_applied',false);
END; $$;

CREATE FUNCTION pf_product.get_version(w uuid,s text,v uuid) RETURNS jsonb
LANGUAGE plpgsql SECURITY DEFINER SET search_path=pg_catalog,pg_temp AS $$
DECLARE result jsonb;
BEGIN
    PERFORM pf_product.authorize(w,s,NULL,false);
    SELECT to_jsonb(x)||jsonb_build_object('active_version',p.active_version,'pipeline_revision',p.revision::text,
        'eligible',pf_product.eligible_version(w,v),'events',COALESCE((SELECT jsonb_agg(
        jsonb_build_object('sequence',e.sequence::text,'event',e.event,'occurred_at',e.occurred_at)
        ORDER BY e.sequence) FROM pf_product.version_events e WHERE e.workspace_id=w AND e.version_id=v),'[]'))
        INTO result FROM pf_product.versions x JOIN pf_product.pipelines p ON p.workspace_id=w
        AND p.id=x.pipeline_id WHERE x.workspace_id=w AND x.id=v;
    RETURN result;
END; $$;
CREATE FUNCTION pf_product.revoke_version(w uuid,s text,c text,v uuid,expected_revision bigint) RETURNS boolean
LANGUAGE plpgsql SECURITY DEFINER SET search_path=pg_catalog,pg_temp AS $$
DECLARE x pf_product.versions%ROWTYPE; p pf_product.pipelines%ROWTYPE;
BEGIN
    PERFORM pg_advisory_xact_lock(604061,2);
    PERFORM pf_product.authorize(w,s,c,true);
    SELECT * INTO x FROM pf_product.versions WHERE workspace_id=w AND id=v FOR UPDATE;
    IF NOT FOUND THEN RAISE EXCEPTION 'VERSION_NOT_FOUND'; END IF;
    IF x.revoked_at IS NOT NULL THEN RETURN false; END IF;
    SELECT * INTO p FROM pf_product.pipelines WHERE workspace_id=w AND id=x.pipeline_id FOR UPDATE;
    IF p.revision IS DISTINCT FROM expected_revision THEN RAISE EXCEPTION 'VERSION_CONFLICT'; END IF;
    UPDATE pf_product.versions SET revoked_at=clock_timestamp() WHERE workspace_id=w AND id=v;
    UPDATE pf_product.pipelines SET active_version=CASE WHEN active_version=v THEN NULL ELSE active_version END,
        revision=revision+1,revocation_epoch=revocation_epoch+1 WHERE workspace_id=w AND id=x.pipeline_id;
    UPDATE pf_product.jobs j SET cancel_requested=true WHERE j.workspace_id=w AND
        j.state NOT IN ('NEEDS_REVIEW','FAILED_INFRA','CANCELLED') AND EXISTS(SELECT 1 FROM pf_product.batches b
        WHERE b.workspace_id=w AND b.id=j.id AND b.version_id=v);
    INSERT INTO pf_product.version_events(workspace_id,version_id,actor,event) VALUES(w,v,s,'version_revoked');
    RETURN true;
END; $$;

CREATE FUNCTION pf_product.enqueue_batch(w uuid,s text,c text,pipeline uuid,expected_version uuid,
    job uuid,idem uuid,transactions uuid,customers uuid) RETURNS uuid
LANGUAGE plpgsql SECURITY DEFINER SET search_path=pg_catalog,pg_temp AS $$
DECLARE v pf_product.versions%ROWTYPE; prior pf_product.jobs%ROWTYPE; identity uuid;
BEGIN
    PERFORM pg_advisory_xact_lock(604061,2);
    PERFORM 1 FROM pf_product.execution_policy WHERE singleton FOR SHARE;
    PERFORM pf_product.authorize(w,s,c,true);
    -- Retry binds to the original immutable assignment even after ordinary activation.
    SELECT * INTO prior FROM pf_product.jobs WHERE workspace_id=w AND idempotency_key=idem;
    IF FOUND THEN
        IF prior.transactions_id<>transactions OR prior.customers_id<>customers OR NOT EXISTS(
            SELECT 1 FROM pf_product.batches WHERE workspace_id=w AND id=prior.id
            AND pipeline_id=pipeline AND version_id=expected_version) THEN
            RAISE EXCEPTION 'JOB_IDEMPOTENCY_CONFLICT'; END IF;
        RETURN prior.id;
    END IF;
    SELECT x.* INTO v FROM pf_product.versions x JOIN pf_product.pipelines p
        ON p.workspace_id=w AND p.id=pipeline AND p.active_version=x.id
        WHERE x.workspace_id=w AND x.id=expected_version AND x.pipeline_id=pipeline;
    IF NOT FOUND OR NOT pf_product.eligible_version(w,v.id) THEN RAISE EXCEPTION 'VERSION_NOT_ELIGIBLE'; END IF;
    identity:=pf_product.enqueue_original(w,s,c,job,idem,v.code_asset_id,transactions,customers,v.contract_id);
    INSERT INTO pf_product.batches(workspace_id,id,pipeline_id,version_id) VALUES(w,identity,pipeline,v.id);
    RETURN identity;
END; $$;

-- Existing original-run verifier/receipts remain mandatory. Version authority is
-- checked under the same lock before dispatch, heartbeat, capture and completion.
ALTER FUNCTION pf_product.guard_job(uuid,uuid,uuid,integer,boolean) RENAME TO guard_job_without_version;
CREATE FUNCTION pf_product.guard_job(workspace uuid,job uuid,controller uuid,fence integer,allow_cancel boolean)
RETURNS pf_product.jobs LANGUAGE plpgsql SECURITY DEFINER SET search_path=pg_catalog,pg_temp AS $$
DECLARE j pf_product.jobs%ROWTYPE; v uuid;
BEGIN
    j:=pf_product.guard_job_without_version(workspace,job,controller,fence,allow_cancel);
    SELECT version_id INTO v FROM pf_product.batches WHERE workspace_id=workspace AND id=job;
    IF NOT allow_cancel AND v IS NOT NULL AND NOT pf_product.eligible_version(workspace,v) THEN
        RAISE EXCEPTION 'JOB_AUTHORITY_REVOKED'; END IF;
    RETURN j;
END; $$;
CREATE FUNCTION pf_product.get_batch(w uuid,s text,b uuid) RETURNS jsonb
LANGUAGE plpgsql SECURITY DEFINER SET search_path=pg_catalog,pg_temp AS $$
DECLARE result jsonb;
BEGIN
    PERFORM pf_product.authorize(w,s,NULL,false);
    SELECT jsonb_build_object('id',b,'pipeline_id',x.pipeline_id,'version_id',x.version_id,
        'state',CASE WHEN j.state='NEEDS_REVIEW' AND j.outcome='match' THEN 'COMPLETED'
            WHEN j.state='NEEDS_REVIEW' THEN 'HELD_FOR_REVIEW'
            WHEN j.state='QUEUED' THEN 'QUEUED' WHEN j.state='FAILED_INFRA' THEN 'FAILED_INFRA'
            WHEN j.state='CANCELLED' THEN 'CANCELLED' ELSE 'RUNNING' END,
        'version_currently_eligible',pf_product.eligible_version(w,x.version_id),
        'outcome',j.outcome,'created_at',x.created_at,'report',j.report,'job_id',j.id)
        INTO result FROM pf_product.batches x JOIN pf_product.jobs j ON j.workspace_id=x.workspace_id AND j.id=x.id
        WHERE x.workspace_id=w AND x.id=b;
    RETURN result;
END; $$;

REVOKE ALL ON ALL TABLES IN SCHEMA pf_product FROM PUBLIC;
REVOKE ALL ON FUNCTION pf_product.pin_repair_policy(),pf_product.eligible_version(uuid,uuid),
    pf_product.version_bundle(uuid,text,uuid,uuid,timestamptz),
    pf_product.guard_job_without_version(uuid,uuid,uuid,integer,boolean),
    pf_product.guard_job(uuid,uuid,uuid,integer,boolean),
    pf_product.prepare_version(uuid,text,text,uuid,uuid),pf_product.preview_version(uuid,text,text,uuid,uuid),
    pf_product.approve_version(uuid,text,text,uuid,uuid,text),pf_product.get_version(uuid,text,uuid),
    pf_product.revoke_version(uuid,text,text,uuid,bigint),
    pf_product.enqueue_batch(uuid,text,text,uuid,uuid,uuid,uuid,uuid,uuid),pf_product.get_batch(uuid,text,uuid)
    FROM PUBLIC;
RESET ROLE;
GRANT EXECUTE ON FUNCTION pf_product.prepare_version(uuid,text,text,uuid,uuid),
    pf_product.preview_version(uuid,text,text,uuid,uuid),pf_product.approve_version(uuid,text,text,uuid,uuid,text),
    pf_product.get_version(uuid,text,uuid),pf_product.revoke_version(uuid,text,text,uuid,bigint),
    pf_product.enqueue_batch(uuid,text,text,uuid,uuid,uuid,uuid,uuid,uuid),pf_product.get_batch(uuid,text,uuid)
    TO pf_product_api;
COMMIT;

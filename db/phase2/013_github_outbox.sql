-- Operator-only, exact approved draft PR. No product use of development Git credentials.
BEGIN;
SET LOCAL ROLE pf_product_owner;
CREATE TABLE pf_product.github_configuration (
    singleton boolean PRIMARY KEY CHECK(singleton), configuration jsonb NOT NULL,
    digest text NOT NULL, enabled boolean NOT NULL DEFAULT false
);
CREATE TABLE pf_product.pr_intents (
    workspace_id uuid NOT NULL, id uuid NOT NULL, version_id uuid NOT NULL, actor text NOT NULL,
    configuration_sha256 text NOT NULL, binding jsonb NOT NULL,
    state text NOT NULL DEFAULT 'PREPARING' CHECK(state IN ('PREPARING','PREVIEW','APPROVED',
        'BRANCH_PENDING','BRANCH_READY','COMMIT_PENDING','COMMIT_READY','PR_PENDING','COMPLETE','STOPPED','UNCERTAIN')),
    created_at timestamptz NOT NULL DEFAULT clock_timestamp(), expires_at timestamptz NOT NULL,
    preview jsonb, preview_sha256 text, approved_at timestamptz, head_sha text, result jsonb,
    lease_owner uuid, lease_until timestamptz, generation integer NOT NULL DEFAULT 0,
    attempts integer NOT NULL DEFAULT 0, retry_after timestamptz NOT NULL DEFAULT clock_timestamp(),
    diagnostic text,
    PRIMARY KEY(workspace_id,id),
    FOREIGN KEY(workspace_id,version_id) REFERENCES pf_product.versions(workspace_id,id)
);
CREATE TABLE pf_product.pr_writes (
    workspace_id uuid NOT NULL, intent_id uuid NOT NULL, stage text NOT NULL,
    authorized_at timestamptz NOT NULL DEFAULT clock_timestamp(), generation integer NOT NULL,
    approval_sha256 text NOT NULL, request jsonb NOT NULL, request_sha256 text NOT NULL,
    readback jsonb, confirmed_at timestamptz,
    PRIMARY KEY(workspace_id,intent_id,stage),
    FOREIGN KEY(workspace_id,intent_id) REFERENCES pf_product.pr_intents(workspace_id,id)
);

CREATE FUNCTION pf_product.configure_github(value jsonb, p_enabled boolean) RETURNS text
LANGUAGE plpgsql SECURITY DEFINER SET search_path=pg_catalog,pg_temp AS $$
DECLARE cfg_digest text;
BEGIN
    PERFORM pf_product.require_transaction(); PERFORM pg_advisory_xact_lock(604061,2);
    IF value IS NULL OR jsonb_typeof(value)<>'object' OR p_enabled IS NULL
        OR (SELECT count(*) FROM jsonb_object_keys(value))<>7
        OR value->>'owner' IS DISTINCT FROM 'arslanabdulghaffar'
        OR value->>'repository' IS DISTINCT FROM 'ProofFlow-Demo'
        OR value->>'base' IS DISTINCT FROM 'main' OR value->>'path' IS DISTINCT FROM 'pipeline.py'
        OR COALESCE(value->>'client_id','') !~ '^[A-Za-z0-9_.-]{1,64}$'
        OR COALESCE(value->>'installation_id','') !~ '^[1-9][0-9]{0,17}$'
        OR COALESCE(value->>'repository_id','') !~ '^[1-9][0-9]{0,17}$' THEN
        RAISE EXCEPTION 'GITHUB_CONFIGURATION_INVALID'; END IF;
    cfg_digest:=encode(sha256(convert_to(value::text,'UTF8')),'hex');
    -- Never revive an old approval by changing configuration away and back.
    UPDATE pf_product.pr_intents SET expires_at=LEAST(expires_at,clock_timestamp())
        WHERE NOT EXISTS(SELECT 1 FROM pf_product.github_configuration g
            WHERE g.digest=cfg_digest AND g.enabled=p_enabled);
    INSERT INTO pf_product.github_configuration VALUES(true,value,cfg_digest,p_enabled)
        ON CONFLICT(singleton) DO UPDATE SET configuration=EXCLUDED.configuration,
            digest=EXCLUDED.digest,enabled=EXCLUDED.enabled;
    RETURN cfg_digest;
END; $$;

CREATE FUNCTION pf_product.pr_current(a pf_product.pr_intents) RETURNS boolean
LANGUAGE sql SECURITY DEFINER SET search_path=pg_catalog,pg_temp AS $$
    SELECT a.expires_at>clock_timestamp() AND pf_product.eligible_version(a.workspace_id,a.version_id)
        AND EXISTS(SELECT 1 FROM pf_product.workspaces w JOIN pf_product.sessions s ON s.workspace_id=w.id
            WHERE w.id=a.workspace_id AND w.kind='operator' AND w.revoked_at IS NULL
            AND w.expires_at>clock_timestamp() AND s.token_hash=a.actor AND s.revoked_at IS NULL
            AND s.expires_at>clock_timestamp())
        AND EXISTS(SELECT 1 FROM pf_product.github_configuration g
            WHERE g.enabled AND g.digest=a.configuration_sha256)
        AND a.binding=pf_product.version_bundle(a.workspace_id,a.actor,a.version_id,a.id,a.created_at)
        AND a.binding->>'expected_active_version'=a.version_id::text;
$$;
CREATE FUNCTION pf_product.request_pr_preview(w uuid,s text,c text,v uuid,intent uuid) RETURNS uuid
LANGUAGE plpgsql SECURITY DEFINER SET search_path=pg_catalog,pg_temp AS $$
DECLARE a pf_product.pr_intents%ROWTYPE; cfg text; stamp timestamptz:=clock_timestamp();
BEGIN
    PERFORM pg_advisory_xact_lock(604061,2);
    IF pf_product.authorize(w,s,c,true)<>'operator' THEN RAISE EXCEPTION 'ACCESS_DENIED'; END IF;
    SELECT * INTO a FROM pf_product.pr_intents WHERE workspace_id=w AND id=intent;
    IF FOUND THEN
        IF a.actor<>s OR a.version_id<>v THEN RAISE EXCEPTION 'PR_CONFLICT'; END IF;
        RETURN a.id;
    END IF;
    SELECT digest INTO cfg FROM pf_product.github_configuration WHERE enabled;
    IF cfg IS NULL THEN RAISE EXCEPTION 'GITHUB_NOT_CONFIGURED'; END IF;
    IF (SELECT count(*) FROM pf_product.pr_intents)>=32 THEN RAISE EXCEPTION 'PR_CAPACITY'; END IF;
    INSERT INTO pf_product.pr_intents(workspace_id,id,version_id,actor,configuration_sha256,binding,
        created_at,expires_at) VALUES(w,intent,v,s,cfg,pf_product.version_bundle(w,s,v,intent,stamp),
        stamp,stamp+interval '10 minutes') RETURNING * INTO a;
    IF NOT COALESCE(pf_product.pr_current(a),false) THEN RAISE EXCEPTION 'VERSION_NOT_ELIGIBLE'; END IF;
    RETURN intent;
END; $$;
CREATE FUNCTION pf_product.get_pr_intent(w uuid,s text,intent uuid) RETURNS jsonb
LANGUAGE plpgsql SECURITY DEFINER SET search_path=pg_catalog,pg_temp AS $$
DECLARE result jsonb;
BEGIN
    PERFORM pf_product.authorize(w,s,NULL,false);
    SELECT jsonb_build_object('intent_id',a.id,'version_id',a.version_id,'state',a.state,
        'preview',a.preview,'preview_sha256',a.preview_sha256,'expires_at',a.expires_at,
        'approved_at',a.approved_at,'result',a.result,'diagnostic',a.diagnostic,
        'currently_authorized',COALESCE(pf_product.pr_current(a),false),
        'writes',COALESCE((SELECT jsonb_agg(jsonb_build_object('stage',x.stage,
            'authorized_at',x.authorized_at,'request_sha256',x.request_sha256,
            'confirmed_at',x.confirmed_at,'readback',x.readback) ORDER BY x.authorized_at)
            FROM pf_product.pr_writes x WHERE x.workspace_id=w AND x.intent_id=intent),'[]'))
        INTO result FROM pf_product.pr_intents a WHERE a.workspace_id=w AND a.id=intent;
    RETURN result;
END; $$;
CREATE FUNCTION pf_product.approve_pr(w uuid,s text,c text,intent uuid,digest text) RETURNS boolean
LANGUAGE plpgsql SECURITY DEFINER SET search_path=pg_catalog,pg_temp AS $$
DECLARE a pf_product.pr_intents%ROWTYPE;
BEGIN
    PERFORM pg_advisory_xact_lock(604061,2);
    IF pf_product.authorize(w,s,c,true)<>'operator' THEN RAISE EXCEPTION 'ACCESS_DENIED'; END IF;
    SELECT * INTO a FROM pf_product.pr_intents WHERE workspace_id=w AND id=intent FOR UPDATE;
    IF NOT FOUND OR a.actor<>s OR digest IS NULL OR a.preview_sha256 IS DISTINCT FROM digest THEN
        RAISE EXCEPTION 'EXACT_PR_APPROVAL_REQUIRED'; END IF;
    IF a.approved_at IS NOT NULL THEN RETURN false; END IF;
    IF a.state<>'PREVIEW' OR NOT COALESCE(pf_product.pr_current(a),false) THEN
        RAISE EXCEPTION 'PR_AUTHORITY_REVOKED'; END IF;
    UPDATE pf_product.pr_intents SET state='APPROVED',approved_at=clock_timestamp(),attempts=0
        WHERE workspace_id=w AND id=intent;
    RETURN true;
END; $$;
CREATE FUNCTION pf_product.claim_pr(controller uuid) RETURNS jsonb
LANGUAGE plpgsql SECURITY DEFINER SET search_path=pg_catalog,pg_temp AS $$
DECLARE a pf_product.pr_intents%ROWTYPE; cfg jsonb; source text;
BEGIN
    PERFORM pf_product.require_transaction(); PERFORM pg_advisory_xact_lock(604061,2);
    SELECT * INTO a FROM pf_product.pr_intents WHERE state IN ('PREPARING','APPROVED',
        'BRANCH_PENDING','BRANCH_READY','COMMIT_PENDING','COMMIT_READY','PR_PENDING')
        AND (lease_until IS NULL OR lease_until<=clock_timestamp()) AND retry_after<=clock_timestamp()
        ORDER BY created_at,id LIMIT 1 FOR UPDATE;
    IF NOT FOUND THEN RETURN NULL; END IF;
    IF a.attempts>=4 THEN
        UPDATE pf_product.pr_intents SET state=CASE WHEN a.state LIKE '%_PENDING' THEN 'UNCERTAIN'
            ELSE 'STOPPED' END,diagnostic='GITHUB_RECONCILIATION_EXHAUSTED',lease_owner=NULL,lease_until=NULL
            WHERE workspace_id=a.workspace_id AND id=a.id; RETURN NULL;
    END IF;
    IF a.state NOT LIKE '%_PENDING' AND NOT COALESCE(pf_product.pr_current(a),false) THEN
        UPDATE pf_product.pr_intents SET state='STOPPED',diagnostic='PR_AUTHORITY_REVOKED',
            lease_owner=NULL,lease_until=NULL WHERE workspace_id=a.workspace_id AND id=a.id; RETURN NULL;
    END IF;
    UPDATE pf_product.pr_intents SET lease_owner=controller,lease_until=clock_timestamp()+interval '180 seconds',
        generation=generation+1,attempts=attempts+1 WHERE workspace_id=a.workspace_id AND id=a.id
        RETURNING * INTO a;
    SELECT g.configuration INTO cfg FROM pf_product.github_configuration g WHERE g.digest=a.configuration_sha256;
    SELECT c.source INTO source FROM pf_product.versions v JOIN pf_product.repairs r
        ON r.workspace_id=v.workspace_id AND r.id=v.repair_id JOIN pf_product.repair_candidates c
        ON c.workspace_id=r.workspace_id AND c.repair_id=r.id AND c.ordinal=r.calls
        WHERE v.workspace_id=a.workspace_id AND v.id=a.version_id;
    RETURN to_jsonb(a)||jsonb_build_object('configuration',cfg,'candidate_source',source);
END; $$;
CREATE FUNCTION pf_product.guard_pr(w uuid,intent uuid,controller uuid,fence integer)
RETURNS pf_product.pr_intents LANGUAGE plpgsql SECURITY DEFINER SET search_path=pg_catalog,pg_temp AS $$
DECLARE a pf_product.pr_intents%ROWTYPE;
BEGIN
    PERFORM pf_product.require_transaction(); PERFORM pg_advisory_xact_lock(604061,2);
    -- Serialize dispatch authorization with logout/deletion, which use workspace locks.
    PERFORM 1 FROM pf_product.workspaces WHERE id=w FOR UPDATE;
    SELECT * INTO a FROM pf_product.pr_intents WHERE workspace_id=w AND id=intent FOR UPDATE;
    IF NOT FOUND OR a.lease_owner IS DISTINCT FROM controller OR a.generation IS DISTINCT FROM fence
        OR a.lease_until<=clock_timestamp() THEN RAISE EXCEPTION 'STALE_PR_LEASE'; END IF;
    PERFORM 1 FROM pf_product.sessions WHERE token_hash=a.actor FOR SHARE;
    RETURN a;
END; $$;
CREATE FUNCTION pf_product.record_pr_preview(w uuid,intent uuid,controller uuid,fence integer,inspection jsonb)
RETURNS text LANGUAGE plpgsql SECURITY DEFINER SET search_path=pg_catalog,pg_temp AS $$
DECLARE a pf_product.pr_intents%ROWTYPE; cfg jsonb; value jsonb; digest text; source text;
BEGIN
    a:=pf_product.guard_pr(w,intent,controller,fence);
    IF a.state<>'PREPARING' OR NOT COALESCE(pf_product.pr_current(a),false) THEN
        RAISE EXCEPTION 'PR_AUTHORITY_REVOKED'; END IF;
    IF inspection IS NULL OR jsonb_typeof(inspection)<>'object'
        OR (SELECT count(*) FROM jsonb_object_keys(inspection))<>5
        OR COALESCE(inspection->>'base_sha','') !~ '^[a-f0-9]{40}$'
        OR COALESCE(inspection->>'base_tree_sha','') !~ '^[a-f0-9]{40}$'
        OR (inspection->'prior_blob'<>'null'::jsonb AND COALESCE(inspection->>'prior_blob','') !~ '^[a-f0-9]{40}$')
        OR NOT inspection ? 'prior_blob'
        OR COALESCE(inspection->>'original_sha256','') !~ '^[a-f0-9]{64}$'
        OR jsonb_typeof(inspection->'diff') IS DISTINCT FROM 'string'
        OR octet_length(inspection->>'diff')>131072 THEN RAISE EXCEPTION 'PR_PREVIEW_INVALID'; END IF;
    SELECT g.configuration INTO cfg FROM pf_product.github_configuration g WHERE g.digest=a.configuration_sha256;
    SELECT c.source INTO source FROM pf_product.versions v JOIN pf_product.repairs r
        ON r.workspace_id=v.workspace_id AND r.id=v.repair_id JOIN pf_product.repair_candidates c
        ON c.workspace_id=r.workspace_id AND c.repair_id=r.id AND c.ordinal=r.calls
        WHERE v.workspace_id=w AND v.id=a.version_id;
    IF encode(sha256(convert_to(source,'UTF8')),'hex') IS DISTINCT FROM a.binding->>'candidate_sha256'
        THEN RAISE EXCEPTION 'VERSION_ASSET_MISMATCH'; END IF;
    value:=jsonb_build_object('schema_version','proofflow-pr-preview-v1','action','create_private_draft_pr',
        'intent_id',intent,'actor_sha256',a.actor,'configuration',cfg,'configuration_sha256',a.configuration_sha256,
        'version',a.binding,'inspection',inspection,'candidate_source',source,
        'branch','proofflow/intent-'||replace(intent::text,'-',''),
        'title','ProofFlow verified pipeline '||a.version_id::text,
        'body','Synthetic demo candidate. Exact approved version: '||a.version_id::text||E'\nSHA256: '||
            (a.binding->>'candidate_sha256')||E'\nIntent: '||intent::text||E'\nDraft for review; no merge or deployment approval.',
        'draft',true,'expires_at',a.expires_at);
    digest:=encode(sha256(convert_to(value::text,'UTF8')),'hex');
    UPDATE pf_product.pr_intents SET state='PREVIEW',preview=value,preview_sha256=digest,
        lease_owner=NULL,lease_until=NULL,attempts=0 WHERE workspace_id=w AND id=intent;
    RETURN digest;
END; $$;
CREATE FUNCTION pf_product.begin_pr_write(w uuid,intent uuid,controller uuid,fence integer,stage text)
RETURNS jsonb LANGUAGE plpgsql SECURITY DEFINER SET search_path=pg_catalog,pg_temp AS $$
DECLARE a pf_product.pr_intents%ROWTYPE; request jsonb; payload jsonb; root text;
BEGIN
    a:=pf_product.guard_pr(w,intent,controller,fence);
    IF a.approved_at IS NULL OR NOT COALESCE(pf_product.pr_current(a),false) THEN
        RAISE EXCEPTION 'PR_AUTHORITY_REVOKED'; END IF;
    IF NOT ((stage='branch' AND a.state='APPROVED') OR (stage='commit' AND a.state='BRANCH_READY')
        OR (stage='pr' AND a.state='COMMIT_READY')) THEN RAISE EXCEPTION 'PR_WRITE_ALREADY_PREPARED'; END IF;
    root:='/repos/arslanabdulghaffar/ProofFlow-Demo';
    IF stage='branch' THEN
        request:=jsonb_build_object('method','POST','path',root||'/git/refs','payload',
            jsonb_build_object('ref','refs/heads/'||(a.preview->>'branch'),'sha',a.preview#>>'{inspection,base_sha}'));
    ELSIF stage='commit' THEN
        payload:=jsonb_build_object('message','ProofFlow verified candidate '||replace(intent::text,'-',''),
            'branch',a.preview->>'branch','content',replace(encode(convert_to(a.preview->>'candidate_source','UTF8'),'base64'),E'\n',''));
        IF a.preview#>>'{inspection,prior_blob}' IS NOT NULL THEN
            payload:=payload||jsonb_build_object('sha',a.preview#>>'{inspection,prior_blob}'); END IF;
        request:=jsonb_build_object('method','PUT','path',root||'/contents/pipeline.py','payload',payload);
    ELSE
        request:=jsonb_build_object('method','POST','path',root||'/pulls','payload',jsonb_build_object(
            'title',a.preview->>'title','body',a.preview->>'body','head',a.preview->>'branch',
            'base','main','draft',true,'maintainer_can_modify',false));
    END IF;
    INSERT INTO pf_product.pr_writes(workspace_id,intent_id,stage,generation,approval_sha256,request,request_sha256)
        VALUES(w,intent,stage,fence,a.preview_sha256,request,encode(sha256(convert_to(request::text,'UTF8')),'hex'));
    UPDATE pf_product.pr_intents SET state=upper(stage)||'_PENDING',attempts=0 WHERE workspace_id=w AND id=intent;
    RETURN request;
END; $$;
CREATE FUNCTION pf_product.record_pr_readback(w uuid,intent uuid,controller uuid,fence integer,stage text,receipt jsonb)
RETURNS void LANGUAGE plpgsql SECURITY DEFINER SET search_path=pg_catalog,pg_temp AS $$
DECLARE a pf_product.pr_intents%ROWTYPE; head text;
BEGIN
    a:=pf_product.guard_pr(w,intent,controller,fence);
    IF stage IS NULL OR stage NOT IN ('branch','commit','pr') OR a.state<>upper(stage)||'_PENDING'
        OR receipt IS NULL OR jsonb_typeof(receipt)<>'object' OR octet_length(receipt::text)>4096 THEN
        RAISE EXCEPTION 'PR_READBACK_INVALID'; END IF;
    head:=receipt->>'head_sha';
    IF COALESCE(head,'') !~ '^[a-f0-9]{40}$' OR receipt->>'base_sha' IS DISTINCT FROM a.preview#>>'{inspection,base_sha}'
        OR (stage='branch' AND head IS DISTINCT FROM a.preview#>>'{inspection,base_sha}')
        OR (stage='pr' AND (head IS DISTINCT FROM a.head_sha OR receipt->'draft' IS DISTINCT FROM 'true'::jsonb
            OR receipt->>'repository_id' IS DISTINCT FROM a.preview#>>'{configuration,repository_id}')) THEN
        RAISE EXCEPTION 'PR_READBACK_INVALID'; END IF;
    UPDATE pf_product.pr_writes SET readback=receipt,confirmed_at=clock_timestamp()
        WHERE workspace_id=w AND intent_id=intent AND pr_writes.stage=record_pr_readback.stage AND confirmed_at IS NULL;
    IF NOT FOUND THEN RAISE EXCEPTION 'PR_READBACK_INVALID'; END IF;
    UPDATE pf_product.pr_intents SET state=CASE stage WHEN 'branch' THEN 'BRANCH_READY'
        WHEN 'commit' THEN 'COMMIT_READY' ELSE 'COMPLETE' END,head_sha=head,result=receipt,
        lease_owner=NULL,lease_until=NULL,attempts=0,diagnostic=NULL WHERE workspace_id=w AND id=intent;
END; $$;
CREATE FUNCTION pf_product.defer_pr(w uuid,intent uuid,controller uuid,fence integer,code text,terminal boolean)
RETURNS void LANGUAGE plpgsql SECURITY DEFINER SET search_path=pg_catalog,pg_temp AS $$
DECLARE a pf_product.pr_intents%ROWTYPE;
BEGIN
    a:=pf_product.guard_pr(w,intent,controller,fence);
    IF code IS NULL OR code !~ '^[A-Z_]{1,80}$' OR terminal IS NULL THEN RAISE EXCEPTION 'PR_DIAGNOSTIC_INVALID'; END IF;
    UPDATE pf_product.pr_intents SET diagnostic=code,lease_owner=NULL,lease_until=NULL,
        retry_after=clock_timestamp()+interval '15 seconds',
        state=CASE WHEN terminal THEN CASE WHEN a.state LIKE '%_PENDING' THEN 'UNCERTAIN' ELSE 'STOPPED' END
            ELSE state END WHERE workspace_id=w AND id=intent;
END; $$;

CREATE FUNCTION pf_product.resume_pr_readback(w uuid,intent uuid) RETURNS boolean
LANGUAGE plpgsql SECURITY DEFINER SET search_path=pg_catalog,pg_temp AS $$
DECLARE a pf_product.pr_intents%ROWTYPE; pending text;
BEGIN
    PERFORM pf_product.require_transaction(); PERFORM pg_advisory_xact_lock(604061,2);
    SELECT * INTO a FROM pf_product.pr_intents WHERE workspace_id=w AND id=intent FOR UPDATE;
    IF NOT FOUND OR a.state<>'UNCERTAIN' OR a.lease_owner IS NOT NULL THEN
        RAISE EXCEPTION 'PR_RECONCILIATION_REQUIRED'; END IF;
    SELECT stage INTO pending FROM pf_product.pr_writes WHERE workspace_id=w AND intent_id=intent
        AND confirmed_at IS NULL;
    IF pending IS NULL THEN RAISE EXCEPTION 'PR_RECONCILIATION_REQUIRED'; END IF;
    -- Administrative recovery permits bounded reads only, never subsequent writes.
    UPDATE pf_product.pr_intents SET state=upper(pending)||'_PENDING',attempts=0,
        expires_at=LEAST(expires_at,clock_timestamp()),retry_after=clock_timestamp()
        WHERE workspace_id=w AND id=intent;
    RETURN true;
END; $$;

-- Existing byte retirement must never remove evidence while an external write is unconfirmed.
ALTER FUNCTION pf_product.retention_plan() RENAME TO retention_plan_without_pr;
CREATE FUNCTION pf_product.retention_plan() RETURNS jsonb
LANGUAGE plpgsql SECURITY DEFINER SET search_path=pg_catalog,pg_temp AS $$
DECLARE plans jsonb;
BEGIN
    plans:=pf_product.retention_plan_without_pr();
    RETURN COALESCE((SELECT jsonb_agg(p) FROM jsonb_array_elements(plans) p WHERE NOT EXISTS(
        SELECT 1 FROM pf_product.pr_intents a WHERE a.workspace_id=(p->>'workspace')::uuid
        AND (a.state NOT IN ('PREVIEW','COMPLETE','STOPPED') OR a.lease_owner IS NOT NULL))),'[]');
END; $$;
ALTER FUNCTION pf_product.complete_deletion(uuid,text) RENAME TO complete_deletion_without_pr;
CREATE FUNCTION pf_product.complete_deletion(workspace uuid,digest text) RETURNS boolean
LANGUAGE plpgsql SECURITY DEFINER SET search_path=pg_catalog,pg_temp AS $$
BEGIN
    PERFORM pf_product.require_transaction(); PERFORM pg_advisory_xact_lock(604061,2);
    IF EXISTS(SELECT 1 FROM pf_product.pr_intents WHERE workspace_id=workspace
        AND (state NOT IN ('PREVIEW','COMPLETE','STOPPED') OR lease_owner IS NOT NULL)) THEN
        RAISE EXCEPTION 'PR_RECONCILIATION_REQUIRED'; END IF;
    DELETE FROM pf_product.pr_writes WHERE workspace_id=workspace;
    DELETE FROM pf_product.pr_intents WHERE workspace_id=workspace;
    RETURN pf_product.complete_deletion_without_pr(workspace,digest);
END; $$;
REVOKE ALL ON ALL TABLES IN SCHEMA pf_product FROM PUBLIC;
REVOKE ALL ON FUNCTION pf_product.configure_github(jsonb,boolean),pf_product.pr_current(pf_product.pr_intents),
    pf_product.request_pr_preview(uuid,text,text,uuid,uuid),pf_product.get_pr_intent(uuid,text,uuid),
    pf_product.approve_pr(uuid,text,text,uuid,text),pf_product.claim_pr(uuid),
    pf_product.guard_pr(uuid,uuid,uuid,integer),pf_product.record_pr_preview(uuid,uuid,uuid,integer,jsonb),
    pf_product.begin_pr_write(uuid,uuid,uuid,integer,text),pf_product.record_pr_readback(uuid,uuid,uuid,integer,text,jsonb),
    pf_product.defer_pr(uuid,uuid,uuid,integer,text,boolean),pf_product.retention_plan(),
    pf_product.resume_pr_readback(uuid,uuid),
    pf_product.complete_deletion(uuid,text) FROM PUBLIC;
RESET ROLE;
REVOKE ALL ON FUNCTION pf_product.retention_plan_without_pr(),pf_product.complete_deletion_without_pr(uuid,text)
    FROM PUBLIC,pf_product_provisioner;
GRANT EXECUTE ON FUNCTION pf_product.configure_github(jsonb,boolean),pf_product.retention_plan(),
    pf_product.resume_pr_readback(uuid,uuid),
    pf_product.complete_deletion(uuid,text) TO pf_product_provisioner;
GRANT EXECUTE ON FUNCTION pf_product.request_pr_preview(uuid,text,text,uuid,uuid),
    pf_product.get_pr_intent(uuid,text,uuid),pf_product.approve_pr(uuid,text,text,uuid,text) TO pf_product_api;
GRANT EXECUTE ON FUNCTION pf_product.claim_pr(uuid),pf_product.record_pr_preview(uuid,uuid,uuid,integer,jsonb),
    pf_product.begin_pr_write(uuid,uuid,uuid,integer,text),pf_product.record_pr_readback(uuid,uuid,uuid,integer,text,jsonb),
    pf_product.defer_pr(uuid,uuid,uuid,integer,text,boolean) TO pf_product_dispatcher;
COMMIT;

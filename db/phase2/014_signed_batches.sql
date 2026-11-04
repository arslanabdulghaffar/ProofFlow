-- Signed ingress delegates only fresh-batch submission to one existing operator session/pipeline.
BEGIN;
SET LOCAL ROLE pf_product_owner;
CREATE TABLE pf_product.batch_connections (
    id uuid PRIMARY KEY, workspace_id uuid NOT NULL, pipeline_id uuid NOT NULL,
    actor text NOT NULL REFERENCES pf_product.sessions(token_hash),
    created_at timestamptz NOT NULL DEFAULT clock_timestamp(), expires_at timestamptz NOT NULL,
    revoked_at timestamptz,
    FOREIGN KEY(workspace_id,pipeline_id) REFERENCES pf_product.pipelines(workspace_id,id)
);
CREATE TABLE pf_product.batch_deliveries (
    connection_id uuid NOT NULL REFERENCES pf_product.batch_connections(id), event_id uuid NOT NULL,
    workspace_id uuid NOT NULL, batch_id uuid NOT NULL, body_sha256 text NOT NULL,
    transactions_id uuid NOT NULL, customers_id uuid NOT NULL, accepted_at timestamptz NOT NULL DEFAULT clock_timestamp(),
    PRIMARY KEY(connection_id,event_id),
    FOREIGN KEY(workspace_id,batch_id) REFERENCES pf_product.batches(workspace_id,id)
);
CREATE FUNCTION pf_product.provision_batch_connection(w uuid,s text,pipeline uuid,connection uuid,expiry timestamptz)
RETURNS void LANGUAGE plpgsql SECURITY DEFINER SET search_path=pg_catalog,pg_temp AS $$
BEGIN
    PERFORM pg_advisory_xact_lock(604061,2);
    IF pf_product.authorize(w,s,NULL,false)<>'operator' THEN RAISE EXCEPTION 'ACCESS_DENIED'; END IF;
    IF connection IS NULL OR expiry IS NULL OR expiry<=clock_timestamp()
        OR NOT EXISTS(SELECT 1 FROM pf_product.sessions WHERE workspace_id=w AND token_hash=s AND expires_at>=expiry)
        OR NOT EXISTS(SELECT 1 FROM pf_product.pipelines WHERE workspace_id=w AND id=pipeline) THEN
        RAISE EXCEPTION 'BATCH_CONNECTION_INVALID'; END IF;
    IF (SELECT count(*) FROM pf_product.batch_connections)>=32 THEN RAISE EXCEPTION 'BATCH_CONNECTION_CAPACITY'; END IF;
    INSERT INTO pf_product.batch_connections(id,workspace_id,pipeline_id,actor,expires_at) VALUES(connection,w,pipeline,s,expiry);
END; $$;
CREATE FUNCTION pf_product.accept_batch_event(connection uuid,event uuid,stamp bigint,digest text,
    transactions uuid,customers uuid) RETURNS jsonb
LANGUAGE plpgsql SECURITY DEFINER SET search_path=pg_catalog,pg_temp AS $$
DECLARE x pf_product.batch_connections%ROWTYPE; d pf_product.batch_deliveries%ROWTYPE;
    csrf text; v uuid; job uuid;
BEGIN
    PERFORM pf_product.require_transaction(); PERFORM pg_advisory_xact_lock(604061,2);
    SELECT * INTO x FROM pf_product.batch_connections WHERE id=connection;
    IF NOT FOUND OR x.revoked_at IS NOT NULL OR x.expires_at<=clock_timestamp() THEN
        RAISE EXCEPTION 'BATCH_CONNECTION_UNAVAILABLE'; END IF;
    SELECT csrf_hash INTO csrf FROM pf_product.sessions WHERE token_hash=x.actor;
    IF pf_product.authorize(x.workspace_id,x.actor,csrf,true)<>'operator' THEN RAISE EXCEPTION 'ACCESS_DENIED'; END IF;
    IF event IS NULL OR stamp IS NULL OR abs(extract(epoch FROM clock_timestamp())-stamp)>300
        OR digest IS NULL OR digest !~ '^[a-f0-9]{64}$' THEN RAISE EXCEPTION 'BATCH_DELIVERY_INVALID'; END IF;
    SELECT * INTO d FROM pf_product.batch_deliveries WHERE connection_id=connection AND event_id=event;
    IF FOUND THEN
        IF d.body_sha256 IS DISTINCT FROM digest OR d.transactions_id IS DISTINCT FROM transactions
            OR d.customers_id IS DISTINCT FROM customers THEN RAISE EXCEPTION 'BATCH_DELIVERY_CONFLICT'; END IF;
        RETURN jsonb_build_object('batch_id',d.batch_id,'event_id',event,'already_accepted',true);
    END IF;
    IF (SELECT count(*) FROM pf_product.batch_deliveries)>=64 THEN RAISE EXCEPTION 'BATCH_DELIVERY_CAPACITY'; END IF;
    SELECT active_version INTO v FROM pf_product.pipelines WHERE workspace_id=x.workspace_id AND id=x.pipeline_id;
    IF v IS NULL THEN RAISE EXCEPTION 'VERSION_NOT_ELIGIBLE'; END IF;
    job:=pf_product.enqueue_batch(x.workspace_id,x.actor,csrf,x.pipeline_id,v,gen_random_uuid(),
        gen_random_uuid(),transactions,customers);
    INSERT INTO pf_product.batch_deliveries(connection_id,event_id,workspace_id,batch_id,body_sha256,transactions_id,customers_id)
        VALUES(connection,event,x.workspace_id,job,digest,transactions,customers);
    RETURN jsonb_build_object('batch_id',job,'event_id',event,'already_accepted',false);
END; $$;
CREATE FUNCTION pf_product.revoke_batch_connection(w uuid,s text,c text,connection uuid) RETURNS boolean
LANGUAGE plpgsql SECURITY DEFINER SET search_path=pg_catalog,pg_temp AS $$
BEGIN
    PERFORM pg_advisory_xact_lock(604061,2);
    IF pf_product.authorize(w,s,c,true)<>'operator' THEN RAISE EXCEPTION 'ACCESS_DENIED'; END IF;
    UPDATE pf_product.batch_connections SET revoked_at=COALESCE(revoked_at,clock_timestamp())
        WHERE workspace_id=w AND id=connection;
    IF NOT FOUND THEN RAISE EXCEPTION 'BATCH_CONNECTION_UNAVAILABLE'; END IF;
    UPDATE pf_product.jobs j SET cancel_requested=true WHERE j.workspace_id=w
        AND j.state NOT IN ('NEEDS_REVIEW','FAILED_INFRA','CANCELLED') AND EXISTS(
            SELECT 1 FROM pf_product.batch_deliveries d WHERE d.connection_id=connection
            AND d.workspace_id=w AND d.batch_id=j.id);
    RETURN true;
END; $$;
ALTER FUNCTION pf_product.complete_deletion(uuid,text) RENAME TO complete_deletion_without_connections;
CREATE FUNCTION pf_product.complete_deletion(workspace uuid,digest text) RETURNS boolean
LANGUAGE plpgsql SECURITY DEFINER SET search_path=pg_catalog,pg_temp AS $$
BEGIN
    PERFORM pf_product.require_transaction(); PERFORM pg_advisory_xact_lock(604061,2);
    DELETE FROM pf_product.batch_deliveries WHERE workspace_id=workspace;
    DELETE FROM pf_product.batch_connections WHERE workspace_id=workspace;
    RETURN pf_product.complete_deletion_without_connections(workspace,digest);
END; $$;
REVOKE ALL ON ALL TABLES IN SCHEMA pf_product FROM PUBLIC;
REVOKE ALL ON FUNCTION pf_product.provision_batch_connection(uuid,text,uuid,uuid,timestamptz),
    pf_product.accept_batch_event(uuid,uuid,bigint,text,uuid,uuid),
    pf_product.revoke_batch_connection(uuid,text,text,uuid),pf_product.complete_deletion(uuid,text) FROM PUBLIC;
RESET ROLE;
REVOKE ALL ON FUNCTION pf_product.complete_deletion_without_connections(uuid,text) FROM PUBLIC,pf_product_provisioner;
GRANT EXECUTE ON FUNCTION pf_product.provision_batch_connection(uuid,text,uuid,uuid,timestamptz),
    pf_product.complete_deletion(uuid,text) TO pf_product_provisioner;
GRANT EXECUTE ON FUNCTION pf_product.accept_batch_event(uuid,uuid,bigint,text,uuid,uuid),
    pf_product.revoke_batch_connection(uuid,text,text,uuid) TO pf_product_api;
COMMIT;

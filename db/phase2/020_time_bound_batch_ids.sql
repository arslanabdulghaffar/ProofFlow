-- Use time-bound worker job IDs for signed fresh batches; idempotency unchanged.
BEGIN;
SET LOCAL ROLE pf_product_owner;
CREATE OR REPLACE FUNCTION pf_product.accept_batch_event(connection uuid,event uuid,stamp bigint,digest text,
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
    job:=pf_product.enqueue_batch(x.workspace_id,x.actor,csrf,x.pipeline_id,v,uuidv7(),
        gen_random_uuid(),transactions,customers);
    INSERT INTO pf_product.batch_deliveries(connection_id,event_id,workspace_id,batch_id,body_sha256,transactions_id,customers_id)
        VALUES(connection,event,x.workspace_id,job,digest,transactions,customers);
    RETURN jsonb_build_object('batch_id',job,'event_id',event,'already_accepted',false);
END; $$;
RESET ROLE;
COMMIT;

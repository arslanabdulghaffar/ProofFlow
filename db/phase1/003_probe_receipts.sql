-- Infrastructure probe evidence, not model verification or billing settlement.
BEGIN;
CREATE TABLE pf_budget.probe_receipts (
    id uuid PRIMARY KEY,
    account_id uuid NOT NULL REFERENCES pf_budget.accounts(id),
    request_hash text NOT NULL CHECK (length(request_hash)=64 AND request_hash ~ '^[0-9a-f]{64}$'),
    payload bytea NOT NULL CHECK (octet_length(payload) BETWEEN 1 AND 102400),
    quote bytea NOT NULL CHECK (octet_length(quote) BETWEEN 1 AND 4096),
    reserve_micro bigint NOT NULL CHECK (reserve_micro BETWEEN 1 AND 2000000),
    state text NOT NULL DEFAULT 'PREPARED' CHECK (state IN ('PREPARED','RECORDED')),
    outcome text CHECK (outcome IN ('PARSED_RESPONSE','FAILED','OUTCOME_UNKNOWN')),
    response bytea CHECK (octet_length(response) BETWEEN 0 AND 262144),
    response_hash text GENERATED ALWAYS AS (encode(sha256(response),'hex')) STORED,
    http_status integer CHECK (http_status BETWEEN 100 AND 599),
    elapsed_ms integer CHECK (elapsed_ms >= 0),
    created_at timestamptz NOT NULL DEFAULT clock_timestamp(),
    recorded_at timestamptz,
    CHECK ((state='PREPARED') = (recorded_at IS NULL)),
    CHECK ((state='PREPARED') = (outcome IS NULL)),
    CHECK ((state='PREPARED') = (elapsed_ms IS NULL)),
    CHECK (outcome IS DISTINCT FROM 'PARSED_RESPONSE' OR (response IS NOT NULL AND http_status=200))
);
CREATE INDEX probe_receipts_account ON pf_budget.probe_receipts(account_id);

CREATE FUNCTION pf_budget.prepare_probe(account uuid, request_id uuid, digest text,
    request_bytes bytea, quote_bytes bytea, amount bigint)
RETURNS boolean LANGUAGE plpgsql SECURITY DEFINER
SET search_path=pg_catalog,pg_temp AS $$
DECLARE old pf_budget.probe_receipts%ROWTYPE;
BEGIN
    IF current_setting('transaction_isolation') <> 'read committed'
        OR current_setting('synchronous_commit') <> 'on' THEN
        RAISE EXCEPTION 'PROBE_REQUIRES_DURABLE_READ_COMMITTED';
    END IF;
    PERFORM id FROM pf_budget.accounts WHERE id=account FOR UPDATE;
    IF NOT FOUND THEN RAISE EXCEPTION 'UNKNOWN_BUDGET_ACCOUNT'; END IF;
    SELECT * INTO old FROM pf_budget.probe_receipts WHERE id=request_id;
    IF FOUND THEN
        IF old.account_id IS DISTINCT FROM account OR old.request_hash IS DISTINCT FROM digest
            OR old.payload IS DISTINCT FROM request_bytes OR old.quote IS DISTINCT FROM quote_bytes
            OR old.reserve_micro IS DISTINCT FROM amount THEN
            RAISE EXCEPTION 'PROBE_INTENT_CONFLICT';
        END IF;
        RETURN false;
    END IF;
    -- Bounded probe evidence; operator archival needs a separately reviewed policy.
    IF (SELECT count(*) FROM pf_budget.probe_receipts WHERE account_id=account) >= 100 THEN
        RAISE EXCEPTION 'PROBE_RECEIPT_CAPACITY';
    END IF;
    INSERT INTO pf_budget.probe_receipts(id,account_id,request_hash,payload,quote,reserve_micro)
    VALUES (request_id,account,digest,request_bytes,quote_bytes,amount);
    RETURN true;
END;
$$;

CREATE FUNCTION pf_budget.record_probe(account uuid, request_id uuid, digest text,
    result text, body bytea, status integer, elapsed integer)
RETURNS boolean LANGUAGE plpgsql SECURITY DEFINER
SET search_path=pg_catalog,pg_temp AS $$
DECLARE old pf_budget.probe_receipts%ROWTYPE;
BEGIN
    IF current_setting('transaction_isolation') <> 'read committed'
        OR current_setting('synchronous_commit') <> 'on' THEN
        RAISE EXCEPTION 'PROBE_REQUIRES_DURABLE_READ_COMMITTED';
    END IF;
    SELECT * INTO old FROM pf_budget.probe_receipts
        WHERE id=request_id AND account_id=account AND request_hash=digest FOR UPDATE;
    IF NOT FOUND THEN RAISE EXCEPTION 'PROBE_INTENT_CONFLICT'; END IF;
    IF old.state='RECORDED' THEN
        IF old.outcome IS DISTINCT FROM result OR old.response IS DISTINCT FROM body
            OR old.http_status IS DISTINCT FROM status OR old.elapsed_ms IS DISTINCT FROM elapsed THEN
            RAISE EXCEPTION 'PROBE_RECEIPT_CONFLICT';
        END IF;
        RETURN false;
    END IF;
    IF result='PARSED_RESPONSE' AND NOT EXISTS (
        SELECT 1 FROM pf_budget.reservations WHERE id=request_id AND account_id=account
        AND request_hash=digest AND state IN ('uncertain','settled')
    ) THEN RAISE EXCEPTION 'PROBE_NOT_CLAIMED'; END IF;
    UPDATE pf_budget.probe_receipts SET state='RECORDED',outcome=result,response=body,
        http_status=status,elapsed_ms=elapsed,recorded_at=clock_timestamp() WHERE id=request_id;
    RETURN true;
END;
$$;

CREATE FUNCTION pf_budget.read_probe(account uuid, request_id uuid)
RETURNS jsonb LANGUAGE sql STABLE SECURITY DEFINER
SET search_path=pg_catalog,pg_temp AS $$
    SELECT jsonb_build_object('request_id',id,'request_sha256',request_hash,
        'payload_base64',encode(payload,'base64'),'quote_base64',encode(quote,'base64'),
        'reserve_micro_usd',reserve_micro,'state',state,'outcome',outcome,
        'response_base64',encode(response,'base64'),'response_sha256',response_hash,
        'http_status',http_status,'elapsed_ms',elapsed_ms,
        'created_at',created_at,'recorded_at',recorded_at)
    FROM pf_budget.probe_receipts WHERE id=request_id AND account_id=account;
$$;
REVOKE ALL ON pf_budget.probe_receipts FROM PUBLIC;
REVOKE ALL ON FUNCTION pf_budget.prepare_probe(uuid,uuid,text,bytea,bytea,bigint),
    pf_budget.record_probe(uuid,uuid,text,text,bytea,integer,integer),
    pf_budget.read_probe(uuid,uuid) FROM PUBLIC;
ALTER TABLE pf_budget.probe_receipts OWNER TO pf_budget_owner;
ALTER FUNCTION pf_budget.prepare_probe(uuid,uuid,text,bytea,bytea,bigint) OWNER TO pf_budget_owner;
ALTER FUNCTION pf_budget.record_probe(uuid,uuid,text,text,bytea,integer,integer)
    OWNER TO pf_budget_owner;
ALTER FUNCTION pf_budget.read_probe(uuid,uuid) OWNER TO pf_budget_owner;
GRANT EXECUTE ON FUNCTION pf_budget.prepare_probe(uuid,uuid,text,bytea,bytea,bigint),
    pf_budget.record_probe(uuid,uuid,text,text,bytea,integer,integer),
    pf_budget.read_probe(uuid,uuid) TO pf_budget_dispatcher;
COMMIT;

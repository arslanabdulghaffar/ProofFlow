-- Infrastructure-only ledger, not the Phase 2 product/business schema.
-- Apply once as migration owner. Runtime identities receive functions only.
BEGIN;
CREATE SCHEMA pf_budget;
REVOKE ALL ON SCHEMA pf_budget FROM PUBLIC;
CREATE ROLE pf_budget_dispatcher NOLOGIN;
CREATE ROLE pf_budget_reconciler NOLOGIN;
CREATE ROLE pf_budget_owner NOLOGIN;

CREATE TABLE pf_budget.accounts (
    id uuid PRIMARY KEY,
    project_limit bigint NOT NULL CHECK (project_limit BETWEEN 1 AND 150000000),
    inference_limit bigint NOT NULL CHECK (inference_limit BETWEEN 1 AND 25000000),
    probe_limit bigint NOT NULL CHECK (probe_limit BETWEEN 1 AND 2000000),
    expires_at timestamptz NOT NULL,
    blocked boolean NOT NULL DEFAULT false,
    CHECK (probe_limit <= inference_limit AND inference_limit <= project_limit)
);
COMMENT ON TABLE pf_budget.accounts IS
    'USD integer micro-units. Limits are application admission controls, NOT provider billing caps or credit approval.';

CREATE TABLE pf_budget.reservations (
    id uuid PRIMARY KEY,
    account_id uuid NOT NULL REFERENCES pf_budget.accounts(id),
    request_hash text NOT NULL CHECK (length(request_hash) = 64 AND request_hash ~ '^[0-9a-f]+$'),
    purpose text NOT NULL CHECK (purpose IN ('probe', 'inference', 'compute', 'other')),
    reserved_micro bigint NOT NULL CHECK (reserved_micro BETWEEN 1 AND 150000000),
    valid_until timestamptz NOT NULL,
    state text NOT NULL DEFAULT 'reserved' CHECK (state IN ('reserved', 'uncertain', 'settled')),
    charged_micro bigint CHECK (charged_micro >= 0),
    evidence_hash text CHECK (length(evidence_hash) = 64 AND evidence_hash ~ '^[0-9a-f]+$'),
    created_at timestamptz NOT NULL DEFAULT clock_timestamp(),
    claimed_at timestamptz,
    settled_at timestamptz,
    CHECK ((state = 'settled' AND charged_micro IS NOT NULL AND evidence_hash IS NOT NULL)
        OR (state <> 'settled' AND charged_micro IS NULL AND evidence_hash IS NULL)),
    CHECK ((state = 'reserved') = (claimed_at IS NULL)),
    CHECK ((state = 'settled') = (settled_at IS NOT NULL))
);
CREATE INDEX reservations_account ON pf_budget.reservations(account_id);

CREATE FUNCTION pf_budget.reserve(
    account uuid, request_id uuid, digest text, category text, amount bigint, deadline timestamptz
) RETURNS boolean LANGUAGE plpgsql SECURITY DEFINER
SET search_path = pg_catalog, pg_temp AS $$
DECLARE
    a pf_budget.accounts%ROWTYPE;
    existing pf_budget.reservations%ROWTYPE;
    total_used numeric;
    inference_used numeric;
    probe_used numeric;
BEGIN
    -- The sum after the account lock must see a fresh committed snapshot.
    IF current_setting('transaction_isolation') <> 'read committed' THEN
        RAISE EXCEPTION 'BUDGET_REQUIRES_READ_COMMITTED';
    END IF;
    IF current_setting('synchronous_commit') <> 'on' THEN
        RAISE EXCEPTION 'BUDGET_REQUIRES_DURABLE_COMMIT';
    END IF;
    IF request_id IS NULL OR digest IS NULL OR length(digest) <> 64
       OR digest !~ '^[0-9a-f]+$' OR category IS NULL
       OR category NOT IN ('probe', 'inference', 'compute', 'other')
       OR amount IS NULL OR amount NOT BETWEEN 1 AND 150000000 OR deadline IS NULL THEN
        RAISE EXCEPTION 'INVALID_RESERVATION';
    END IF;
    SELECT * INTO a FROM pf_budget.accounts WHERE id = account FOR UPDATE;
    IF NOT FOUND THEN RAISE EXCEPTION 'UNKNOWN_BUDGET_ACCOUNT'; END IF;
    SELECT * INTO existing FROM pf_budget.reservations WHERE id = request_id;
    IF FOUND THEN
        IF existing.account_id <> account OR existing.request_hash <> digest
           OR existing.purpose <> category OR existing.reserved_micro <> amount
           OR existing.valid_until <> deadline THEN
            RAISE EXCEPTION 'RESERVATION_CONFLICT';
        END IF;
        RETURN false; -- Existing intent is NOT authorization for another call.
    END IF;
    IF a.blocked OR a.expires_at <= clock_timestamp() THEN
        RAISE EXCEPTION 'BUDGET_ADMISSION_CLOSED';
    END IF;
    IF deadline <= clock_timestamp() OR deadline > a.expires_at THEN
        RAISE EXCEPTION 'INVALID_RESERVATION_DEADLINE';
    END IF;
    SELECT coalesce(sum(coalesce(charged_micro, reserved_micro)), 0),
           coalesce(sum(coalesce(charged_micro, reserved_micro))
               FILTER (WHERE purpose IN ('probe', 'inference')), 0),
           coalesce(sum(coalesce(charged_micro, reserved_micro))
               FILTER (WHERE purpose = 'probe'), 0)
    INTO total_used, inference_used, probe_used
    FROM pf_budget.reservations WHERE account_id = account;
    IF total_used + amount > a.project_limit
       OR (category IN ('probe', 'inference') AND inference_used + amount > a.inference_limit)
       OR (category = 'probe' AND probe_used + amount > a.probe_limit) THEN
        RAISE EXCEPTION 'BUDGET_EXHAUSTED';
    END IF;
    INSERT INTO pf_budget.reservations
        (id, account_id, request_hash, purpose, reserved_micro, valid_until)
    VALUES (request_id, account, digest, category, amount, deadline);
    RETURN true;
END;
$$;

CREATE FUNCTION pf_budget.claim(account uuid, request_id uuid, digest text)
RETURNS boolean LANGUAGE plpgsql SECURITY DEFINER
SET search_path = pg_catalog, pg_temp AS $$
DECLARE
    a pf_budget.accounts%ROWTYPE;
    r pf_budget.reservations%ROWTYPE;
BEGIN
    -- The sum after the account lock must see a fresh committed snapshot.
    IF current_setting('transaction_isolation') <> 'read committed' THEN
        RAISE EXCEPTION 'BUDGET_REQUIRES_READ_COMMITTED';
    END IF;
    IF current_setting('synchronous_commit') <> 'on' THEN
        RAISE EXCEPTION 'BUDGET_REQUIRES_DURABLE_COMMIT';
    END IF;
    SELECT * INTO a FROM pf_budget.accounts WHERE id = account FOR UPDATE;
    IF NOT FOUND THEN RAISE EXCEPTION 'UNKNOWN_BUDGET_ACCOUNT'; END IF;
    IF a.blocked OR a.expires_at <= clock_timestamp() THEN
        RAISE EXCEPTION 'BUDGET_ADMISSION_CLOSED';
    END IF;
    SELECT * INTO r FROM pf_budget.reservations WHERE id = request_id AND account_id = account;
    IF NOT FOUND OR digest IS DISTINCT FROM r.request_hash THEN
        RAISE EXCEPTION 'RESERVATION_CONFLICT';
    END IF;
    IF r.valid_until <= clock_timestamp() THEN
        RAISE EXCEPTION 'RESERVATION_EXPIRED';
    END IF;
    IF r.state <> 'reserved' THEN RETURN false; END IF;
    -- Commit this before network I/O. Lost commit/response is uncertain; no replay.
    UPDATE pf_budget.reservations SET state = 'uncertain', claimed_at = clock_timestamp()
    WHERE id = request_id;
    RETURN true;
END;
$$;

CREATE FUNCTION pf_budget.settle(
    account uuid, request_id uuid, amount bigint, evidence text
) RETURNS boolean LANGUAGE plpgsql SECURITY DEFINER
SET search_path = pg_catalog, pg_temp AS $$
DECLARE
    r pf_budget.reservations%ROWTYPE;
BEGIN
    -- The sum after the account lock must see a fresh committed snapshot.
    IF current_setting('transaction_isolation') <> 'read committed' THEN
        RAISE EXCEPTION 'BUDGET_REQUIRES_READ_COMMITTED';
    END IF;
    IF current_setting('synchronous_commit') <> 'on' THEN
        RAISE EXCEPTION 'BUDGET_REQUIRES_DURABLE_COMMIT';
    END IF;
    IF amount IS NULL OR amount < 0 OR evidence IS NULL OR length(evidence) <> 64
       OR evidence !~ '^[0-9a-f]+$' THEN RAISE EXCEPTION 'INVALID_SETTLEMENT'; END IF;
    PERFORM id FROM pf_budget.accounts WHERE id = account FOR UPDATE;
    IF NOT FOUND THEN RAISE EXCEPTION 'UNKNOWN_BUDGET_ACCOUNT'; END IF;
    SELECT * INTO r FROM pf_budget.reservations WHERE id = request_id AND account_id = account;
    IF NOT FOUND THEN RAISE EXCEPTION 'RESERVATION_CONFLICT'; END IF;
    IF r.state = 'settled' THEN
        IF r.charged_micro <> amount OR r.evidence_hash <> evidence THEN
            RAISE EXCEPTION 'SETTLEMENT_CONFLICT';
        END IF;
        RETURN false;
    END IF;
    IF r.state <> 'uncertain' THEN RAISE EXCEPTION 'RESERVATION_NOT_CLAIMED'; END IF;
    UPDATE pf_budget.reservations
    SET state = 'settled', charged_micro = amount, evidence_hash = evidence,
        settled_at = clock_timestamp() WHERE id = request_id;
    -- Never discard an unexpectedly high real charge to preserve the budget illusion.
    IF amount > r.reserved_micro THEN
        UPDATE pf_budget.accounts SET blocked = true WHERE id = account;
    END IF;
    RETURN true;
END;
$$;

REVOKE ALL ON ALL TABLES IN SCHEMA pf_budget FROM PUBLIC;
REVOKE ALL ON ALL FUNCTIONS IN SCHEMA pf_budget FROM PUBLIC;
ALTER SCHEMA pf_budget OWNER TO pf_budget_owner;
ALTER TABLE pf_budget.accounts OWNER TO pf_budget_owner;
ALTER TABLE pf_budget.reservations OWNER TO pf_budget_owner;
ALTER FUNCTION pf_budget.reserve(uuid, uuid, text, text, bigint, timestamptz)
    OWNER TO pf_budget_owner;
ALTER FUNCTION pf_budget.claim(uuid, uuid, text) OWNER TO pf_budget_owner;
ALTER FUNCTION pf_budget.settle(uuid, uuid, bigint, text) OWNER TO pf_budget_owner;
GRANT USAGE ON SCHEMA pf_budget TO pf_budget_dispatcher, pf_budget_reconciler;
GRANT EXECUTE ON FUNCTION pf_budget.reserve(uuid, uuid, text, text, bigint, timestamptz),
    pf_budget.claim(uuid, uuid, text) TO pf_budget_dispatcher;
GRANT EXECUTE ON FUNCTION pf_budget.settle(uuid, uuid, bigint, text) TO pf_budget_reconciler;
COMMIT;

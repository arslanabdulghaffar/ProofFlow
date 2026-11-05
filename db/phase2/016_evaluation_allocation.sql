-- Share the unchanged $5 development envelope with finite evaluation pilots.
-- This is a conservative allocation, not provider settlement or model dispatch.
BEGIN;
SET LOCAL ROLE pf_product_owner;
CREATE TABLE pf_product.evaluation_allocations (
    id uuid PRIMARY KEY,
    manifest_sha256 text NOT NULL CHECK(manifest_sha256 ~ '^[a-f0-9]{64}$'),
    reserved_micro bigint NOT NULL CHECK(reserved_micro BETWEEN 1 AND 1200000),
    created_at timestamptz NOT NULL DEFAULT clock_timestamp()
);
CREATE FUNCTION pf_product.reserve_evaluation(id uuid, digest text, amount bigint)
RETURNS boolean LANGUAGE plpgsql SECURITY DEFINER SET search_path=pg_catalog,pg_temp AS $$
DECLARE old pf_product.evaluation_allocations%ROWTYPE;
BEGIN
    PERFORM pf_product.require_transaction();
    IF id IS NULL OR digest IS NULL OR digest !~ '^[a-f0-9]{64}$'
        OR amount IS NULL OR amount NOT BETWEEN 1 AND 1200000 THEN
        RAISE EXCEPTION 'EVALUATION_ALLOCATION_INVALID'; END IF;
    -- Serialize with prepare_repair_call, which uses this same advisory lock.
    PERFORM pg_advisory_xact_lock(604061,4);
    PERFORM 1 FROM pf_product.repair_allocation WHERE singleton FOR UPDATE;
    IF NOT FOUND THEN RAISE EXCEPTION 'EVALUATION_ALLOCATION_MISSING'; END IF;
    SELECT * INTO old FROM pf_product.evaluation_allocations e WHERE e.id=reserve_evaluation.id;
    IF FOUND THEN
        IF old.manifest_sha256<>digest OR old.reserved_micro<>amount THEN
            RAISE EXCEPTION 'EVALUATION_ALLOCATION_CONFLICT'; END IF;
        RETURN false;
    END IF;
    IF (SELECT count(*) FROM pf_product.evaluation_allocations)>=16
        OR (SELECT reserved_micro FROM pf_product.repair_allocation WHERE singleton)+amount>5000000
        THEN RAISE EXCEPTION 'REPAIR_DEVELOPMENT_ALLOCATION'; END IF;
    UPDATE pf_product.repair_allocation SET reserved_micro=reserved_micro+amount WHERE singleton;
    INSERT INTO pf_product.evaluation_allocations VALUES(id,digest,amount,clock_timestamp());
    RETURN true;
END; $$;
REVOKE ALL ON pf_product.evaluation_allocations FROM PUBLIC;
REVOKE ALL ON FUNCTION pf_product.reserve_evaluation(uuid,text,bigint) FROM PUBLIC;
RESET ROLE;
GRANT EXECUTE ON FUNCTION pf_product.reserve_evaluation(uuid,text,bigint) TO pf_product_provisioner;
COMMIT;

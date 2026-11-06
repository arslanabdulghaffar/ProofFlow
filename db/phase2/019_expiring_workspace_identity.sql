-- Only time-bound new workspace IDs; expired deletion rows can then be retired
-- without permitting the same ID to be created again. Never restores authority.
BEGIN;
SET LOCAL ROLE pf_product_owner;
CREATE TABLE pf_product.retention_clock (
    singleton boolean PRIMARY KEY CHECK(singleton),
    observed_at timestamptz NOT NULL,
    expiry_enabled boolean NOT NULL DEFAULT false,
    runtime_sha256 text
);
INSERT INTO pf_product.retention_clock(singleton,observed_at) VALUES(true,clock_timestamp());
CREATE FUNCTION pf_product.enable_retention_expiry(runtime text) RETURNS void
LANGUAGE plpgsql SECURITY DEFINER SET search_path=pg_catalog,pg_temp AS $$
BEGIN
    PERFORM pf_product.require_transaction();
    PERFORM pg_advisory_xact_lock(604061,2);
    IF NOT EXISTS(SELECT 1 FROM pf_product.execution_policy
        WHERE runtime_sha256=runtime AND NOT enabled) THEN
        RAISE EXCEPTION 'CLOSED_MATCHING_RUNTIME_REQUIRED'; END IF;
    UPDATE pf_product.retention_clock SET expiry_enabled=true,runtime_sha256=runtime WHERE singleton;
END; $$;
CREATE FUNCTION pf_product.retention_expiry_ready() RETURNS boolean
LANGUAGE sql SECURITY DEFINER SET search_path=pg_catalog,pg_temp AS $$
    SELECT EXISTS(SELECT 1 FROM pf_product.retention_clock r
        JOIN pf_product.execution_policy p ON p.runtime_sha256=r.runtime_sha256
        WHERE r.singleton AND r.expiry_enabled)
$$;
CREATE FUNCTION pf_product.require_fresh_workspace_identity() RETURNS trigger
LANGUAGE plpgsql SECURITY DEFINER SET search_path=pg_catalog,pg_temp AS $$
DECLARE observed timestamptz; issued timestamptz;
BEGIN
    UPDATE pf_product.retention_clock SET observed_at=greatest(observed_at,clock_timestamp())
        WHERE singleton RETURNING observed_at INTO observed;
    issued:=uuid_extract_timestamp(NEW.id);
    IF observed IS NULL OR uuid_extract_version(NEW.id) IS DISTINCT FROM 7
        OR issued IS NULL OR issued<observed-interval '60 seconds'
        OR issued>observed+interval '5 seconds' THEN
        RAISE EXCEPTION 'FRESH_WORKSPACE_ID_REQUIRED';
    END IF;
    RETURN NEW;
END; $$;
-- After the existing deletion guard so retained deleted IDs preserve its error.
CREATE TRIGGER z_fresh_workspace_identity BEFORE INSERT ON pf_product.workspaces
FOR EACH ROW EXECUTE FUNCTION pf_product.require_fresh_workspace_identity();
CREATE FUNCTION pf_product.prune_deletion_metadata() RETURNS integer
LANGUAGE plpgsql SECURITY DEFINER SET search_path=pg_catalog,pg_temp AS $$
DECLARE observed timestamptz; removed integer;
BEGIN
    PERFORM pf_product.require_transaction();
    PERFORM pg_advisory_xact_lock(604061,2);
    IF NOT pf_product.retention_expiry_ready()
        THEN RAISE EXCEPTION 'RETENTION_EXPIRY_NOT_ENABLED'; END IF;
    UPDATE pf_product.retention_clock SET observed_at=greatest(observed_at,clock_timestamp())
        WHERE singleton RETURNING observed_at INTO observed;
    IF observed IS NULL THEN RAISE EXCEPTION 'RETENTION_CLOCK_REQUIRED'; END IF;
    DELETE FROM pf_product.deletions WHERE workspace_id IN (
        SELECT d.workspace_id FROM pf_product.deletions d
        WHERE d.completed_at<=observed-interval '7 days'
        AND (uuid_extract_version(d.workspace_id) IS DISTINCT FROM 7
             OR uuid_extract_timestamp(d.workspace_id)<=observed-interval '7 days')
        AND NOT EXISTS(SELECT 1 FROM pf_product.workspaces w WHERE w.id=d.workspace_id)
        ORDER BY d.completed_at LIMIT 32
    );
    GET DIAGNOSTICS removed=ROW_COUNT;
    RETURN removed;
END; $$;
REVOKE ALL ON pf_product.retention_clock FROM PUBLIC;
REVOKE ALL ON FUNCTION pf_product.require_fresh_workspace_identity(),
    pf_product.prune_deletion_metadata(),pf_product.enable_retention_expiry(text),
    pf_product.retention_expiry_ready() FROM PUBLIC;
GRANT EXECUTE ON FUNCTION pf_product.prune_deletion_metadata(),
    pf_product.enable_retention_expiry(text),pf_product.retention_expiry_ready()
    TO pf_product_provisioner;
RESET ROLE;
COMMIT;

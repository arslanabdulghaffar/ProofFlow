-- Expired operator workspaces use the same revoke/cleanup/erase path as guests.
-- Preserve PR reconciliation gates and permanent restore tombstones.
BEGIN;
SET LOCAL ROLE pf_product_owner;
ALTER FUNCTION pf_product.retention_plan() RENAME TO retention_plan_before_operator_expiry;
CREATE FUNCTION pf_product.retention_plan() RETURNS jsonb
LANGUAGE plpgsql SECURITY DEFINER SET search_path=pg_catalog,pg_temp AS $$
BEGIN
    PERFORM pf_product.require_transaction();
    PERFORM pg_advisory_xact_lock(604061,2);
    -- Lock in the same order as the underlying planner. Insert requests only;
    -- never mark cleanup complete or bypass running/uncertain executions.
    PERFORM id FROM pf_product.workspaces WHERE kind='operator'
        AND expires_at<=clock_timestamp() ORDER BY created_at FOR UPDATE;
    INSERT INTO pf_product.deletions(workspace_id,reason)
        SELECT id,'expiry' FROM pf_product.workspaces WHERE kind='operator'
        AND expires_at<=clock_timestamp() ON CONFLICT DO NOTHING;
    RETURN pf_product.retention_plan_before_operator_expiry();
END; $$;
REVOKE ALL ON FUNCTION pf_product.retention_plan(),
    pf_product.retention_plan_before_operator_expiry() FROM PUBLIC;
RESET ROLE;
REVOKE ALL ON FUNCTION pf_product.retention_plan_before_operator_expiry()
    FROM pf_product_provisioner;
GRANT EXECUTE ON FUNCTION pf_product.retention_plan() TO pf_product_provisioner;
COMMIT;

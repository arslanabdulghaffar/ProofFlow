-- Bounded, currently authorized replay. No caller state/event mutation.
BEGIN;
SET LOCAL ROLE pf_product_owner;
CREATE FUNCTION pf_product.read_job_events(workspace uuid, session_digest text, job uuid,
    after_sequence bigint) RETURNS jsonb
LANGUAGE plpgsql SECURITY DEFINER SET search_path=pg_catalog,pg_temp AS $$
DECLARE current_sequence bigint; result jsonb;
BEGIN
    PERFORM pf_product.authorize(workspace,session_digest,NULL,false);
    SELECT event_sequence INTO current_sequence FROM pf_product.jobs
        WHERE workspace_id=workspace AND id=job;
    IF NOT FOUND THEN RAISE EXCEPTION 'JOB_NOT_FOUND'; END IF;
    IF after_sequence IS NULL OR after_sequence<0 OR after_sequence>current_sequence THEN
        RAISE EXCEPTION 'INVALID_EVENT_CURSOR';
    END IF;
    SELECT COALESCE(jsonb_agg(jsonb_build_object('sequence',e.sequence::text,
        'state',e.state,'event',e.event,'occurred_at',e.occurred_at)
        ORDER BY e.sequence),'[]'::jsonb) INTO result
        FROM (SELECT * FROM pf_product.job_events
              WHERE workspace_id=workspace AND job_id=job AND sequence>after_sequence
              ORDER BY sequence LIMIT 64) e;
    RETURN result;
END;
$$;
REVOKE ALL ON FUNCTION pf_product.read_job_events(uuid,text,uuid,bigint) FROM PUBLIC;
RESET ROLE;
GRANT EXECUTE ON FUNCTION pf_product.read_job_events(uuid,text,uuid,bigint) TO pf_product_api;
COMMIT;

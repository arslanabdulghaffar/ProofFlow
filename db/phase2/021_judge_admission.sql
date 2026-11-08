-- Public bootstrap can create only a NEW, bounded guest identity. No role promotion.
BEGIN;
SET LOCAL ROLE pf_product_owner;
CREATE TABLE pf_product.judge_admission (
    singleton boolean PRIMARY KEY CHECK(singleton),
    available_until timestamptz NOT NULL DEFAULT '-infinity',
    funded_until timestamptz NOT NULL DEFAULT '-infinity',
    claims integer NOT NULL DEFAULT 0 CHECK(claims BETWEEN 0 AND 128),
    last_claim timestamptz NOT NULL DEFAULT '-infinity'
);
INSERT INTO pf_product.judge_admission(singleton) VALUES(true);
CREATE FUNCTION pf_product.claim_judge(workspace uuid, token text, csrf text)
RETURNS timestamptz LANGUAGE plpgsql SECURITY DEFINER
SET search_path=pg_catalog,pg_temp AS $$
DECLARE admission pf_product.judge_admission%ROWTYPE; expiry timestamptz;
BEGIN
    PERFORM pf_product.require_transaction();
    SELECT * INTO admission FROM pf_product.judge_admission WHERE singleton FOR UPDATE;
    IF NOT FOUND OR admission.available_until<=clock_timestamp()
        OR admission.funded_until<clock_timestamp()+interval '35 minutes'
        OR NOT EXISTS(SELECT 1 FROM pf_product.execution_policy WHERE enabled)
        THEN RAISE EXCEPTION 'ADMISSION_CLOSED'; END IF;
    IF admission.claims>=128 OR admission.last_claim>clock_timestamp()-interval '10 seconds'
        OR (SELECT count(*) FROM pf_product.workspaces)>=8
        THEN RAISE EXCEPTION 'JOB_CAPACITY'; END IF;
    expiry:=clock_timestamp()+interval '30 minutes';
    PERFORM pf_product.create_workspace(workspace,'guest',expiry);
    PERFORM pf_product.create_session(workspace,token,csrf,expiry);
    UPDATE pf_product.judge_admission SET claims=claims+1,last_claim=clock_timestamp() WHERE singleton;
    RETURN expiry;
END; $$;
REVOKE ALL ON pf_product.judge_admission FROM PUBLIC,pf_product_api,pf_product_dispatcher;
REVOKE ALL ON FUNCTION pf_product.claim_judge(uuid,text,text) FROM PUBLIC;
GRANT EXECUTE ON FUNCTION pf_product.claim_judge(uuid,text,text) TO pf_product_api;
RESET ROLE;
COMMIT;

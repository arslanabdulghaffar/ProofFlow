-- Reserve quota durably BEFORE publishing bytes; uncertain writes retain their reservation.
BEGIN;
DO $$ BEGIN
    IF current_database() <> 'proofflow_product' THEN
        RAISE EXCEPTION 'WRONG_PRODUCT_DATABASE';
    END IF;
END $$;
SET LOCAL ROLE pf_product_owner;
CREATE TABLE pf_product.uploads (
    workspace_id uuid NOT NULL REFERENCES pf_product.workspaces(id),
    id uuid NOT NULL,
    kind text NOT NULL CHECK (kind IN ('pipeline','transactions','customers','contract')),
    sha256 text NOT NULL CHECK (sha256 ~ '^[0-9a-f]{64}$'),
    byte_size integer NOT NULL CHECK (byte_size > 0),
    created_at timestamptz NOT NULL DEFAULT clock_timestamp(),
    PRIMARY KEY(workspace_id,id),
    CHECK ((kind='pipeline' AND byte_size<=16384) OR (kind='contract' AND byte_size<=32768)
        OR (kind IN ('transactions','customers') AND byte_size<=5242880))
);
COMMENT ON TABLE pf_product.uploads IS
    'Reserved unpublished bytes; never release automatically after uncertain filesystem writes.';

CREATE FUNCTION pf_product.reserve_upload(workspace uuid, session_digest text, csrf_digest text,
    asset_id uuid, asset_kind text, digest text, bytes integer) RETURNS boolean
LANGUAGE plpgsql SECURITY DEFINER SET search_path=pg_catalog,pg_temp AS $$
DECLARE existing record; objects bigint; total bigint;
BEGIN
    PERFORM pf_product.authorize(workspace,session_digest,csrf_digest,true);
    IF asset_id IS NULL OR asset_kind IS NULL
       OR asset_kind NOT IN ('pipeline','transactions','customers','contract')
       OR digest IS NULL OR digest !~ '^[0-9a-f]{64}$' OR bytes IS NULL OR bytes<1
       OR bytes > (CASE asset_kind WHEN 'pipeline' THEN 16384 WHEN 'contract' THEN 32768
                                  ELSE 5242880 END) THEN RAISE EXCEPTION 'INVALID_ASSET'; END IF;
    SELECT a.kind,a.sha256,a.byte_size INTO existing FROM pf_product.assets a
        WHERE a.workspace_id=workspace AND a.id=asset_id;
    IF FOUND THEN
        IF existing.kind<>asset_kind OR existing.sha256<>digest OR existing.byte_size<>bytes THEN
            RAISE EXCEPTION 'ASSET_IDEMPOTENCY_CONFLICT';
        END IF;
        RETURN false;
    END IF;
    SELECT u.kind,u.sha256,u.byte_size INTO existing FROM pf_product.uploads u
        WHERE u.workspace_id=workspace AND u.id=asset_id;
    IF FOUND THEN
        IF existing.kind<>asset_kind OR existing.sha256<>digest OR existing.byte_size<>bytes THEN
            RAISE EXCEPTION 'ASSET_IDEMPOTENCY_CONFLICT';
        END IF;
        RETURN true;
    END IF;
    SELECT count(*),COALESCE(sum(s.byte_size),0) INTO objects,total FROM (
        SELECT a.byte_size FROM pf_product.assets a WHERE a.workspace_id=workspace
        UNION ALL SELECT u.byte_size FROM pf_product.uploads u WHERE u.workspace_id=workspace
    ) AS s;
    IF objects>=64 OR total+bytes>134217728 THEN RAISE EXCEPTION 'ASSET_QUOTA'; END IF;
    INSERT INTO pf_product.uploads(workspace_id,id,kind,sha256,byte_size)
        VALUES(workspace,asset_id,asset_kind,digest,bytes);
    RETURN true;
END;
$$;

CREATE FUNCTION pf_product.complete_upload(workspace uuid, session_digest text, csrf_digest text,
    asset_id uuid, asset_kind text, digest text, bytes integer) RETURNS boolean
LANGUAGE plpgsql SECURITY DEFINER SET search_path=pg_catalog,pg_temp AS $$
DECLARE pending pf_product.uploads%ROWTYPE; created boolean; existing pf_product.assets%ROWTYPE;
BEGIN
    PERFORM pf_product.authorize(workspace,session_digest,csrf_digest,true);
    SELECT * INTO pending FROM pf_product.uploads WHERE workspace_id=workspace AND id=asset_id;
    IF NOT FOUND THEN
        SELECT * INTO existing FROM pf_product.assets WHERE workspace_id=workspace AND id=asset_id;
        IF FOUND AND existing.kind IS NOT DISTINCT FROM asset_kind
           AND existing.sha256 IS NOT DISTINCT FROM digest
           AND existing.byte_size IS NOT DISTINCT FROM bytes THEN RETURN false; END IF;
        RAISE EXCEPTION 'UPLOAD_RESERVATION_REQUIRED';
    END IF;
    IF pending.kind IS DISTINCT FROM asset_kind OR pending.sha256 IS DISTINCT FROM digest
       OR pending.byte_size IS DISTINCT FROM bytes THEN RAISE EXCEPTION 'ASSET_IDEMPOTENCY_CONFLICT';
    END IF;
    -- Publication/hash/fsync precede this call. The same workspace lock covers
    -- both rows so a concurrent reserve cannot observe a transient free slot.
    created := pf_product.register_asset(workspace,session_digest,csrf_digest,
                                         asset_id,asset_kind,digest,bytes);
    DELETE FROM pf_product.uploads WHERE workspace_id=workspace AND id=asset_id;
    RETURN created;
END;
$$;
REVOKE ALL ON pf_product.uploads FROM PUBLIC;
REVOKE EXECUTE ON FUNCTION pf_product.register_asset(uuid,text,text,uuid,text,text,integer)
    FROM pf_product_api;
REVOKE ALL ON FUNCTION pf_product.reserve_upload(uuid,text,text,uuid,text,text,integer),
    pf_product.complete_upload(uuid,text,text,uuid,text,text,integer) FROM PUBLIC;
GRANT EXECUTE ON FUNCTION pf_product.reserve_upload(uuid,text,text,uuid,text,text,integer),
    pf_product.complete_upload(uuid,text,text,uuid,text,text,integer) TO pf_product_api;
COMMIT;

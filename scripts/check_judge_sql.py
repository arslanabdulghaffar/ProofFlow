# ruff: noqa: S101, S107, E501 - disposable synthetic SQL fixture only
"""Real disposable PostgreSQL guest admission tests. No cloud or candidate execution."""

from uuid import uuid4

from tests.integration.product_database_fixture import database


def main():
    with database() as db:

        def claim(token="a", csrf="b"):
            # UUIDv7 supplied by the DB solely for this synthetic admission probe.
            return (
                "SELECT pf_product.claim_judge(uuidv7(),'" + token * 64 + "','" + csrf * 64 + "');"
            )

        db.expect(claim(), "ADMISSION_CLOSED")
        db.sql(
            "UPDATE pf_product.judge_admission SET available_until=clock_timestamp()+interval '3 minutes',"
            "funded_until=clock_timestamp()+interval '2 hours';"
            "SELECT pf_product.configure_execution('" + "a" * 64 + "','" + "b" * 64 + "',true);",
            "admin",
        )
        assert db.sql(claim())
        assert (
            db.sql(
                "SELECT count(*)=1 AND bool_and(kind='guest' AND expires_at<clock_timestamp()+interval '31 minutes') FROM pf_product.workspaces;",
                "admin",
            )
            == "t"
        )
        db.expect(claim("c", "d"), "JOB_CAPACITY")
        db.expect("UPDATE pf_product.judge_admission SET claims=0;", "permission denied")
        db.expect(
            "SELECT pf_product.create_workspace('"
            + str(uuid4())
            + "','operator',clock_timestamp()+interval '1 hour');",
            "permission denied",
        )
        db.sql("UPDATE pf_product.judge_admission SET last_claim='-infinity',claims=128;", "admin")
        db.expect(claim("c", "d"), "JOB_CAPACITY")
        db.sql(
            "UPDATE pf_product.judge_admission SET claims=1,available_until=clock_timestamp()-interval '1 second';",
            "admin",
        )
        db.expect(claim("c", "d"), "ADMISSION_CLOSED")
        assert db.sql("SELECT count(*) FROM pf_product.sessions;", "admin") == "1"
    print("JUDGE_SQL_BOUNDARIES_PASS_AND_FIXTURE_REMOVED")


if __name__ == "__main__":
    main()

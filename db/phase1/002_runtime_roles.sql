-- Apply once as administrator in proofflow_budget after 001_budget.sql.
-- No password/account/credit permission is created by this migration.
BEGIN;
CREATE ROLE pf_budget_login LOGIN NOSUPERUSER NOCREATEDB NOCREATEROLE
    NOREPLICATION NOBYPASSRLS CONNECTION LIMIT 8 IN ROLE pf_budget_dispatcher;
CREATE ROLE pf_budget_settlement_login NOLOGIN NOSUPERUSER NOCREATEDB NOCREATEROLE
    NOREPLICATION NOBYPASSRLS CONNECTION LIMIT 2 IN ROLE pf_budget_reconciler;
REVOKE ALL ON DATABASE proofflow_budget FROM PUBLIC;
GRANT CONNECT ON DATABASE proofflow_budget TO pf_budget_login, pf_budget_settlement_login;
REVOKE CREATE ON SCHEMA public FROM PUBLIC;
COMMIT;

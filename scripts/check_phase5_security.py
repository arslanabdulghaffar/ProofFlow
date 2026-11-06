"""Fixed deployed security regression; payload text executes only on the worker.

No model call, product job, approval, PR, new resource or admission opening.
Preserve receipts before checking results; fail closed on any critical failure.
"""

import hashlib
import json
import shlex
import ssl
import time
from datetime import UTC, datetime
from uuid import uuid4

import httpx
from check_product_integrity import AUTH_PROBE
from install_product_services import IMAGE
from product_live_session import ORIGIN, LiveSession, require
from vultr_phase1 import PRIVATE, ROOT

PROBES = ("filesystem", "network", "cpu", "storage", "inodes", "logs", "symlink",
          "fifo", "hardlink", "extra", "output_bytes", "output_lines", "memory",
          "timeout", "descendants", "benign")


def outbox_snapshot(live):
    """Current rowsets, including empty after normal retention; no historic ID assumption."""
    return json.loads(live.sql("""
        SELECT json_build_object(
          'intents',(SELECT encode(sha256(convert_to(coalesce(
            jsonb_agg(to_jsonb(p) ORDER BY to_jsonb(p)::text)::text,'[]'),'UTF8')),'hex')
            FROM pf_product.pr_intents p),
          'writes',(SELECT encode(sha256(convert_to(coalesce(
            jsonb_agg(to_jsonb(p) ORDER BY to_jsonb(p)::text)::text,'[]'),'UTF8')),'hex')
            FROM pf_product.pr_writes p));
    """))


def accepted(name, result, seconds):
    receipt, observed = result["receipt"], result.get("observed", {})
    if receipt.get("cleanup") != "confirmed":
        return False
    if name in {"symlink", "fifo", "hardlink", "extra", "output_bytes", "output_lines"}:
        return receipt.get("collected") is False and receipt.get("outcome") == "output_rejected"
    if name == "memory":
        return (receipt.get("unit_result") == "oom-kill" or
                receipt.get("resource_observation", {}).get("last_observed", {}).get(
                    "memory_events", {}).get("oom_kill", 0) > 0)
    if name in {"timeout", "descendants"}:
        return receipt.get("outcome") == "timeout" and seconds < 30
    if receipt.get("collected") is not True or receipt.get("runtime_client_exit_code") != 0:
        return False
    if name == "filesystem":
        return all(observed.get(n) in (2, 13, 30) for n in (
            "host_marker", "host_credential", "input_write")) and observed.get("root_write") == 30
    if name == "network":
        expected = {"private_control", "private_worker", "controlled_external", "external_ipv4",
                    "external_ipv6", "metadata", "dns", "udp", "raw_socket"}
        return set(observed) == expected and all(
            type(value) is dict and type(value.get("errno")) is int
            and value["errno"] != 0 for value in observed.values())
    if name == "cpu":
        cpu = receipt["resource_observation"]["last_observed"]["cpu"]
        return observed.get("elapsed_seconds", 0) >= 3 and cpu["nr_throttled"] > 0
    if name == "storage":
        return observed.get("aliases_share_bytes") is True and all(
            63 * 1024 * 1024 <= observed.get(n, {}).get("bytes_written", 0) <= 64 * 1024 * 1024
            and observed[n]["errno"] == 28
            for n in ("/scratch", "/output", "/dev/shm", "/tmp", "combined_aliases"))  # noqa: S108 - guest receipt labels
    if name == "inodes":
        return all(1000 <= observed.get(n, {}).get("files_created", 0) <= 1023
                   and observed[n]["errno"] == 28 for n in ("/scratch", "/output"))
    if name == "logs":
        return (sum(item["retained"] for item in receipt["logs"]) == 102400
                and sum(item["received"] for item in receipt["logs"]) >= 524288)
    if name == "benign":
        return observed.get("sums") == {"A": 150, "B": 350} and observed.get("uid") == 10001
    return False


def main():
    run = uuid4().hex
    folder = PRIVATE / "evidence" / ("phase5-security-" + run)
    folder.mkdir(mode=0o700)
    summary = {"run": run, "started_at": datetime.now(UTC).isoformat(), "image": IMAGE,
               "provider_calls": 0, "new_cloud_resources": 0, "probes": [],
               "network_positive_controls": "NOT_RERUN; prior Phase1 evidence retained",
               "independent_human_review": "NOT_AVAILABLE"}
    try:
        with LiveSession() as live:
            summary["credit"] = live.credit
            before = outbox_snapshot(live)
            require(live.sql("SELECT count(*)=1 AND bool_and(blocked) FROM pf_budget.accounts;",
                             "proofflow_budget") == b"t", "INFERENCE_MUST_STAY_BLOCKED")
            for role in ("api", "dispatcher"):
                config = json.loads(live.host("docker inspect proofflow-product-" + role))[0]
                host = config["HostConfig"]
                require(config["Image"] == "sha256:" + IMAGE and config["State"]["Running"]
                        and config["Config"]["User"] == "10003:10003"
                        and host["ReadonlyRootfs"] and host["CapDrop"] == ["ALL"]
                        and host["Memory"] == host["MemorySwap"] == 384 * 1024 * 1024
                        and host["PidsLimit"] == 64 and host["NanoCpus"] == 1000000000
                        and "no-new-privileges" in host["SecurityOpt"]
                        and host["NetworkMode"] == ("none" if role == "api" else "host")
                        and not host["PortBindings"], "DEPLOYED_SERVICE_POLICY_CHANGED")
                summary[role + "_auth"] = json.loads(live.host(
                    "docker exec -i proofflow-product-" + role + " python -c "
                    + shlex.quote(AUTH_PROBE), role.encode()))
            actual = live.host(
                "docker exec proofflow-product-api sha256sum /app/api/app/product.py")
            require(actual.decode().split()[0] == hashlib.sha256(
                (ROOT / "api/app/product.py").read_bytes()).hexdigest(), "HTTP_SOURCE_CHANGED")
            with httpx.Client(base_url=ORIGIN, trust_env=False, timeout=10,
                              verify=ssl.create_default_context(
                                  cafile=str(PRIVATE / "tls/ca.pem"))) as client:
                statuses = {path: client.get(path).status_code
                            for path in ("/health/live", "/health/ready", "/v1/session")}
                require(statuses == {"/health/live": 200, "/health/ready": 503,
                                     "/v1/session": 403}, "PRIVATE_HTTP_BOUNDARY_CHANGED")
                summary["http_statuses"] = statuses
            raw = (ROOT / "scripts/probe_worker_controller.py").read_bytes()
            target = "/opt/proofflow-control/probe_worker_controller.py"
            live.host("umask 077; cat > " + target, raw)
            require(live.host("sha256sum " + target).decode().split()[0]
                    == hashlib.sha256(raw).hexdigest(), "WORKER_PROBE_SOURCE_CHANGED")
            summary["probe_source_sha256"] = hashlib.sha256(raw).hexdigest()
            summary["worker_identity"] = json.loads(live.host(
                "/usr/bin/python3 -I -B " + target + " identity"))
            for name in PROBES:
                started = time.monotonic()
                reply = live.host("/usr/bin/python3 -I -B " + target + " " + name)
                seconds = time.monotonic() - started
                (folder / (name + ".json")).write_bytes(reply)
                result = json.loads(reply)
                passed = accepted(name, result, seconds)
                entry = {"probe": name, "passed": passed, "execution": result["execution"],
                         "receipt_sha256": hashlib.sha256(reply).hexdigest(),
                         "seconds": round(seconds, 3), "cleanup": result["receipt"]["cleanup"]}
                summary["probes"].append(entry)
                print(json.dumps(entry), flush=True)
                require(passed, "CRITICAL_WORKER_GATE_FAILED")
            require(outbox_snapshot(live) == before, "EXISTING_PR_RECEIPTS_CHANGED")
            summary["existing_pr_unchanged"] = True
            require(live.sql("SELECT bool_or(enabled) FROM pf_product.execution_policy;") == b"f",
                    "PRODUCT_ADMISSION_CHANGED")
            summary["passed"] = True
    finally:
        summary["finished_at"] = datetime.now(UTC).isoformat()
        (folder / "summary.json").write_text(json.dumps(summary, indent=2), encoding="utf-8")
        print(json.dumps({"run": run, "passed": summary.get("passed", False),
                          "passed_probes": sum(item["passed"] for item in summary["probes"])}))


if __name__ == "__main__":
    main()

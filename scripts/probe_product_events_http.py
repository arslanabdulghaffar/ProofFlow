"""Actual private event replay and live revocation using existing synthetic assets."""

import json
import ssl
import sys

import httpx


def require(value, code):
    if not value:
        raise RuntimeError(code)


def main():
    data = json.loads(sys.stdin.buffer.read(32768))
    def client(secret):
        return httpx.Client(base_url="https://127.0.0.1:18443", timeout=20,
            transport=httpx.HTTPTransport(uds="/run/proofflow-product-api/api.sock",
                verify=ssl.create_default_context(cafile="/etc/proofflow-product/tls/ca.pem")),
            headers={"Cookie": "__Host-proofflow=" + secret["session"],
                "Origin": "https://127.0.0.1:18443", "X-ProofFlow-CSRF": secret["csrf"]})
    with (client(data["control"]) as control, client(data["stream"]) as stream,
          client(data["foreign"]) as foreign):
        url = "/v1/jobs/" + data["existing_job"] + "/events"
        response = control.get(url)
        require(response.status_code == 200, "EVENT_REPLAY_FAILED")
        ids = [line[4:] for line in response.text.splitlines() if line.startswith("id: ")]
        require(len(ids) >= 3, "COMMITTED_EVENTS_MISSING")
        require([int(v.split(":")[1]) for v in ids] == list(range(1, len(ids)+1)),
                "EVENT_SEQUENCE_CHANGED")
        resumed = control.get(url, headers={"Last-Event-ID": ids[0]})
        require([line[4:] for line in resumed.text.splitlines() if line.startswith("id: ")]
                == ids[1:], "EVENT_RESUME_DUPLICATED_OR_SKIPPED")
        require(control.get(url, headers={"Last-Event-ID": ids[-1]}).status_code == 204,
                "TERMINAL_EVENT_STREAM_NOT_CLOSED")
        require(control.get(url, headers={"Last-Event-ID": data["existing_job"] + ":999"})
                .status_code == 400, "FUTURE_CURSOR_ACCEPTED")
        require(foreign.get(url).status_code == 404, "CROSS_WORKSPACE_EVENT_DISCLOSURE")
        response = control.post("/v1/jobs", json=data["enqueue"])
        require(response.status_code == 202, "EVENT_FIXTURE_ENQUEUE_FAILED")
        job = response.json()["job_id"]
        with stream.stream("GET", "/v1/jobs/" + job + "/events") as live:
            require(live.status_code == 200, "LIVE_STREAM_FAILED")
            iterator = live.iter_lines()
            first = []
            for line in iterator:
                first.append(line)
                if line == "":
                    break
            require(any(line.startswith("id: ") for line in first), "LIVE_EVENT_NOT_RECORDED")
            with client(data["stream"]) as revoker:
                require(revoker.post("/v1/logout").status_code == 204, "STREAM_LOGOUT_FAILED")
            tail = list(iterator)
            require(any("STREAM_AUTHORITY_OR_STORE_UNAVAILABLE" in line for line in tail)
                    and not any(line.startswith("id: ") for line in tail),
                    "REVOKED_STREAM_DISCLOSED")
        require(control.post("/v1/jobs/" + job + "/cancel").status_code == 200,
                "QUEUED_EVENT_FIXTURE_CANCEL_FAILED")
        require(control.get("/v1/jobs/" + job).json()["state"] == "CANCELLED",
                "QUEUED_EVENT_FIXTURE_NOT_CANCELLED")
        print(json.dumps({"checks": ["actual_committed_event_replay", "exact_cursor_resume",
            "terminal204_future_cursor400", "cross_workspace404", "live_logout_closes_no_new_ids",
            "queued_fixture_cancel_without_execution"], "existing_job": data["existing_job"],
            "fixture_job": job, "events": len(ids), "provider_calls": 0}))


if __name__ == "__main__":
    main()

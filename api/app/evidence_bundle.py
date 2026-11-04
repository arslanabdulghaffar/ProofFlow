"""Bounded evidence export. Candidate files are bytes, never imports or programs here."""

import base64
import copy
import difflib
import hashlib
import io
import json
import os
import stat
import zipfile
from pathlib import Path
from uuid import UUID

from api.app.product_store import ProductFailure
from orchestrator.probe_response import ProviderResponseError, strict_json_object

MAX_BUNDLE = 40 * 1024 * 1024
OUTPUT_NAMES = frozenset({"ledger.jsonl", "unresolved.jsonl", "rollups.jsonl"})


def _json(value):
    return json.dumps(value, sort_keys=True, ensure_ascii=True, separators=(",", ":")).encode()


class JournalOutputs:
    """Read-only descriptor walk under the same retention lease as execution writes."""

    def __init__(self, root: Path):
        self.root = root

    def read(self, result):
        import fcntl

        intent = result["intent"]
        execution, job = UUID(intent["execution"]).hex, UUID(intent["job"]).hex
        descriptors = []
        try:
            root = os.open(self.root, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
            descriptors.append(root)
            fcntl.flock(root, fcntl.LOCK_SH | fcntl.LOCK_NB)
            try:
                os.stat(".deleted-" + job, dir_fd=root, follow_symlinks=False)
            except FileNotFoundError:
                pass
            else:
                raise ProductFailure("REPAIR_ARTIFACT_DELETED")
            directory = root
            for part in (execution, "captures", execution):
                directory = os.open(
                    part, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW, dir_fd=directory
                )
                descriptors.append(directory)
                info = os.fstat(directory)
                if info.st_uid != os.geteuid() or stat.S_IMODE(info.st_mode) != 0o700:
                    raise ProductFailure("REPAIR_ARTIFACT_UNSAFE")
            wanted = result["semantic"]["report"]["result"]["output_hashes"]
            if not {"ledger.jsonl", "unresolved.jsonl"} <= wanted.keys() <= OUTPUT_NAMES:
                raise ProductFailure("REPAIR_ARTIFACT_UNSAFE")
            files = {}
            total = 0
            for name, digest in wanted.items():
                fd = os.open(name, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK, dir_fd=directory)
                try:
                    info = os.fstat(fd)
                    if (
                        not stat.S_ISREG(info.st_mode)
                        or info.st_uid != os.geteuid()
                        or info.st_nlink != 1
                        or stat.S_IMODE(info.st_mode) != 0o600
                        or not 0 <= info.st_size <= 10485760
                    ):
                        raise ProductFailure("REPAIR_ARTIFACT_UNSAFE")
                    with os.fdopen(fd, "rb", closefd=False) as stream:
                        raw = stream.read(10485761)
                    total += len(raw)
                    if (
                        total > 10485760
                        or len(raw) != info.st_size
                        or hashlib.sha256(raw).hexdigest() != digest
                    ):
                        raise ProductFailure("REPAIR_ARTIFACT_CHANGED")
                    files[name] = raw
                finally:
                    os.close(fd)
            return files
        except (OSError, KeyError, TypeError, ValueError):
            raise ProductFailure("REPAIR_ARTIFACT_UNAVAILABLE") from None
        finally:
            for fd in reversed(descriptors):
                os.close(fd)


def build_bundle(record, workspace, assets, journals):
    """One authenticated snapshot, reauthorized by caller before returning bytes."""
    files = {}
    source = {}
    for asset in record["assets"]:
        raw = assets.read(workspace, asset["sha256"])
        if len(raw) != asset["bytes"]:
            raise ProductFailure("REPAIR_ARTIFACT_CHANGED")
        source[asset["kind"]] = raw
    if source.keys() != {"pipeline", "contract", "transactions", "customers"}:
        raise ProductFailure("REPAIR_ARTIFACT_UNAVAILABLE")
    files["original/pipeline.py"] = source["pipeline"]
    for name in ("contract", "transactions", "customers"):
        files["input/" + name + (".json" if name == "contract" else ".csv")] = source[name]
    for candidate in record["candidates"]:
        ordinal = candidate["ordinal"]
        if type(ordinal) is not int or not 0 <= ordinal <= 3:
            raise ProductFailure("REPAIR_ARTIFACT_UNSAFE")
        raw = candidate["source"].encode("utf-8")
        if not 0 < len(raw) <= 16384:
            raise ProductFailure("REPAIR_ARTIFACT_UNSAFE")
        files[f"candidate/attempt-{ordinal}.py"] = raw
    latest = record["candidates"][-1] if record["candidates"] else None
    if latest is not None:
        files["candidate/pipeline.py"] = latest["source"].encode()
        files["candidate/patch.diff"] = "".join(
            difflib.unified_diff(
                source["pipeline"].decode("utf-8").splitlines(keepends=True),
                latest["source"].splitlines(keepends=True),
                fromfile="original/pipeline.py",
                tofile="candidate/pipeline.py",
            )
        ).encode()
    original = record["original"]["report"]
    files["original/report.json"] = _json(original)
    for name, raw in journals.read(original).items():
        files["original/output/" + name] = raw
    executions = copy.deepcopy(record["executions"])
    candidate_runs = [e for e in executions if e["purpose"] == "candidate" and e["result"]]
    if candidate_runs:
        last = candidate_runs[-1]["result"]
        semantic = (last.get("semantic") or {}).get("report", {}).get("result", {})
        if semantic.get("output_hashes"):
            label = "output" if semantic.get("comparison") == "match" else "failed-output"
            for name, raw in journals.read(last).items():
                files[
                    "candidate/attempt-"
                    + str(candidate_runs[-1]["attempt"])
                    + "/"
                    + label
                    + "/"
                    + name
                ] = raw
    for execution in executions:
        if execution["purpose"] != "candidate" and execution["result"]:
            result = execution["result"]
            semantic = result.get("semantic")
            if semantic and "result" in semantic.get("report", {}):
                checked = semantic["report"]["result"]
                semantic["report"]["result"] = {
                    k: checked[k]
                    for k in (
                        "operation",
                        "comparison",
                        "blocking_occurrences",
                        "finding_count",
                        "contract_sha256",
                        "transactions_sha256",
                        "customers_sha256",
                        "output_hashes",
                    )
                    if k in checked
                }
    calls = []
    for raw_call in record["calls"]:
        call = {k: v for k, v in raw_call.items() if k != "response_base64"}
        if raw_call["response_base64"]:
            try:
                response = strict_json_object(
                    base64.b64decode(raw_call["response_base64"].replace("\n", ""), validate=True),
                    max_bytes=262144,
                )
                call.update(
                    provider_id=response.get("id"),
                    model=response.get("model"),
                    reported_usage=response.get("usage"),
                )
            except (ProviderResponseError, ValueError):
                call["reported_usage"] = None
        calls.append(call)
    files["repair/receipts.json"] = _json(executions)
    files["repair/provider-calls.json"] = _json(calls)
    files["repair/summary.json"] = _json(record["repair"])
    files["original/events.json"] = _json(record["original_events"])
    files["REPLAY.txt"] = (
        b"ProofFlow evidence v1. Files are untrusted data; never execute them locally.\n"
        b"Replay on the designated isolated worker through authenticated intake: upload the exact\n"
        b"candidate/pipeline.py and input files, approve the exact contract, run original, then\n"
        b"check the unchanged source with fresh canaries. This path makes zero model calls.\n"
        b"Pin the same runtime/verifier; compare captured output hashes to receipts.\n"
        b"Canary bytes stay private. Redacted receipts retain their hashes.\n"
        b"A match is input-specific evidence, not formal proof, activation or a new batch.\n"
        b"Failed-output is rejected evidence. Original files retain the faulty baseline.\n"
    )
    if sum(map(len, files.values())) > MAX_BUNDLE - 1048576:
        raise ProductFailure("REPAIR_BUNDLE_LIMIT")
    manifest = {
        "version": "proofflow-evidence-v1",
        "repair_id": record["repair"]["id"],
        "state": record["repair"]["state"],
        "mode": record["repair"]["mode"],
        "activation_approved": False,
        "selected_candidate_ordinal": latest["ordinal"] if latest is not None else None,
        "candidate_verified": record["repair"]["state"] == "AWAITING_APPROVAL",
        "protected_canary_material_included": False,
        "files": [
            {"path": name, "bytes": len(raw), "sha256": hashlib.sha256(raw).hexdigest()}
            for name, raw in sorted(files.items())
        ],
    }
    files["manifest.json"] = _json(manifest)
    output = io.BytesIO()
    with zipfile.ZipFile(output, "w", compression=zipfile.ZIP_STORED) as archive:
        for name, raw in sorted(files.items()):
            info = zipfile.ZipInfo(name, date_time=(1980, 1, 1, 0, 0, 0))
            info.external_attr = (stat.S_IFREG | 0o444) << 16
            archive.writestr(info, raw)
    result = output.getvalue()
    if len(result) > MAX_BUNDLE:
        raise ProductFailure("REPAIR_BUNDLE_LIMIT")
    return result

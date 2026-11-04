"""Finite trusted-verifier byte protocol. No code, paths, URLs or runtime selector."""

import base64
import binascii
import hashlib

from contracts.codec import InputError, canonical_bytes, parse_object
from contracts.policy import parse_contract
from contracts.source import MAX_CSV_BYTES, parse_sources
from verifier.canaries import generate
from verifier.compare import compare_bytes
from verifier.outputs import MAX_OUTPUT_BYTES

MAX_REQUEST = 29 * 1024 * 1024
MAX_RESPONSE = 15 * 1024 * 1024
VERSION = "proofflow-verifier-v1"


def sha(raw):
    return hashlib.sha256(raw).hexdigest()


def encode(raw):
    return base64.b64encode(raw).decode("ascii")


def decode(value, maximum):
    if type(value) is not str or len(value) > 4 * ((maximum + 2) // 3):
        raise InputError("VERIFIER_FIELD_LIMIT")
    try:
        result = base64.b64decode(value, validate=True)
    except (ValueError, binascii.Error):
        raise InputError("VERIFIER_BASE64_INVALID") from None
    if len(result) > maximum or encode(result) != value:
        raise InputError("VERIFIER_BASE64_INVALID")
    return result


def process(raw: bytes) -> bytes:
    """Called only inside the bounded process in deployment; unit tests use data."""
    request_hash = sha(raw)
    try:
        request = parse_object(raw, max_bytes=MAX_REQUEST)
        op = request.get("operation")
        fields = {"operation", "contract"}
        if op == "canary":
            fields |= {"seed", "case"}
        elif op in ("prepare", "verify"):
            fields |= {"transactions", "customers"}
            if op == "verify":
                fields.add("outputs")
        else:
            raise InputError("VERIFIER_OPERATION_INVALID")
        if set(request) != fields:
            raise InputError("VERIFIER_FIELDS_INVALID")
        contract_raw = decode(request["contract"], 32768)
        contract = parse_contract(contract_raw)
        if op == "canary":
            tx, cs = generate(contract, request["seed"], request["case"])
        else:
            tx = decode(request["transactions"], MAX_CSV_BYTES)
            cs = decode(request["customers"], MAX_CSV_BYTES)
        result = {"operation": op, "contract_sha256": contract.sha256,
                  "transactions_sha256": sha(tx), "customers_sha256": sha(cs)}
        if op in ("prepare", "canary"):
            parsed_tx, parsed_cs = parse_sources(tx, cs, aliases=dict(contract.aliases),
                                               customer_attributes=contract.attributes)
            result.update(transactions_jsonl=encode(parsed_tx.worker_jsonl()),
                          customers_jsonl=encode(parsed_cs.worker_jsonl()),
                          requirements=encode(contract.canonical), include_rollups=contract.rollups)
            if op == "canary":
                result.update(transactions_csv=encode(tx), customers_csv=encode(cs),
                              case=request["case"], seed_sha256=sha(bytes.fromhex(request["seed"])))
        else:
            outputs = request["outputs"]
            if (type(outputs) is not dict
                    or not set(outputs) <= {"ledger.jsonl", "unresolved.jsonl", "rollups.jsonl"}):
                raise InputError("VERIFIER_OUTPUT_NAMES_INVALID")
            files = {name: decode(value, MAX_OUTPUT_BYTES) for name, value in outputs.items()}
            if sum(map(len, files.values())) > MAX_OUTPUT_BYTES:
                raise InputError("VERIFIER_OUTPUT_LIMIT")
            compared = compare_bytes(tx, cs, contract_raw, files)
            result.update(output_hashes=dict(compared.output_hashes),
                          comparison="mismatch" if compared.findings else "match",
                          blocking_occurrences=compared.expected.blocking_occurrences,
                          ledger_count=len(compared.expected.ledger),
                          unresolved_count=len(compared.expected.unresolved),
                          finding_count=len(compared.findings),
                          findings=[{"check": f.check_id, "code": f.code, "source": f.source_row_id}
                                    for f in compared.findings[:20]])
        response = {"version": VERSION, "request_sha256": request_hash,
                    "status": "processed", "result": result}
    except InputError as error:
        response = {"version": VERSION, "request_sha256": request_hash,
                    "status": "rejected", "code": str(error)}
    return canonical_bytes(response, max_bytes=MAX_RESPONSE)

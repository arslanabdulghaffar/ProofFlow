"""Twelve disclosed synthetic development cases. Never final/held-out data.

Returns source as inert bytes only. Never compile/import/execute these payloads on
the development machine, controller or verifier. Reuses disclosed canary data shape;
it cannot demonstrate generalization to independent customer problems.
"""

import hashlib
import json
from collections import Counter
from pathlib import Path

from contracts.codec import canonical_bytes
from contracts.policy import parse_contract
from contracts.source import parse_csv
from eval.report import FAMILIES, digest
from verifier.canaries import generate
from verifier.reference import derive

ROOT = Path(__file__).resolve().parents[1]


def replace_once(source, before, after):
    if source.count(before) != 1:
        raise ValueError("DEVELOPMENT_FIXTURE_SOURCE_CHANGED")
    return source.replace(before, after)


def cases():
    template = (ROOT / "tests/fixtures/phase2/canary_correct.py.txt").read_text(encoding="utf-8")
    faults = {
        "schema": [("joined[0]['canonical_customer_id']", "joined[0]['legacy_owner_id']")],
        "units": [("int(Decimal(tx['amount']) * factor)", "int(Decimal(tx['amount']))")],
        "joins": [("lookup[(c['merchant_id'], c['customer_id'])]", "lookup[c['customer_id']]"),
                  ("lookup[(tx['merchant_id'], tx['customer_id'])]", "lookup[tx['customer_id']]")],
        "duplicates": [("representative = min(group", "representative = max(group")],
        "completeness": [("    reason = None", "    if Decimal(tx['amount']) <= 0: continue\n"
                                              "    reason = None")],
        "downstream": [("{attr: joined[0][attr] for attr in policy['customer_attributes']}", "{}")],
    }
    results = []
    for family in FAMILIES:
        for kind in ("repairable", "ambiguous"):
            name = family + "-" + kind
            contract = json.loads((ROOT / "contracts/examples/synthetic-v1.1.json").read_bytes())
            if family == "units":
                # Exercise fractional major units, not the generator's first
                # alphabetic currency (JPY), whose exponent zero masks this fault.
                contract["currency_exponents"] = {"USD": 2}
            if family == "downstream":
                contract["downstream"].update(customer_attributes=["segment"],
                    occurred_at_from_utc="2026-11-04T00:00:00.000000Z",
                    occurred_at_before_utc="2026-11-05T00:00:00.000000Z",
                    rollup="merchant_currency")
            if family == "schema":
                contract["column_aliases"] = {"seller": "merchant_id", "value": "amount"}
            policy = parse_contract(canonical_bytes(contract))
            txs, customers = generate(policy, digest({"development_case": name}),
                                      "ownership" if kind == "repairable" else "quarantine")
            source = template
            for before, after in faults[family]:
                source = replace_once(source, before, after)
            files = {"pipeline.py.txt": source.encode(), "contract.json": policy.canonical,
                     "transactions.csv": txs, "customers.csv": customers}
            hashes = {key: hashlib.sha256(raw).hexdigest() for key, raw in files.items()}
            # Small arithmetic expectations authored before any model run. They
            # constrain data semantics, not whether the faulty original crashes.
            reasons = {"DUPLICATE_EXACT": 1}
            if kind == "ambiguous":
                reasons.update(CONFLICTING_DUPLICATE=2, MISSING_CUSTOMER=1, AMBIGUOUS_CUSTOMER=1)
                if family == "downstream":
                    reasons.update(MISSING_ATTRIBUTE=1, FILTERED_BY_CONTRACT=1)
            oracle = {"ledger_rows": 3, "unresolved_reasons": reasons,
                      "blocking_occurrences": (5 if family == "downstream" else 4)
                      if kind == "ambiguous" else 0,
                      "net_minor_units": 0}
            results.append({"id": name, "family": family, "kind": kind, "files": files,
                            "sha256": digest({"files": hashes, "oracle": oracle}),
                            "file_hashes": hashes, "oracle_summary": oracle})
    return results


def check_oracle(case):
    """Parse source data and compare independent count arithmetic; no payload execution."""
    files = case["files"]
    policy = parse_contract(files["contract.json"])
    aliases = dict(policy.aliases)
    txs = parse_csv(files["transactions.csv"], kind="transactions", aliases=aliases)
    customers = parse_csv(files["customers.csv"], kind="customers", aliases=aliases,
                          customer_attributes=policy.attributes)
    expected = derive(txs, customers, policy)
    actual = {"ledger_rows": len(expected.ledger),
              "unresolved_reasons": dict(Counter(r["reason_code"] for r in expected.unresolved)),
              "blocking_occurrences": expected.blocking_occurrences,
              "net_minor_units": sum(r["amount_minor"] for r in expected.ledger)}
    if actual != case["oracle_summary"]:
        raise ValueError("DEVELOPMENT_ORACLE_DISAGREEMENT")
    return actual


def inventory():
    result = []
    for case in cases():
        check_oracle(case)
        result.append({k: v for k, v in case.items() if k != "files"})
    return {"scope": "disclosed_canary_derived_development_only", "cases": result,
            "candidate_executions": "NOT_RUN_BY_THIS_CHECK", "model_calls": 0,
            "manual_owner_oracle_review": "NOT_AVAILABLE"}


if __name__ == "__main__":
    print(json.dumps(inventory(), sort_keys=True, indent=2))

"""V02–V04 independent source accounting/ownership checks, not a full verdict.

Money, timestamp normalization, duplicate/filter eligibility, reason precedence,
rollups, canaries, execution provenance and approvals remain separate gates.
"""

from collections import Counter, defaultdict
from dataclasses import dataclass

from contracts.codec import InputError
from contracts.source import ParsedTable
from verifier.outputs import DecodedOutputs


@dataclass(frozen=True)
class Finding:
    check_id: str
    code: str
    source_row_id: str


def check_lineage(transactions: ParsedTable, customers: ParsedTable,
                  outputs: DecodedOutputs) -> tuple[Finding, ...]:
    """Inputs must come from the bounded source/output decoders.

    Empty findings means only these three checks found no violation. No verified
    report, activation, completion state or external action is produced here.
    """
    if transactions.kind != "transactions" or customers.kind != "customers":
        raise InputError("LINEAGE_SOURCE_KIND_INVALID")
    source = {transactions.transaction_row_id(ordinal): dict(zip(transactions.columns, row,
                                                                 strict=True))
              for ordinal, row in enumerate(transactions.rows, 1)}
    lookup = defaultdict(list)
    for row in customers.rows:
        customer = dict(zip(customers.columns, row, strict=True))
        lookup[(customer["merchant_id"], customer["customer_id"])].append(customer)
    counts = Counter(row["source_row_id"] for row in outputs.ledger + outputs.unresolved)
    findings = []
    for identifier in source:
        if counts[identifier] != 1:
            findings.append(Finding("V02", "SOURCE_OCCURRENCE_COUNT", identifier))
    for identifier in counts.keys() - source.keys():
        findings.append(Finding("V02", "FOREIGN_SOURCE_OCCURRENCE", identifier))
    for row in outputs.ledger:
        identifier = row["source_row_id"]
        expected = source.get(identifier)
        if expected is None:
            continue
        identity = ("merchant_id", "transaction_id", "customer_id")
        if any(not 1 <= len(expected[key]) <= 128 or row[key] != expected[key]
               for key in identity):
            findings.append(Finding("V03", "SOURCE_IDENTITY_MISMATCH", identifier))
        # Crucially derive the lookup from original source, never candidate IDs.
        matches = lookup[(expected["merchant_id"], expected["customer_id"])]
        if len(matches) != 1:
            findings.append(Finding("V04", "CUSTOMER_LOOKUP_NOT_UNIQUE", identifier))
        elif (not 1 <= len(matches[0]["canonical_customer_id"]) <= 128
              or row["canonical_customer_id"] != matches[0]["canonical_customer_id"]):
            findings.append(Finding("V04", "CANONICAL_CUSTOMER_MISMATCH", identifier))
    # Stable order independent of hash randomization/candidate file order.
    return tuple(sorted(set(findings), key=lambda item: (item.check_id, item.source_row_id,
                                                        item.code)))

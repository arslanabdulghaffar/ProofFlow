"""Independent source derivation for the owner-approved synthetic contract.

No candidate output, model text, external tool, execution, or candidate import is
used. Internal results are evidence, not a version/activation approval.
"""

from collections import defaultdict
from dataclasses import dataclass

from contracts.codec import InputError
from contracts.policy import Contract
from contracts.scalars import AMOUNT, amount_minor, timestamp_utc
from contracts.source import TRANSACTION_FIELDS, ParsedTable

PRECEDENCE = (
    "MISSING_IDENTITY", "UNKNOWN_UNIT", "INVALID_CURRENCY", "INVALID_AMOUNT", "INVALID_TIMESTAMP",
    "CONFLICTING_DUPLICATE", "AMBIGUOUS_CUSTOMER", "MISSING_CUSTOMER", "MISSING_ATTRIBUTE",
    "FILTERED_BY_CONTRACT", "DUPLICATE_EXACT",
)
NONBLOCKING = frozenset({"FILTERED_BY_CONTRACT", "DUPLICATE_EXACT"})


@dataclass(frozen=True)
class SourceFact:
    source_row_id: str
    violations: tuple[str, ...]
    failed_filters: tuple[str, ...]


@dataclass(frozen=True)
class ExpectedBatch:
    ledger: tuple[dict, ...]
    unresolved: tuple[dict, ...]
    rollups: tuple[dict, ...] | None
    facts: tuple[SourceFact, ...]
    blocking_occurrences: int


def _identifier(value):
    return 1 <= len(value) <= 128


def derive(transactions: ParsedTable, customers: ParsedTable, contract: Contract) -> ExpectedBatch:
    """Only parsed immutable sources and a validated, immutable Contract enter."""
    rows = [dict(zip(transactions.columns, row, strict=True)) for row in transactions.rows]
    customer_rows = [dict(zip(customers.columns, row, strict=True)) for row in customers.rows]
    lookup = defaultdict(list)
    for customer in customer_rows:
        lookup[(customer["merchant_id"], customer["customer_id"])].append(customer)
    groups = defaultdict(list)
    for index, row in enumerate(rows):
        if all(_identifier(row[key]) for key in ("merchant_id", "transaction_id")):
            groups[(row["merchant_id"], row["transaction_id"])].append(index)
    conflicts, representatives = set(), {}
    for members in groups.values():
        raw_values = {tuple(rows[index][key] for key in TRANSACTION_FIELDS) for index in members}
        if len(raw_values) > 1:
            conflicts.update(members)
        for index in members:
            representatives[index] = members[0]
    exponents = dict(contract.exponents)
    ledger, unresolved, facts = [], [], []
    blocking = 0
    for index, row in enumerate(rows):
        identifier = transactions.transaction_row_id(index + 1)
        violations, failed_filters = set(), []
        if any(not _identifier(row[key])
               for key in ("merchant_id", "transaction_id", "customer_id")):
            violations.add("MISSING_IDENTITY")
        minor, occurred = None, None
        if row["currency"] not in exponents:
            violations.add("INVALID_CURRENCY")
            # No exponent is invented for an unknown currency. Independently
            # malformed number syntax can still be diagnosed without one.
            match = AMOUNT.fullmatch(row["amount"])
            if match is None or (contract.amount_unit == "integer_minor" and match.group(3)):
                violations.add("INVALID_AMOUNT")
        else:
            try:
                minor = amount_minor(row["amount"], unit=contract.amount_unit,
                                     exponent=exponents[row["currency"]])
            except InputError as error:
                violations.add(str(error))
        try:
            occurred = timestamp_utc(row["occurred_at"])
        except InputError:
            violations.add("INVALID_TIMESTAMP")
        if index in conflicts:
            violations.add("CONFLICTING_DUPLICATE")
        customer = None
        if all(_identifier(row[key]) for key in ("merchant_id", "customer_id")):
            matches = lookup[(row["merchant_id"], row["customer_id"])]
            if not matches:
                violations.add("MISSING_CUSTOMER")
            elif len(matches) > 1:
                violations.add("AMBIGUOUS_CUSTOMER")
            else:
                customer = matches[0]
                if not _identifier(customer["canonical_customer_id"]):
                    violations.add("MISSING_IDENTITY")
                # Q08: inspect attributes even when a date/currency filter will exclude.
                if any(not customer[name] for name in contract.attributes):
                    violations.add("MISSING_ATTRIBUTE")
        if (contract.include_currencies is not None
                and row["currency"] not in contract.include_currencies):
            failed_filters.append("include_currencies")
        if occurred is not None and contract.from_utc is not None:
            if occurred < contract.from_utc:
                failed_filters.append("occurred_at_from_utc")
            if occurred >= contract.before_utc:
                failed_filters.append("occurred_at_before_utc")
        if failed_filters:
            violations.add("FILTERED_BY_CONTRACT")
        if not violations and representatives.get(index, index) != index:
            violations.add("DUPLICATE_EXACT")
        ordered = tuple(reason for reason in PRECEDENCE if reason in violations)
        facts.append(SourceFact(identifier, ordered, tuple(failed_filters)))
        if ordered:
            primary = ordered[0]
            record = {"source_row_id": identifier, "reason_code": primary}
            if primary == "DUPLICATE_EXACT":
                record["duplicate_of_source_row_id"] = transactions.transaction_row_id(
                    representatives[index] + 1)
            unresolved.append(record)
            blocking += int(primary not in NONBLOCKING)
        else:
            ledger.append({"source_row_id": identifier, "merchant_id": row["merchant_id"],
                           "transaction_id": row["transaction_id"],
                           "customer_id": row["customer_id"],
                           "canonical_customer_id": customer["canonical_customer_id"],
                           "amount_minor": minor, "currency": row["currency"],
                           "occurred_at_utc": occurred,
                           "attributes": {name: customer[name] for name in contract.attributes}})
    aggregates = defaultdict(lambda: [0, 0])
    for record in ledger:
        bucket = aggregates[(record["merchant_id"], record["currency"])]
        bucket[0] += 1
        bucket[1] += record["amount_minor"]
    rollups = tuple({"merchant_id": merchant, "currency": currency, "transaction_count": values[0],
                    "amount_minor_total": str(values[1])}
                   for (merchant, currency), values in sorted(aggregates.items()))
    return ExpectedBatch(tuple(ledger), tuple(unresolved), rollups if contract.rollups else None,
                         tuple(facts), blocking)

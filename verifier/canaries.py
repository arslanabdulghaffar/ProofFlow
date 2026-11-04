"""Protected synthetic challenges. Seeds are controller secrets, never model input.

This generator contains no candidate code or caller-provided expected answers.
Each generated source is subsequently verified by the normal source comparator.
"""

import csv
import hashlib
import io
import re

from contracts.codec import InputError
from contracts.policy import Contract
from contracts.source import CUSTOMER_FIELDS, TRANSACTION_FIELDS


def generate(contract: Contract, seed: str, case: str) -> tuple[bytes, bytes]:
    if (type(seed) is not str or re.fullmatch(r"[0-9a-f]{64}", seed) is None
            or case not in ("ownership", "quarantine")):
        raise InputError("CANARY_REQUEST_INVALID")

    def name(label):
        return hashlib.sha256(bytes.fromhex(seed) + case.encode() + label.encode()).hexdigest()[:24]

    a, b, c = name("merchant-a"), name("merchant-b"), name("shared-customer")
    currency = (contract.include_currencies or tuple(dict(contract.exponents)))[0]
    exponent = dict(contract.exponents)[currency]
    instant = contract.from_utc or "2026-11-04T00:00:00.000000Z"

    def amount(minor):
        if contract.amount_unit == "integer_minor" or exponent == 0:
            return str(minor)
        whole, fraction = divmod(abs(minor), 10 ** exponent)
        return ("-" if minor < 0 else "") + f"{whole}.{fraction:0{exponent}d}"

    customers = [[a, c, name("owner-a"), *[name(attr) for attr in contract.attributes]],
                 [b, c, name("owner-b"), *[name(attr) for attr in contract.attributes]]]
    transactions = [[a, name("sale"), c, amount(123), currency, instant],
                    [b, name("refund"), c, amount(-123), currency, instant],
                    [a, name("zero"), c, amount(0), currency, instant]]
    transactions.append(transactions[0].copy())
    if case == "quarantine":
        # A conflicting group, a missing customer, and an ambiguous lookup.
        conflict = [a, name("conflict"), c, amount(1), currency, instant]
        transactions.extend([conflict, [*conflict[:3], amount(2), *conflict[4:]]])
        transactions.append([a, name("missing"), name("absent"), amount(3), currency, instant])
        ambiguous = name("ambiguous")
        customers.extend([[a, ambiguous, name("owner-c"),
                           *[name(attr) for attr in contract.attributes]]] * 2)
        transactions.append([a, name("ambiguous-tx"), ambiguous, amount(4), currency, instant])
        if contract.attributes:
            missing = name("missing-attribute")
            customers.append([a, missing, name("owner-d"), *["" for _ in contract.attributes]])
            transactions.append([a, name("attribute-tx"), missing, amount(5), currency,
                                 contract.before_utc or instant])
        if contract.before_utc:
            transactions.append([a, name("excluded"), c, amount(6), currency,
                                 contract.before_utc])
        excluded = sorted(set(dict(contract.exponents)) - set(contract.include_currencies or
                                                              dict(contract.exponents)))
        if excluded:
            transactions.append([a, name("currency-filter"), c, "0", excluded[0], instant])

    # Hash ordering is deterministic for replay but changes with fresh secret entropy.
    transactions.sort(key=lambda row: name(repr(row)))
    customers.sort(key=lambda row: name(repr(row)))
    aliases = dict(contract.aliases)
    inverse = {target: source for source, target in aliases.items()}

    def encode(fields, rows):
        stream = io.StringIO(newline="")
        writer = csv.writer(stream, lineterminator="\n")
        writer.writerow([inverse.get(field, field) for field in fields])
        writer.writerows(rows)
        return stream.getvalue().encode()

    return (encode(TRANSACTION_FIELDS, transactions),
            encode((*CUSTOMER_FIELDS, *contract.attributes), customers))

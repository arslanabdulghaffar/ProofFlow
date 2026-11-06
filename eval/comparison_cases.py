"""New synthetic comparison inputs, independent of the canary data generator.

Programs are inert bytes. Never import, compile or execute them here. Small source
oracles are hand-derived counts/sums, then checked against the existing verifier.
This is synthetic prospective evaluation, not human-reviewed customer evidence.
"""

import csv
import hashlib
import io
import json
from collections import Counter
from pathlib import Path

from contracts.codec import InputError, canonical_bytes
from contracts.policy import parse_contract
from contracts.source import parse_csv
from eval.development import replace_once
from eval.report import FAMILIES, digest
from verifier.reference import derive

ROOT = Path(__file__).resolve().parents[1]
TX_FIELDS = ('merchant_id', 'transaction_id', 'customer_id', 'amount', 'currency', 'occurred_at')
CS_FIELDS = ('merchant_id', 'customer_id', 'canonical_customer_id')


def csv_bytes(rows, fields, aliases):
    reverse = {target: source for source, target in aliases.items()}
    out = io.StringIO(newline='')
    writer = csv.writer(out, lineterminator='\n')
    writer.writerow([reverse.get(f, f) for f in fields])
    writer.writerows([[row[f] for f in fields] for row in rows])
    return out.getvalue().encode()


def faulty_source(template, family, variant):
    replacements = {
        'schema': [
            [("joined[0]['canonical_customer_id']", "joined[0]['legacy_owner']")],
            [("tx['customer_id'],\n                       'canonical_customer_id'",
              "tx['legacy_customer_id'],\n                       'canonical_customer_id'")],
            [("'amount_minor': int(Decimal(tx['amount']) * factor)",
              "'amount_minor': str(int(Decimal(tx['amount']) * factor))")]],
        'units': [
            [("int(Decimal(tx['amount']) * factor)", "int(Decimal(tx['amount']))")],
            [("int(Decimal(tx['amount']) * factor)", "int(Decimal(tx['amount'])) * factor")],
            [("int(Decimal(tx['amount']) * factor)", "abs(int(Decimal(tx['amount']) * factor))")]],
        'joins': [
            [("lookup[(c['merchant_id'], c['customer_id'])]", "lookup[c['customer_id']]"),
             ("lookup[(tx['merchant_id'], tx['customer_id'])]", "lookup[tx['customer_id']]")],
            [("joined[0]['canonical_customer_id']", "tx['customer_id']")],
            [("joined[0]['canonical_customer_id']", "customers[-1]['canonical_customer_id']")]],
        'duplicates': [
            [("representative = min(group", "representative = max(group")],
            [("    if reason:\n",
              "    if reason == 'DUPLICATE_EXACT': continue\n    if reason:\n")],
            [("item['duplicate_of_source_row_id'] = representative['source_row_id']",
              "item['duplicate_of_source_row_id'] = tx['source_row_id']")]],
        'completeness': [
            [("    reason = None",
              "    if Decimal(tx['amount']) <= 0: continue\n    reason = None")],
            [("ledger, unresolved = [], []\nfor tx in txs:",
              "ledger, unresolved = [], []\nfor tx in txs[1:]:")],
            [("for name, rows in [('ledger', ledger)",
              "ledger.extend(ledger[:1])\nfor name, rows in [('ledger', ledger)")]],
        'downstream': [
            [("{attr: joined[0][attr] for attr in policy['customer_attributes']}", "{}")],
            [("'transaction_count': count", "'transaction_count': count + 1")],
            [("not policy['occurred_at_from_utc'] <= utc < policy['occurred_at_before_utc']",
              "False")]],
    }
    source = template
    for before, after in replacements[family][variant]:
        source = replace_once(source, before, after)
    return source.encode()


def cases(seed):
    if type(seed) is not str or len(seed) != 64 or any(c not in '0123456789abcdef' for c in seed):
        raise ValueError('COMPARISON_SEED_INVALID')
    template = (ROOT / 'tests/fixtures/phase2/canary_correct.py.txt').read_text(encoding='utf-8')
    result = []
    for family in FAMILIES:
        for variant in range(4):
            kind = 'ambiguous' if variant == 3 else 'repairable'
            name = f'{family}-{variant + 1}'
            token = hashlib.sha256((seed + name).encode()).hexdigest()[:10]
            east, west, shared = 'east-' + token, 'west-' + token, '000-' + token
            p, n, q = 12345 + 37 * variant, -2367 - 13 * variant, 2159 + 29 * variant
            contract = json.loads((ROOT / 'contracts/examples/synthetic-v1.1.json').read_bytes())
            contract['currency_exponents'] = {'USD': 2, 'JPY': 0}
            contract['amount_unit'] = 'integer_minor' if variant == 2 else 'decimal_major'
            def amount(value, currency, unit=contract['amount_unit']):
                if unit == 'integer_minor' or currency == 'JPY':
                    return str(value)
                sign = '-' if value < 0 else ''
                return sign + str(abs(value) // 100) + '.' + str(abs(value) % 100).zfill(2)

            rows = [dict(zip(TX_FIELDS, values, strict=True)) for values in (
                (east, 'first-' + token, shared, amount(p, 'USD'), 'USD',
                 '2026-11-02T09:00:00+09:00'),
                (west, 'refund-' + token, shared, amount(n, 'USD'), 'USD',
                 '2026-11-02T23:59:59.999999Z'),
                (east, 'zero-' + token, 'other-' + token, amount(0, 'USD'), 'USD',
                 '2026-11-03T00:00:00Z'),
                (west, 'yen-' + token, shared, amount(q, 'JPY'), 'JPY',
                 '2026-11-01T23:59:59.999999Z'))]
            customers = [dict(zip(CS_FIELDS, values, strict=True)) for values in (
                (east, shared, 'owner-east-' + token), (west, shared, 'owner-west-' + token),
                (east, 'other-' + token, 'owner-zero-' + token))]
            reasons, count, blocked, total = {'DUPLICATE_EXACT': 1}, 4, 0, p + n + q
            if family == 'schema':
                contract['column_aliases'] = {'店': 'merchant_id', 'net value': 'amount',
                                            'owner ref': 'canonical_customer_id'}
            if family == 'downstream':
                contract['downstream'].update(customer_attributes=['segment'],
                    occurred_at_from_utc='2026-11-02T00:00:00.000000Z',
                    occurred_at_before_utc='2026-11-03T00:00:00.000000Z',
                    include_currencies=None, rollup='merchant_currency')
                for i, row in enumerate(customers):
                    row['segment'] = ['retail,local', 'web\npriority', 'zero'][i]
                reasons, count, total = {'DUPLICATE_EXACT': 1, 'FILTERED_BY_CONTRACT': 2}, 2, p + n
            if kind == 'ambiguous':
                if family == 'units':
                    # Unknown units are not guessed. Contract intake must request
                    # clarification; do not manufacture an owner-approved policy.
                    contract['amount_unit'] = None
                elif family == 'schema':
                    customers.append({**customers[0], 'canonical_customer_id': 'conflicting-owner'})
                    reasons, count, blocked, total = {'AMBIGUOUS_CUSTOMER': 2}, 3, 2, n + q
                elif family == 'joins':
                    customers.pop(0)
                    reasons, count, blocked, total = {'MISSING_CUSTOMER': 2}, 3, 2, n + q
                elif family == 'duplicates':
                    reasons, count, blocked, total = {'CONFLICTING_DUPLICATE': 3}, 3, 3, n + q
                elif family == 'completeness':
                    rows[0]['currency'] = 'XXX'
                    reasons, count, blocked, total = {'INVALID_CURRENCY': 2}, 3, 2, n + q
                else:
                    customers[0]['segment'] = ''
                    rows[0]['occurred_at'] = '2026-11-01T23:59:59.000000Z'
                    reasons, count, blocked, total = {
                        'MISSING_ATTRIBUTE': 2, 'FILTERED_BY_CONTRACT': 2}, 1, 2, n
            rows.append(dict(rows[0]))
            if family == 'duplicates' and kind == 'ambiguous':
                rows.append({**rows[0], 'amount': amount(p + 1, 'USD')})
            fields = TX_FIELDS[variant % 6:] + TX_FIELDS[:variant % 6]
            customer_fields = CS_FIELDS + (('segment',) if family == 'downstream' else ())
            files = {'pipeline.py.txt': faulty_source(template, family, variant % 3),
                     'contract.json': canonical_bytes(contract),
                     'transactions.csv': csv_bytes(rows, fields, contract['column_aliases']),
                     'customers.csv': csv_bytes(customers, customer_fields,
                                                contract['column_aliases'])}
            oracle = {'ledger_rows': count, 'unresolved_reasons': reasons,
                      'blocking_occurrences': blocked, 'net_minor_units': total}
            if family == 'units' and kind == 'ambiguous':
                oracle = {'contract_rejected': True, 'clarification': 'amount_unit'}
            hashes = {k: hashlib.sha256(v).hexdigest() for k, v in files.items()}
            result.append({'id': name, 'family': family, 'kind': kind, 'files': files,
                           'file_hashes': hashes, 'oracle_summary': oracle,
                           'sha256': digest({'files': hashes, 'oracle': oracle})})
    return result


def check_oracle(case):
    files, oracle = case['files'], case['oracle_summary']
    if oracle.get('contract_rejected'):
        try:
            parse_contract(files['contract.json'])
        except InputError as error:
            if str(error) != 'UNKNOWN_UNIT':
                raise
            return oracle
        raise ValueError('UNDECLARED_UNITS_ACCEPTED')
    policy = parse_contract(files['contract.json'])
    txs = parse_csv(files['transactions.csv'], kind='transactions', aliases=dict(policy.aliases))
    cs = parse_csv(files['customers.csv'], kind='customers', aliases=dict(policy.aliases),
                   customer_attributes=policy.attributes)
    expected = derive(txs, cs, policy)
    actual = {'ledger_rows': len(expected.ledger),
              'unresolved_reasons': dict(Counter(r['reason_code'] for r in expected.unresolved)),
              'blocking_occurrences': expected.blocking_occurrences,
              'net_minor_units': sum(r['amount_minor'] for r in expected.ledger)}
    if actual != oracle:
        raise ValueError('COMPARISON_ORACLE_DISAGREEMENT:' + case['id'])
    return actual

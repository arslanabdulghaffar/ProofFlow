"""One real guest AI repair in an expiring window; synthetic test approvals, no PR."""

import hashlib
import json
from datetime import UTC, datetime
from uuid import UUID, uuid4

from check_phase6_browser import version_rehearsal
from guest_demo import client_for, current, host, sign_in_and_stage, start, stop
from guest_demo_access import load
from playwright.sync_api import expect, sync_playwright
from product_live_session import require
from vultr_phase1 import PRIVATE, Admin


def counts():
    admin = Admin()
    try:
        statement = ("SELECT json_build_object('calls',"
                     "(SELECT count(*) FROM pf_product.repair_calls),"
                     "'prs',(SELECT count(*) FROM pf_product.pr_intents),"
                     "'assets',(SELECT count(*) FROM pf_product.assets),"
                     "'approvals',(SELECT count(*) FROM pf_product.contract_approvals));")
        return json.loads(host(admin, 'docker exec -i --user=70:70 proofflow-budget '
            'psql -X -qAt -h /run/proofflow-budget -U postgres -d proofflow_product '
            '--set ON_ERROR_STOP=1', statement.encode()))
    finally:
        admin.close()


def main():
    run = uuid4().hex
    path = PRIVATE / 'evidence' / ('phase6-guest-live-' + run + '.json')
    for old in path.parent.glob('phase6-guest-live-*.json'):
        previous = json.loads(old.read_bytes())
        require(previous.get('completed') or previous.get('reconciled_no_retry'),
                'RECONCILE_PREVIOUS_GUEST_AI_TEST')
    record = {'started_at': datetime.now(UTC).isoformat(), 'completed': False,
              'synthetic_automated_approvals_not_human_signoff': True, 'checks': [],
              'provider_calls': None}

    def save():
        path.write_text(json.dumps(record, indent=2), encoding='utf-8')

    save()
    start()
    latest = current()
    access = load(latest['access_file'])
    record['window_receipt'] = latest['receipt']
    baseline = counts()
    save()
    try:
        with client_for(access) as client, sync_playwright() as p:
            browser = p.chromium.launch()
            context = browser.new_context(viewport={'width': 1366, 'height': 900})
            page = context.new_page()
            files = sign_in_and_stage(page, access)
            require(counts() == baseline, 'LAUNCHER_UPLOADED_OR_APPROVED_AUTOMATICALLY')
            record['checks'].append('launcher_only_stages_files_no_upload_or_approval')
            record['file_hashes'] = {k: hashlib.sha256(v).hexdigest() for k, v in files.items()}
            page.locator('#files button').click()
            expect(page.locator('#confirm-contract')).to_be_enabled()
            expect(page.locator('#run')).to_be_disabled()
            page.locator('#confirm-contract').check()
            page.locator('#approve').click()
            expect(page.locator('#run')).to_be_enabled()
            page.locator('#run').click()
            page.wait_for_url('**/?job=*', timeout=20000)
            record['job'] = str(UUID(page.url.split('?job=', 1)[1]))
            save()
            expect(page.locator('#state')).to_have_text('Needs review', timeout=120000)
            original = client.get('/v1/jobs/' + record['job'] + '/summary').json()
            require(original['outcome'] == 'mismatch' and original['blocking_occurrences'] == 0,
                    'GUEST_ORIGINAL_MISMATCH_REQUIRED')
            record['original'] = original
            save()
            version_rehearsal(page, client, files, run, record, save, real_ai=True)
            page.locator('#job').screenshot(path=str(PRIVATE / 'evidence' /
                                                    ('phase6-guest-live-' + run + '.png')))
            after = counts()
            record['provider_calls'] = after['calls'] - baseline['calls']
            require(1 <= record['provider_calls'] <= 3 and after['prs'] == baseline['prs'],
                    'GUEST_CALL_OR_PR_BOUNDARY_CHANGED')
            record['checks'] += ['public_browser_system_trust_no_override',
                                 'actual_guest_original_mismatch', 'no_external_pr_intent']
            context.close()
            browser.close()
        record['completed'] = True
    finally:
        record['closure'] = stop()
        record['finished_at'] = datetime.now(UTC).isoformat()
        save()
    print(json.dumps({'completed': record['completed'], 'provider_calls': record['provider_calls'],
                      'checks': record['checks'], 'receipt': path.name}))


if __name__ == '__main__':
    main()

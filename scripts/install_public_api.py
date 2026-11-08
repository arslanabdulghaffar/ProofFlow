# ruff: noqa: E501 - systemd ExecStart must remain one logical line
"""Install a guest-only networkless API; listener activation is a separate step."""

import ipaddress
import json
import os
from pathlib import Path

from install_product_services import DOCKER, IMAGE, command, directory, expected_mounts, write
from public_api_policy import PUBLIC_MOUNTS, validate_public_container


def main():
    if os.geteuid() != 0:
        raise RuntimeError('ADMINISTRATOR_REQUIRED')
    os.umask(0o077)
    config = json.loads((Path(__file__).parent / 'public.json').read_bytes())
    address = str(ipaddress.IPv4Address(config['address']))
    directory('/etc/proofflow-public')
    write('/etc/proofflow-public/config.json', json.dumps({'address': address}).encode())
    directory('/etc/proofflow-public-api')
    directory('/etc/proofflow-public-api/tls', 10003)
    directory('/run/proofflow-public-api', 10003)
    write('/etc/tmpfiles.d/proofflow-public-api.conf',
          b'd /run/proofflow-public-api 0700 10003 10003 -\n', mode=0o644)
    write('/etc/proofflow-public-api/tls/origin.json',
          json.dumps({'origin': 'https://' + address + ':8443'}).encode(), 10003)
    hook = str(Path(__file__).parent / 'install_public_certificate.py')
    certificate = json.loads(command(['/opt/proofflow-acme/bin/python', '-I', hook]))
    name = 'proofflow-public-api'
    image = json.loads(command([*DOCKER, 'image', 'inspect', 'sha256:' + IMAGE]))[0]
    if image['Id'] != 'sha256:' + IMAGE:
        raise RuntimeError('PUBLIC_IMAGE_CHANGED')
    mounts = expected_mounts('api') | PUBLIC_MOUNTS
    args = [*DOCKER, 'create', '--pull=never', '--name=' + name,
            '--label=proofflow.role=product-public-api', '--read-only', '--cap-drop=ALL',
            '--security-opt=no-new-privileges', '--user=10003:10003', '--group-add=10001',
            '--memory=384m', '--memory-swap=384m', '--cpus=1', '--pids-limit=64',
            '--ulimit=core=0', '--ulimit=nofile=128:128', '--network=none']
    for destination, (source, writable) in mounts.items():
        args.append('--mount=type=bind,src=' + source + ',dst=' + destination
                    + ('' if writable else ',readonly'))
    args += ['sha256:' + IMAGE, 'python', '-m', 'api.app.product_bootstrap']
    if not command([*DOCKER, 'ps', '-aq', '--filter=name=^/' + name + '$']):
        command(args)
    actual = json.loads(command([*DOCKER, 'inspect', name]))[0]
    validate_public_container(actual, image['Config']['Env'])
    unit = '''[Unit]
Description=ProofFlow guest-only networkless API
Requires=docker.service proofflow-budget.service
After=docker.service proofflow-budget.service systemd-tmpfiles-setup.service
[Service]
ExecStart=/usr/bin/docker --host=unix:///var/run/docker.sock start -a proofflow-public-api
ExecStop=/usr/bin/docker --host=unix:///var/run/docker.sock stop -t 15 proofflow-public-api
Restart=on-failure
RestartSec=3
TimeoutStopSec=25
[Install]
WantedBy=multi-user.target
'''
    write('/etc/systemd/system/proofflow-public-api.service', unit.encode(), mode=0o644)
    for suffix in ('socket', 'service'):
        raw = (Path(__file__).parent / ('proofflow-public.' + suffix)).read_text()
        raw = raw.replace('@PUBLIC_IPV4@', address)
        write('/etc/systemd/system/proofflow-public.' + suffix, raw.encode(), mode=0o644)
    renewal = f'''[Unit]
Description=ProofFlow bounded IP certificate renewal
After=network-online.target
[Service]
Type=oneshot
ExecStart=/opt/proofflow-acme/bin/certbot renew --non-interactive --no-random-sleep-on-renew --config-dir /etc/proofflow-acme/production --work-dir /var/lib/proofflow-acme/production --logs-dir /var/log/proofflow-acme/production --deploy-hook "/opt/proofflow-acme/bin/python -I {hook}"
TimeoutStartSec=240
TimeoutStopSec=10
KillMode=control-group
UMask=0077
MemoryMax=256M
MemorySwapMax=0
TasksMax=32
LimitCORE=0
NoNewPrivileges=yes
PrivateTmp=yes
ProtectHome=yes
'''
    write('/etc/systemd/system/proofflow-public-renew.service', renewal.encode(), mode=0o644)
    timer = b'''[Unit]
Description=ProofFlow twice-daily certificate renewal
[Timer]
OnCalendar=*-*-* 00,12:00:00
RandomizedDelaySec=300
Persistent=true
[Install]
WantedBy=timers.target
'''
    write('/etc/systemd/system/proofflow-public-renew.timer', timer, mode=0o644)
    command(['/usr/bin/systemctl', 'daemon-reload'])
    command(['/usr/bin/systemctl', 'enable', '--now', 'proofflow-public-api.service',
             'proofflow-public-renew.timer'])
    print(json.dumps({'public_api_installed': True, 'image': IMAGE,
                      'listener_enabled': False, 'certificate': certificate}))


if __name__ == '__main__':
    main()

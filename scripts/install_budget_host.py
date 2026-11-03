"""One-time trusted control-host database install, private socket and bounded disk.

No public application route, provider call, candidate execution or ledger verdict.
Partial failure requires readback; never erase or reinitialize an existing database.
"""

import errno
import hashlib
import json
import os
import secrets
import subprocess
import time
from datetime import datetime
from pathlib import Path
from uuid import UUID, uuid4

IMAGE = "sha256:9ed8d24e2d804f04bd228a4619c9ed43c3a8d2f4a09fe947b44b112615eb010d"
SETUP = Path("/var/lib/proofflow-setup")
DATA = Path("/var/lib/proofflow-budget")
DOCKER = ["/usr/bin/docker", "--host=unix:///var/run/docker.sock"]


def command(args, data=None, timeout=90):
    result = subprocess.run(args, input=data, capture_output=True, timeout=timeout, check=False)  # noqa: S603
    if result.returncode:
        raise RuntimeError("BUDGET_INSTALL_COMMAND_FAILED")
    return result.stdout


def write(path, data, mode=0o600, uid=0, gid=0):
    fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, mode)
    with os.fdopen(fd, "wb") as output:
        output.write(data)
        os.fchmod(output.fileno(), mode)
        os.fchown(output.fileno(), uid, gid)
        output.flush()
        os.fsync(output.fileno())


def main():
    if os.geteuid() != 0:
        raise RuntimeError("CONTROL_ADMIN_REQUIRED")
    config = json.loads((SETUP / "budget-setup.json").read_bytes())
    if config["machine_id"] != Path("/etc/machine-id").read_text().strip():
        raise RuntimeError("WRONG_CONTROL_HOST")
    account = str(UUID(config["account_id"]))
    expiry = datetime.fromisoformat(config["expires_at"])
    if expiry.tzinfo is None:
        raise RuntimeError("INVALID_FUNDED_DEADLINE")
    os.umask(0o077)
    disk = SETUP / "budget.ext4"
    write(disk, b"")  # CreateNew refuses a partial/existing install.
    command(["/usr/bin/fallocate", "-l", "8589934592", str(disk)])
    command(["/usr/sbin/mkfs.ext4", "-q", "-F", "-N", "32768", "-L", "PF_BUDGET", str(disk)])
    DATA.mkdir(mode=0o700)
    command(["/usr/bin/mount", "-o", "loop,nodev,nosuid,noexec", str(disk), str(DATA)])
    observed = json.loads(command(["/usr/bin/findmnt", "--json", "--target", str(DATA),
                                   "--output", "TARGET,FSTYPE,OPTIONS"]))["filesystems"][0]
    if observed["target"] != str(DATA) or observed["fstype"] != "ext4" or not {
            "nodev", "nosuid", "noexec"} <= set(observed["options"].split(",")):
        raise RuntimeError("BOUNDED_DISK_MOUNT_MISMATCH")
    fs = os.statvfs(DATA)
    capacity = fs.f_blocks * fs.f_frsize
    if not 7 * 1024**3 <= capacity <= 8 * 1024**3:
        raise RuntimeError("BOUNDED_DISK_SIZE_MISMATCH")
    filler = DATA / "capacity-probe"
    fd = os.open(filler, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600)
    try:
        try:
            os.posix_fallocate(fd, 0, 9 * 1024**3)
        except OSError as error:
            if error.errno != errno.ENOSPC:
                raise
        else:
            raise RuntimeError("DISK_BOUND_NOT_ENFORCED")
    finally:
        os.close(fd)
        filler.unlink()
    # Persistent mount; exact new project path only, never replace existing entries.
    with Path("/etc/fstab").open("a") as output:
        output.write(f"\n{disk} {DATA} ext4 loop,nodev,nosuid,noexec 0 0\n")
        output.flush()
        os.fsync(output.fileno())
    pgdata = DATA / "pgdata"
    pgdata.mkdir(mode=0o700)
    os.chown(pgdata, 70, 70)
    socket = Path("/run/proofflow-budget")
    socket.mkdir(mode=0o2770)
    os.chown(socket, 70, 10001)
    os.chmod(socket, 0o2770)  # noqa: S103 - only DB and service group; setgid socket inheritance
    write(Path("/etc/tmpfiles.d/proofflow-budget.conf"),
          b"d /run/proofflow-budget 2770 70 10001 -\n", 0o644)
    conf = Path("/etc/proofflow-budget")
    conf.mkdir(mode=0o755)
    os.chmod(conf, 0o755)  # noqa: S103 - root-owned non-secret configuration
    for name in ("postgresql.conf", "pg_hba.conf"):
        write(conf / name, (SETUP / "postgres" / name).read_bytes(), 0o444)
    common = ["--pull=never", "--network=none", "--user=70:70", "--group-add=10001",
              "--read-only", "--cap-drop=ALL", "--security-opt=no-new-privileges:true",
              "--memory=536870912", "--memory-swap=536870912", "--cpus=1", "--pids-limit=64",
              "--tmpfs=/tmp:rw,noexec,nosuid,nodev,size=33554432",  # noqa: S108 - bounded container
              "--mount=type=bind,src=" + str(pgdata) + ",dst=/var/lib/postgresql/data"]
    command([*DOCKER, "run", "--rm", "--name=proofflow-budget-init", *common,
             "--entrypoint=initdb", IMAGE, "-D", "/var/lib/postgresql/data",
             "--auth-local=peer", "--auth-host=scram-sha-256"])
    command([*DOCKER, "create", "--name=proofflow-budget", "--label=proofflow.role=budget",
             *common, "--mount=type=bind,src=/run/proofflow-budget,dst=/run/proofflow-budget",
             "--mount=type=bind,src=/etc/proofflow-budget,dst=/etc/proofflow-budget,readonly",
             "--entrypoint=postgres", IMAGE, "-D", "/var/lib/postgresql/data",
             "-c", "config_file=/etc/proofflow-budget/postgresql.conf",
             "-c", "hba_file=/etc/proofflow-budget/pg_hba.conf"])
    unit = b"""[Unit]
Description=ProofFlow private budget database
Requires=docker.service
After=docker.service systemd-tmpfiles-setup.service
RequiresMountsFor=/var/lib/proofflow-budget
[Service]
ExecStart=/usr/bin/docker --host=unix:///var/run/docker.sock start -a proofflow-budget
ExecStop=/usr/bin/docker --host=unix:///var/run/docker.sock stop -t 20 proofflow-budget
Restart=on-failure
RestartSec=2
TimeoutStopSec=30
[Install]
WantedBy=multi-user.target
"""
    write(Path("/etc/systemd/system/proofflow-budget.service"), unit, 0o644)
    command(["/usr/bin/systemctl", "daemon-reload"])
    command(["/usr/bin/systemctl", "enable", "--now", "proofflow-budget.service"])
    deadline = time.monotonic() + 15
    while True:
        try:
            command([*DOCKER, "exec", "--user=70:70", "proofflow-budget", "pg_isready",
                     "-h", "/run/proofflow-budget", "-U", "postgres"], timeout=3)
            break
        except RuntimeError:
            if time.monotonic() >= deadline:
                raise
            time.sleep(0.2)
    command([*DOCKER, "exec", "--user=70:70", "proofflow-budget", "createdb",
             "-h", "/run/proofflow-budget", "-U", "postgres", "proofflow_budget"])

    def sql(data):
        return command([*DOCKER, "exec", "-i", "--user=70:70", "proofflow-budget", "psql",
                        "-X", "-qAt", "-h", "/run/proofflow-budget", "-U", "postgres",
                        "-d", "proofflow_budget", "--set", "ON_ERROR_STOP=1"], data)

    for name in ("001_budget.sql", "002_runtime_roles.sql", "003_probe_receipts.sql"):
        sql((SETUP / "migrations" / name).read_bytes())
    directory = Path("/etc/proofflow/credentials")
    directory.mkdir(mode=0o700, parents=True)
    os.chmod(directory.parent, 0o755)  # noqa: S103 - root-owned ancestor; secret child stays0700
    os.chown(directory, 10001, 10001)
    password = secrets.token_urlsafe(48)
    write(directory / "budget-password", password.encode(), 0o400, 10001, 10001)
    sql(("ALTER ROLE pf_budget_login PASSWORD '" + password + "';").encode())
    sql((f"INSERT INTO pf_budget.accounts VALUES ('{account}',150000000,25000000,2000000,"  # noqa: S608 - parsed UUID/datetime only
         f"'{expiry.isoformat()}',false);").encode())
    for category, amount in (("compute", 72000000), ("other", 48000000)):
        reservation = str(uuid4())
        digest = hashlib.sha256((category + str(amount)).encode()).hexdigest()
        sql((f"SELECT pf_budget.reserve('{account}','{reservation}','{digest}',"
             f"'{category}',{amount},'{expiry.isoformat()}');").encode())
    settings = sql(b"SELECT current_setting('listen_addresses'),current_setting('fsync'),"
                   b"current_setting('full_page_writes'),current_setting('synchronous_commit');")
    if settings.strip() != b"|on|on|on":
        raise RuntimeError("DATABASE_DURABILITY_OR_NETWORK_MISMATCH")
    sql(b"UPDATE pf_budget.accounts SET blocked=true;")
    report = {"database": "installed_private_scram_socket", "disk_capacity_bytes": capacity,
              "disk_exhaustion": "ENOSPC_then_fixture_removed", "image": IMAGE,
              "project_limit_micro_usd": 150000000, "inference_limit_micro_usd": 25000000,
              "probe_limit_micro_usd": 2000000, "non_inference_reserved_micro_usd": 120000000,
              "admission": "blocked_until_fresh_provider_and_account_checks",
              "provider_calls": 0, "acceptance": "AUTH_RESTORE_PROVIDER_CHECKS_PENDING"}
    write(SETUP / "budget-install.json", json.dumps(report, sort_keys=True).encode())
    print(json.dumps(report))


if __name__ == "__main__":
    try:
        main()
    except Exception:
        raise SystemExit("BUDGET_HOST_INSTALL_FAILED_REQUIRES_READBACK") from None

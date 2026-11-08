"""First private product service installation; existing mismatched resources are preserved."""

import json
import os
import re
import stat
import subprocess
from pathlib import Path

IMAGE = "441d3a417149242c7afb1f6ae72a355865b8515f2416ff02f92a0deb1cf50a74"
PREVIOUS = "c65fa2203eed08f062f76a9c6a58d056119d1521e19af42091244ede201c7dc4"
DOCKER = ["/usr/bin/docker", "--host=unix:///var/run/docker.sock"]


def expected_mounts(role):
    if role not in ("api", "dispatcher"):
        raise RuntimeError("PRODUCT_ROLE_INVALID")
    mounts = {
        "/run/proofflow-budget": ("/run/proofflow-budget", False),
        "/etc/proofflow-product/credentials": (
            "/etc/proofflow-product-" + role + "/credentials", False),
        "/var/lib/proofflow-product/assets": ("/var/lib/proofflow-product/assets", role == "api"),
        "/var/lib/proofflow-product/jobs": ("/var/lib/proofflow-product/jobs", role != "api"),
    }
    if role == "api":
        mounts.update({
            "/etc/proofflow-batch-events": ("/etc/proofflow-batch-events", False),
            "/run/proofflow-product-api": ("/run/proofflow-product-api", True),
            "/etc/proofflow-product/tls": ("/etc/proofflow-product-api/tls", False),
        })
    else:
        mounts.update({
            "/etc/proofflow-github": ("/etc/proofflow-github", False),
            "/etc/proofflow-repair": ("/etc/proofflow-repair", False),
            "/etc/proofflow-product/worker": ("/etc/proofflow-product-dispatcher/worker", False),
            "/run/proofflow-verifier": ("/run/proofflow-verifier", False),
        })
    return mounts


def validate_container(config, role, image_env):
    """Reject security drift before accepting an existing or rebuilt container.

    The immutable image alone cannot pin host mounts, privileges or runtime limits.
    Called only with trusted Docker inspect data; errors never include its contents.
    """
    try:
        host, process = config["HostConfig"], config["Config"]
        expected = expected_mounts(role)
        mounts = config["Mounts"]
        actual = {m["Destination"]: (m["Source"], m["RW"]) for m in mounts}
        limits = {v["Name"]: (v["Soft"], v["Hard"]) for v in host["Ulimits"]}
        module = "api.app.product_bootstrap" if role == "api" else "orchestrator.product_bootstrap"
        valid = (
            config["Image"] == "sha256:" + IMAGE
            and process["Labels"].get("proofflow.role") == "product-" + role
            and process["User"] == "10003:10003" and process["WorkingDir"] == "/app"
            and process["Cmd"] == ["python", "-m", module] and not process["Entrypoint"]
            and process["Env"] == image_env
            and host["ReadonlyRootfs"] is True and host["Privileged"] is False
            and host["CapDrop"] == ["ALL"] and not host["CapAdd"]
            and host["SecurityOpt"] == ["no-new-privileges"]
            and host["Memory"] == host["MemorySwap"] == 384 * 1024 * 1024
            and host["NanoCpus"] == 1000000000 and host["PidsLimit"] == 64
            and host["GroupAdd"] == ["10001"]
            and limits == {"core": (0, 0), "nofile": (128, 128)}
            and len(host["Ulimits"]) == len(limits)
            and host["NetworkMode"] == ("none" if role == "api" else "host")
            and not host["PortBindings"] and not host["PublishAllPorts"]
            and host["PidMode"] == "" and host["IpcMode"] == "private"
            and host["UTSMode"] == "" and host["UsernsMode"] == ""
            and host["CgroupnsMode"] == "private" and host["Runtime"] == "runc"
            and all(not host.get(k) for k in ("Binds", "VolumesFrom", "Tmpfs", "Devices",
                                              "DeviceRequests", "DeviceCgroupRules", "Links"))
            and actual == expected and len(mounts) == len(expected)
            and all(m["Type"] == "bind" and m["Propagation"] == "rprivate" for m in mounts)
        )
    except (KeyError, TypeError, AttributeError):
        valid = False
    if not valid:
        raise RuntimeError("PRODUCT_CONTAINER_CONFIGURATION_CHANGED")


def command(args, timeout=30):
    result = subprocess.run(args, capture_output=True, timeout=timeout,  # noqa: S603 - fixed admin argv
                            env={"PATH": "/usr/sbin:/usr/bin:/sbin:/bin", "LANG": "C"})
    if result.returncode:
        raise RuntimeError("PRODUCT_SERVICE_ADMIN_FAILED")
    return result.stdout.decode().strip()


def directory(path, uid=0, mode=0o700):
    target = Path(path)
    try:
        target.mkdir(mode=mode)
        os.chown(target, uid, uid)
        os.chmod(target, mode)
    except FileExistsError:
        info = target.lstat()
        if (not stat.S_ISDIR(info.st_mode) or info.st_uid != uid
                or stat.S_IMODE(info.st_mode) != mode):
            raise RuntimeError("PRODUCT_DIRECTORY_CHANGED") from None
    return target


def write(path, raw, uid=0, mode=0o400):
    target = Path(path)
    if target.exists() or target.is_symlink():
        info = target.lstat()
        if (not stat.S_ISREG(info.st_mode) or info.st_uid != uid or info.st_nlink != 1
                or stat.S_IMODE(info.st_mode) != mode or target.read_bytes() != raw):
            raise RuntimeError("EXISTING_PRODUCT_CONFIGURATION_CHANGED")
        return
    fd = os.open(target, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, mode)
    try:
        with os.fdopen(fd, "wb", closefd=False) as file:
            file.write(raw)
            file.flush()
            os.fchmod(fd, mode)
            os.fchown(fd, uid, uid)
            os.fsync(fd)
    finally:
        os.close(fd)
    parent = os.open(target.parent, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
    try:
        os.fsync(parent)
    finally:
        os.close(parent)


def verifier_unit(verifier):
    return f"""[Unit]
Description=ProofFlow fixed verifier socket helper
Requires=proofflow-verifier-helper.socket
After=proofflow-verifier-helper.socket
[Service]
ExecStart=/usr/bin/python3 -I -B {verifier}/verifier_socket_admin.py
User=root
Group=root
UMask=0077
NoNewPrivileges=yes
CapabilityBoundingSet=
AmbientCapabilities=
ProtectSystem=strict
ProtectHome=yes
PrivateNetwork=yes
PrivateDevices=yes
RestrictAddressFamilies=AF_UNIX
RestrictNamespaces=yes
ProtectKernelTunables=yes
ProtectKernelModules=yes
ProtectControlGroups=yes
ReadWritePaths=/var/lib/proofflow-verifier
MemoryMax=384M
MemorySwapMax=0
CPUQuota=100%
TasksMax=16
LimitNOFILE=64
LimitCORE=0
Restart=on-failure
RestartSec=3
TimeoutStopSec=3
""".encode()


def main():
    if os.geteuid() != 0:
        raise RuntimeError("ADMINISTRATOR_REQUIRED")
    os.umask(0o077)
    settings = json.loads((Path(__file__).parent / "settings.json").read_bytes())
    revision = settings["verifier_deployment"]
    if re.fullmatch(r"[0-9a-f]{64}", revision) is None:
        raise RuntimeError("INVALID_VERIFIER_REVISION")
    verifier = Path("/opt/proofflow-verifier") / revision
    verifier_config = json.loads((verifier / "deployment.json").read_bytes())
    image = json.loads(command([*DOCKER, "image", "inspect", "sha256:" + IMAGE]))[0]
    if (image["Id"] != "sha256:" + IMAGE or image["Architecture"] != "amd64"
            or image["Os"] != "linux" or image["Config"]["User"] != "10003:10003"):
        raise RuntimeError("PRODUCT_IMAGE_IDENTITY_CHANGED")
    directory("/var/lib/proofflow-product")
    directory("/var/lib/proofflow-product/assets", 10003)
    directory("/var/lib/proofflow-product/jobs", 10003)
    directory("/run/proofflow-product-api", 10003)
    directory("/run/proofflow-verifier", mode=0o750)
    os.chown("/run/proofflow-verifier", 0, 10003)
    directory("/var/lib/proofflow-verifier")
    write("/etc/tmpfiles.d/proofflow-product.conf",
          b"d /run/proofflow-product-api 0700 10003 10003 -\n"
          b"d /run/proofflow-verifier 0750 root 10003 -\n", mode=0o644)
    directory("/etc/proofflow-product-api/tls", 10003)
    for name in ("health.pem", "health.key", "ca.pem"):
        write("/etc/proofflow-product-api/tls/" + name,
              (Path("/etc/proofflow-health") / name).read_bytes(), 10003)
    private_worker = directory("/etc/proofflow-product-dispatcher/worker", 10003)
    worker_config = json.loads(Path("/opt/proofflow-control/worker.json").read_bytes())
    worker_config["verifier_sha256"] = verifier_config["rootfs_sha256"]
    write(private_worker / "worker.json", json.dumps(worker_config, sort_keys=True).encode(), 10003)
    for name in ("ca.pem", "controller.pem", "controller.key"):
        write(private_worker / name,
              (Path("/opt/proofflow-control/tls") / name).read_bytes(), 10003)
    helper = verifier_unit(verifier)
    socket = b"""[Unit]
Description=ProofFlow private verifier dispatcher socket
[Socket]
ListenStream=/run/proofflow-verifier/verify.sock
SocketUser=10003
SocketGroup=10003
SocketMode=0600
Backlog=4
RemoveOnStop=yes
[Install]
WantedBy=sockets.target
"""
    write("/etc/systemd/system/proofflow-verifier-helper.service", helper, mode=0o644)
    write("/etc/systemd/system/proofflow-verifier-helper.socket", socket, mode=0o644)
    # Only the trusted dispatcher gets inference/budget credentials. API, worker
    # and verifier receive neither. No management key is installed on either VM.
    directory("/etc/proofflow-repair", mode=0o755)
    directory("/etc/proofflow-repair/credentials", 10003)
    write("/etc/proofflow-repair/config.json",
          json.dumps(settings["repair_provider"], sort_keys=True).encode(), mode=0o444)
    for secret_name in ("vultr-api-key", "budget-password"):
        source = Path("/etc/proofflow/credentials") / secret_name
        info = source.lstat()
        if (not stat.S_ISREG(info.st_mode) or info.st_uid != 10001 or info.st_nlink != 1
                or stat.S_IMODE(info.st_mode) != 0o400):
            raise RuntimeError("PROVIDER_CREDENTIAL_IDENTITY_CHANGED")
        write(Path("/etc/proofflow-repair/credentials") / secret_name, source.read_bytes(), 10003)
    directory("/etc/proofflow-github", 10003)
    directory("/etc/proofflow-batch-events", 10003)
    master = Path("/etc/proofflow-batch-events/master")
    if master.exists() or master.is_symlink():
        info = master.lstat()
        if (not stat.S_ISREG(info.st_mode) or info.st_uid != 10003 or info.st_nlink != 1
                or info.st_size != 32 or stat.S_IMODE(info.st_mode) != 0o400):
            raise RuntimeError("BATCH_MASTER_IDENTITY_CHANGED")
    else:
        write(master, os.urandom(32), 10003)
    for role in ("api", "dispatcher"):
        name = "proofflow-product-" + role
        # No Docker management socket, host PID namespace or API-management key.
        args = [*DOCKER, "create", "--pull=never", "--name=" + name,
                "--label=proofflow.role=product-" + role, "--read-only", "--cap-drop=ALL",
                "--security-opt=no-new-privileges", "--user=10003:10003", "--group-add=10001",
                "--memory=384m", "--memory-swap=384m", "--cpus=1", "--pids-limit=64",
                "--ulimit=core=0", "--ulimit=nofile=128:128",
                "--network=" + ("none" if role == "api" else "host"),
                "--mount=type=bind,src=/run/proofflow-budget,dst=/run/proofflow-budget,readonly",
                "--mount=type=bind,src=/etc/proofflow-product-" + role
                + "/credentials,dst=/etc/proofflow-product/credentials,readonly",
                "--mount=type=bind,src=/var/lib/proofflow-product/assets,"
                "dst=/var/lib/proofflow-product/assets"
                + (",readonly" if role == "dispatcher" else "")]
        if role == "api":
            args.extend(["--mount=type=bind,src=/etc/proofflow-batch-events,dst=/etc/proofflow-batch-events,readonly",
                         "--mount=type=bind,src=/var/lib/proofflow-product/jobs,"
                         "dst=/var/lib/proofflow-product/jobs,readonly","--mount=type=bind,src=/run/proofflow-product-api,dst=/run/proofflow-product-api",
                         "--mount=type=bind,src=/etc/proofflow-product-api/tls,"
                         "dst=/etc/proofflow-product/tls,readonly"])
            module = "api.app.product_bootstrap"
        else:
            args.extend(["--mount=type=bind,src=/etc/proofflow-github,dst=/etc/proofflow-github,readonly",
                         "--mount=type=bind,src=/etc/proofflow-repair,dst=/etc/proofflow-repair,readonly",
                         "--mount=type=bind,src=/etc/proofflow-product-dispatcher/worker,"
                         "dst=/etc/proofflow-product/worker,readonly",
                         "--mount=type=bind,src=/run/proofflow-verifier,dst=/run/proofflow-verifier,readonly",
                         "--mount=type=bind,src=/var/lib/proofflow-product/jobs,"
                         "dst=/var/lib/proofflow-product/jobs"])
            module = "orchestrator.product_bootstrap"
        args.extend(["sha256:" + IMAGE, "python", "-m", module])
        existing = command([*DOCKER, "ps", "-aq", "--filter=name=^/" + name + "$"])
        if existing:
            prior = json.loads(command([*DOCKER, "inspect", name]))[0]
            if prior["Image"] == "sha256:" + PREVIOUS:
                if (prior["Config"]["Labels"].get("proofflow.role") != "product-" + role
                        or prior["Config"]["User"] != "10003:10003"
                        or not prior["HostConfig"]["ReadonlyRootfs"]):
                    raise RuntimeError("PRIOR_PRODUCT_IDENTITY_CHANGED")
                # Preserve the stopped predecessor. No replacement while any job
                # is active or admission open; migrations and assets stay intact.
                ready = command([*DOCKER, "exec", "--user=70:70", "proofflow-budget",
                    "psql", "-X", "-qAt", "-h", "/run/proofflow-budget", "-U", "postgres",
                    "-d", "proofflow_product", "-c", "SELECT NOT EXISTS(SELECT 1 FROM "
                    "pf_product.execution_policy WHERE enabled) AND NOT EXISTS(SELECT 1 FROM "
                    "pf_product.jobs WHERE state NOT IN "
                    "('NEEDS_REVIEW','FAILED_INFRA','CANCELLED')) AND NOT EXISTS(SELECT 1 FROM "
                    "pf_product.repairs WHERE state IN ('QUEUED','RUNNING','RECONCILING')) "
                    "AND NOT EXISTS(SELECT 1 FROM pf_product.pr_intents "
                    "WHERE lease_owner IS NOT NULL "
                    "OR state IN ('BRANCH_PENDING','COMMIT_PENDING','PR_PENDING'));"])
                if ready != "t":
                    raise RuntimeError("PRODUCT_UPGRADE_REQUIRES_CLOSED_IDLE_QUEUE")
                archived = name + "-previous-" + PREVIOUS[:12]
                if command([*DOCKER, "ps", "-aq", "--filter=name=^/" + archived + "$"]):
                    raise RuntimeError("PRIOR_PRODUCT_ARCHIVE_ALREADY_EXISTS")
                command(["/usr/bin/systemctl", "stop", name + ".service"])
                if json.loads(command([*DOCKER, "inspect", name]))[0]["State"]["Running"]:
                    raise RuntimeError("PRIOR_PRODUCT_STILL_RUNNING")
                command([*DOCKER, "rename", name, archived])
                existing = ""
        if not existing:
            command(args)
        config = json.loads(command([*DOCKER, "inspect", name]))[0]
        validate_container(config, role, image["Config"]["Env"])
        unit = f"""[Unit]
Description=ProofFlow private product {role}
Requires=docker.service proofflow-budget.service proofflow-verifier-helper.socket
After=docker.service proofflow-budget.service proofflow-verifier-helper.socket
[Service]
ExecStart=/usr/bin/docker --host=unix:///var/run/docker.sock start -a {name}
ExecStop=/usr/bin/docker --host=unix:///var/run/docker.sock stop -t 15 {name}
Restart=on-failure
RestartSec=3
TimeoutStopSec=25
[Install]
WantedBy=multi-user.target
""".encode()
        write("/etc/systemd/system/" + name + ".service", unit, mode=0o644)
    command(["/usr/bin/systemctl", "daemon-reload"])
    command(["/usr/bin/systemctl", "enable", "--now", "proofflow-verifier-helper.socket",
             "proofflow-product-api.service", "proofflow-product-dispatcher.service"])
    print(json.dumps({"image": IMAGE, "api_network": "none", "api_transport": "private_unix_tls",
                      "dispatcher_targets": "fixed_vultr_worker_and_local_database_verifier",
                      "inference_credentials_mounted": "dispatcher_only",
                      "github_credentials_mounted": "dispatcher_only_optional",
                      "new_cloud_resources": 0}))


if __name__ == "__main__":
    main()

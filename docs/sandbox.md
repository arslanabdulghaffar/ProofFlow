# Sandbox design and compatibility gate

DESIGN / NOT RUN. Use a dedicated Vultr Linux worker, never the control VM or this Windows/WSL development computer for candidate execution. Pin Docker, runsc binary digest/version, OS, candidate image digest and `--platform=systrap` runtime arguments. gVisor's platform guide recommends systrap for VM environments; that is not evidence that a selected Vultr plan works. See [external evidence](external-evidence.md).

The supervisor accepts only private mTLS create/status/cancel/fence operations with execution/job IDs, generation, server-approved image/limit profile, immutable manifest and hard deadline. No public Docker socket, arbitrary path, shell command, privilege or runtime flags. Non-root candidate UID, all capabilities dropped, no-new-privileges, read-only root, no host PID/IPC/network namespace/devices. Dependencies are installed in trusted image builds only. Fail readiness if explicit runsc identity/configuration is missing. Guest `dmesg` text alone is forgeable and is not runtime identity evidence.

## Controls and independent probes

| Resource | Planned enforcement | Phase 1 evidence required |
| --- | --- | --- |
| CPU | cgroup v2 quota equivalent to 1 vCPU, covering all execution processes plus runtime children; supervisor outside guest budget | Saturating workload; host cgroup counters/quota and measured throttling; application remains responsive |
| Memory | 768 MiB sandbox memory limit, bounded runtime overhead, swap disabled for the execution; reserve host headroom | Capped allocation hits configured limit, host peak/accounting and termination receipt, no host OOM |
| Guest processes/tasks | Hard and soft guest RLIMIT_NPROC=64 for unprivileged UID via immutable launcher/OCI settings, if the pinned runsc actually enforces it; host pids limit separately bounds runtime overhead | Bounded fork AND thread probes count guest tasks, deny creation above cap, prevent raising hard limit; verify pandas thread configuration. Docker host PID counts are not proof of guest count |
| Output capacity | Supervisor-owned dedicated tmpfs or equivalent per-execution filesystem, 64 MiB, restrictive ownership/mount flags | Output flood gets ENOSPC/cap violation without filling host; accounting before/after |
| Scratch capacity | Separate 64 MiB bounded mount, including /tmp and reviewed writable /dev/shm; no other writable image layer | Scratch/shared-memory flood capped; inspect all writable mounts |
| Inodes/files | Proposed `nr_inodes=1024` per bounded filesystem plus fixed output allowlist | Many zero-byte files exhaust the execution quota; no unbounded host inode growth |
| Network | runsc networking disabled/none with isolated loopback only; host egress policy defense in depth | IPv4/IPv6, DNS, metadata, control/worker private IP and controlled external endpoint probes denied |
| Wall time | Supervisor monotonic 20s execution watchdog independent of controller RPC; includes child processes | Loop/background child stopped by deadline, no residual guest/runtime writer, cleanup receipt |
| Collector | <=10 MiB combined allowed JSONL, <=20,000 lines; 100 KiB combined stdout/stderr with truncation flag | Large files/logs, wrong types, links, FIFO/device and filename substitutions fail safely |
| Trusted parser/verifier | Separate process/image: 1 vCPU, 512 MiB, 5s per task | Malformed/oversized/deep JSON/CSV fails within cap; no imports or execution of candidate |

Guest process control is a specific **unproven compatibility gate**. gVisor maps guest tasks differently from host processes. Inspect the pinned implementation and probe guest RLIMIT behavior; if no reliable 64-task bound can be demonstrated, do not expose uploaded code. Evaluate a reviewed runtime/throwaway-VM alternative with equivalent controls or stop. Do not substitute a host `--pids-limit=64` claim or a prompt instruction. Record runsc overhead separately so host PID/memory limits do not unexpectedly kill the supervisor.

## Stop writers without losing output

The supervisor mounts its own private bounded output/scratch filesystems and owns their lifecycle; it does not use ephemeral container-only output that vanishes on stop. It stages validated code/input bytes under fixed read-only paths and retains open parent-directory handles.

On normal exit, timeout, cancel or lost controller: terminate the entire guest including descendants; wait for runtime termination and confirm no remaining guest/runtime writers through host process/cgroup and runtime state. Freeze/stop alone without this evidence is not safe collection. Keep supervisor-owned output storage mounted after runtime termination. Mark collection uncertain if any writer cannot be ruled out; never verify racing bytes.

After termination, collect only ledger.jsonl, unresolved.jsonl and rollups.jsonl when the v1.1 contract explicitly enables it. Use directory-relative non-following opens; inspect regular-file type, link count, device/inode identity, size and bounds; forbid symlinks/hard-link anomalies, FIFOs, sockets, devices, directories and extra output entries. Read bounded bytes once, hash them, transport to immutable control storage; check identity again. Diagnostics are untrusted escaped text. Candidate receipts/reports are ignored as authority.

After control acknowledges durable collection (or bounded retention deadline expires), remove container/runtime resources, unmount job filesystems and remove only the supervisor-created execution directory. Journal cleanup success/failure and sweep stale server-labeled execution IDs. Never let caller paths determine deletion. Failed cleanup disables affected capacity until reconciled; a verified data result cannot hide a leaked execution. The hard watchdog always wins over collection convenience.

## Loop/admission limits

Original plus <=3 proposals; <=4 canary executions (one per otherwise passing original/candidate); <=5 model requests including retries; 300s total. Two execution slots, global queue <=20, guest one active job, three starts/day, one start/minute; ten starts/IP/day, 100 public starts/day, guest creation one/IP/10min. Daily counters use documented UTC windows; UI displays reset in explicit timezone. Benchmark mode can bypass guest/IP quotas only, never resource/time/cost caps. Optional witness reducer is deferred; if added, <=8 reruns/30s within the same job budget.

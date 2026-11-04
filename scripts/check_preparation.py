"""Check Phase 0 documentation coverage/hygiene; never execute product candidates."""

import re
import shutil
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
errors: list[str] = []


def require(condition: bool, message: str) -> None:
    if not condition:
        errors.append(message)


required = [
    "README.md", "AGENTS.md", "CONTRIBUTING.md", ".gitignore", ".env.example",
    "THIRD_PARTY_NOTICES.md", "eval/plan.md",
] + [f"docs/{name}.md" for name in (
    "product", "contract", "architecture", "threat-model", "requirements-traceability",
    "rules", "decisions", "risks", "phase-plan", "progress", "environment-readiness",
    "test-plan", "demo", "release", "next-session", "source-review", "external-evidence",
    "sandbox", "inference", "api",
)]
for name in required:
    require((ROOT / name).is_file(), f"Missing required preparation file: {name}")

trace = ROOT / "docs/requirements-traceability.md"
if trace.exists():
    rows = [line for line in trace.read_text(encoding="utf-8").splitlines()
            if re.match(r"\| R\d{2}-\d{2} \|", line)]
    pages, ids = set(), set()
    for row in rows:
        cells = [cell.strip() for cell in row.strip("|").split("|")]
        require(len(cells) == 9 and all(cells), "Incomplete traceability row")
        if len(cells) != 9:
            continue
        rid, page, kind, priority, _, _, _, _, status = cells
        require(rid not in ids, f"Duplicate requirement ID: {rid}")
        ids.add(rid)
        require(page.isdigit() and 1 <= int(page) <= 59, f"Bad page: {rid}")
        if page.isdigit():
            pages.add(int(page))
            require(rid.startswith(f"R{int(page):02d}-"), f"ID/page mismatch: {rid}")
        require(kind in {"DESIGN", "OFFICIAL", "CONTEXT", "TARGET", "OPEN", "OBSERVED"},
                f"Missing classification: {rid}")
        require(priority in {"P0", "P1", "INFO"}, f"Missing priority: {rid}")
        require(status in {"IMPLEMENTED_DOC", "IMPLEMENTED_PHASE1", "IMPLEMENTED_PHASE2",
                           "IMPLEMENTED_PHASE3", "PARTIAL_PHASE2", "PARTIAL_PHASE3",
                           "BLOCKED_OWNER", "DEFERRED_P1",
                           "DEFERRED_CONDITIONAL"} |
                {f"DEFERRED_PHASE{i}" for i in range(1, 7)}, f"Bad status: {rid}")
    require(pages == set(range(1, 60)), "Traceability does not cover all 59 PDF pages")
    print(f"Traceability: {len(ids)} unique entries, {len(pages)} pages; fields checked")

source_index = ROOT / "docs/external-evidence.md"
if source_index.exists():
    source_ids = re.findall(r"^\| (S\d{2}) \|", source_index.read_text(encoding="utf-8"), re.M)
    require(len(source_ids) == 42 and set(source_ids) == {f"S{i:02d}" for i in range(1, 43)},
            "PDF source index must contain each S01–S42 exactly once")

doc_files = [ROOT / "README.md", ROOT / "AGENTS.md", ROOT / "CONTRIBUTING.md",
             ROOT / "THIRD_PARTY_NOTICES.md"]
doc_files += list((ROOT / "docs").glob("*.md")) + list((ROOT / "eval").glob("*.md"))
for path in doc_files:
    if not path.exists():
        continue
    text = path.read_text(encoding="utf-8")
    for target in re.findall(r"\]\(([^)]+)\)", text):
        if re.match(r"[a-z]+://", target) or target.startswith("#"):
            continue
        clean = target.split("#", 1)[0].strip("<>")
        require((path.parent / clean).exists(), f"Broken local link in {path.name}: {clean}")
    require("\ufffd" not in text, f"Replacement character in {path.name}")

env = ROOT / ".env.example"
if env.exists():
    keys = []
    for line in env.read_text(encoding="utf-8").splitlines():
        if not line or line.startswith("#"):
            continue
        require("=" in line, "Invalid environment template line")
        if "=" not in line:
            continue
        key, value = line.split("=", 1)
        keys.append(key)
        require(not key.startswith("NEXT_PUBLIC"), "Public environment variable needs review")
        if key.endswith("_FILE") or key in {
            "DATABASE_URL", "GITHUB_APP_ID", "GITHUB_INSTALLATION_ID",
        }:
            require(not value, f"Sensitive/location template must be empty: {key}")
    require(len(keys) == len(set(keys)), "Duplicate environment template keys")

samples = [".env", ".env.local", "secrets/test.pem", ".venv-tools/test", ".tools/test",
           "node_modules/test", "data/private.csv", "artifacts/run.json", "backups/db.dump",
           "eval/results/run.jsonl", "ProofFlow_Complete_Engineering_Handoff.pdf"]
git = shutil.which("git")
if git is None:
    errors.append("Git is required for ignore-policy checks")
else:
    for sample in [*samples, ".env.example"]:
        result = subprocess.run(  # noqa: S603 - resolved Git, fixed verb and local fixture paths
            [git, "check-ignore", "--quiet", "--no-index", sample], cwd=ROOT, timeout=10,
        )
        expected = 1 if sample == ".env.example" else 0
        require(result.returncode == expected, f"Unexpected ignore policy for: {sample}")

if errors:
    for error in errors:
        print(f"FAIL: {error}", file=sys.stderr)
    sys.exit(1)
print("PASS: preparation inventory, all-page fields, source index, local links, "
      "template and ignore rules")
print("Scope: documentation hygiene only. "
      "Application/runtime/inference/security acceptance NOT RUN.")

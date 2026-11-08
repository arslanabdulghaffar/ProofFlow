"""Offline private review bundle. No publication, cloud call or candidate execution."""

import argparse
import hashlib
import io
import json
import re
import shutil
import stat
import struct
import subprocess
import sys
import zipfile
from datetime import UTC, datetime
from pathlib import Path, PurePosixPath
from xml.etree import ElementTree as ET

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from eval.comparison_artifact import check  # noqa: E402

MAX_TOTAL = 64 * 1024 * 1024
NS = {"a": "http://schemas.openxmlformats.org/drawingml/2006/main"}
DOCUMENTS = {
    "README.md": "release/README.md",
    "setup.md": "release/setup.md",
    "submission.json": "release/submission.json",
    "submission-copy.md": "release/submission-copy.md",
    "evidence/comparison.md": "eval/final-comparison-2026-11-06.md",
    "evidence/phase6.json": "docs/evidence/phase6-scheduled-portable-demo-2026-11-08.json",
    "evidence/phase5.json": "docs/evidence/phase5-binary-acceptance-2026-11-07.json",
    "evidence/ingress-recovery.json": "docs/evidence/phase6-ingress-recovery-2026-11-08.json",
    "evidence/public-tls.json": "docs/evidence/phase6-public-tls-2026-11-08.json",
    "evidence/guest-operation.json": "docs/evidence/phase6-guest-operation-2026-11-08.json",
    "evidence/recovery-release.json":
        "docs/evidence/phase6-recovery-release-hardening-2026-11-08.json",
}


def require(condition, message):
    if not condition:
        raise ValueError(message)


def release_gate(submission, public=None):
    require(submission["repository_visibility"] == "private"
            and submission["release_allowed"] is False and submission["license_issued"] is False,
            "UNAPPROVED_RELEASE_CLAIM")
    if submission["public_demo_url"] is not None:
        require(public is not None and public.get("external_acceptance_passed") is True
                and public.get("owner_authorized_activation") is True
                and submission["public_demo_url"] == public.get("origin"),
                "PUBLIC_URL_WITHOUT_EVIDENCE")


def sha(raw):
    return hashlib.sha256(raw).hexdigest()


def git(*args):
    return subprocess.run(  # noqa: S603 - fixed Git operations, no shell or candidate source
        [shutil.which("git"), *args], cwd=ROOT, capture_output=True, check=True
    ).stdout


def safe_entries(archive):
    infos = archive.infolist()
    require(all(i.orig_filename == i.filename for i in infos), "ARCHIVE_NAME_NORMALIZATION")
    names = [item.filename for item in infos]
    require(len(names) == len(set(names)), "DUPLICATE_ARCHIVE_NAME")
    require(len(names) <= 5000 and sum(i.file_size for i in infos) <= MAX_TOTAL,
            "ARCHIVE_BOUNDS")
    require(not any(stat.S_ISLNK(i.external_attr >> 16) for i in infos), "ARCHIVE_SYMLINK")
    for name in names:
        parts = PurePosixPath(name).parts
        require(not name.startswith("/") and "\\" not in name and ":" not in name
                and not any(p in ("..", ".git", "secrets", ".venv", ".tools") for p in parts),
                "UNSAFE_ARCHIVE_NAME")
        leaf = parts[-1] if parts else ""
        require(not leaf.lower().endswith((".pem", ".key", ".p12", ".pfx", ".sqlite", ".dump"))
                and (not leaf.startswith(".env") or leaf == ".env.example")
                and not leaf.lower().startswith("credentials"), "SECRET_OR_RUNTIME_FILE")
    return names


def xml(raw):
    lowered = raw.lower()
    require(len(raw) <= 2 * 1024 * 1024 and b"\x00" not in raw
            and b"<!doctype" not in lowered and b"<!entity" not in lowered,
            "OOXML_DECLARATION_OR_SIZE")
    return ET.fromstring(raw)  # noqa: S314 - bounded UTF-8 OOXML, DTD/entities denied above


def inspect_deck(raw, content):
    with zipfile.ZipFile(io.BytesIO(raw)) as deck:
        names = safe_entries(deck)
        slides = [n for n in names if re.fullmatch(r"ppt/slides/slide\d+\.xml", n)]
        require(len(slides) == 8, "DECK_SLIDE_COUNT")
        require(not any("vbaproject" in n.lower() for n in names), "DECK_MACRO_FORBIDDEN")
        for n in names:
            if n.endswith(".rels"):
                require(all(r.attrib.get("TargetMode") != "External"
                            for r in xml(deck.read(n))), "DECK_EXTERNAL_LINK")
        table = xml(deck.read("ppt/slides/slide7.xml")).find(".//a:tbl", NS)
        require(table is not None, "NATIVE_COMPARISON_TABLE_REQUIRED")
        values = [["".join(cell.itertext()) for cell in row.findall("a:tc", NS)]
                  for row in table.findall("a:tr", NS)]
        # itertext includes only encoded table text, not rendered/OCR guesses.
        require(values == content["comparison"], "DECK_COMPARISON_CHANGED")
        notes = [n for n in names if re.fullmatch(r"ppt/notesSlides/notesSlide\d+\.xml", n)]
        require(len(notes) == 8, "DECK_SOURCE_NOTES_REQUIRED")


def check_claims():
    artifact = json.loads((ROOT / "eval/final-comparison-2026-11-06.json").read_bytes())
    report = check(artifact)  # Data-only accounting; never imports the candidate strings.
    content = json.loads((ROOT / "release/deck-content.json").read_bytes())
    for row, arm in zip(content["comparison"][1:], "ABCD", strict=True):
        result = report["arms"][arm]
        wanted = [f"{result['outcomes'][k]['successful']} / {result['outcomes'][k]['planned']}"
                  for k in ("repairable", "ambiguous")]
        wanted.append(f"{result['incorrect_accepted']} / {result['accepted']}")
        require(row[1:] == wanted, "RELEASE_COMPARISON_DRIFT")
    submission = json.loads((ROOT / "release/submission.json").read_bytes())
    public = json.loads((ROOT / DOCUMENTS["evidence/public-tls.json"]).read_bytes())
    release_gate(submission, public)
    return content


def source_bindings(archive, source, *, documents):
    """Cross-check outer claims/media with the source snapshot, without execution."""
    for name, local in documents.items():
        # Historical Windows packages used CRLF working-tree text. New packages
        # use exact committed bytes; comparison tolerates only that newline form.
        require(archive.read(name).replace(b"\r\n", b"\n")
                == source.read(local).replace(b"\r\n", b"\n"), "PACKAGE_DOCUMENT_DRIFT")
    pins = json.loads(source.read("release/assets.json"))
    require(set(pins) == {"ProofFlow-deck.pptx", "ProofFlow-cover.png", "ProofFlow-demo.mp4",
                         "demo-edit-manifest.json"}, "PACKAGE_ASSET_SET")
    for name, pin in pins.items():
        raw = archive.read(name)
        require(sha(raw) == pin["sha256"] and len(raw) == pin["bytes"],
                "PACKAGE_MEDIA_DRIFT")


def verify(path, *, expected_sha256=None):
    require(path.stat().st_size <= MAX_TOTAL, "PACKAGE_SIZE")
    with path.open("rb") as handle:
        package = handle.read(MAX_TOTAL + 1)
    require(len(package) <= MAX_TOTAL, "PACKAGE_SIZE")
    digest = sha(package)
    if expected_sha256 is not None:
        require(re.fullmatch(r"[a-f0-9]{64}", expected_sha256) is not None
                and digest == expected_sha256, "PACKAGE_CHECKPOINT_HASH_MISMATCH")
    # Parse the same bounded bytes that were hashed, even if the path changes.
    with zipfile.ZipFile(io.BytesIO(package)) as archive:
        names = safe_entries(archive)
        manifest = json.loads(archive.read("MANIFEST.json"))
        require(manifest["status"] == "PRIVATE_REVIEW_NOT_RELEASED", "PACKAGE_RELEASE_GATE")
        require(manifest["version"] in (1, 2), "PACKAGE_VERSION")
        require(set(names) == set(manifest["files"]) | {"MANIFEST.json"}, "PACKAGE_FILE_SET")
        for name, expected in manifest["files"].items():
            raw = archive.read(name)
            require(expected == {"sha256": sha(raw), "bytes": len(raw)}, "PACKAGE_HASH_MISMATCH")
        with zipfile.ZipFile(io.BytesIO(archive.read("SOURCE.zip"))) as source:
            safe_entries(source)
            require(source.comment.decode().strip() == manifest["source_commit"],
                    "SOURCE_COMMIT_MISMATCH")
            content = json.loads(source.read("release/deck-content.json"))
            inspect_deck(archive.read("ProofFlow-deck.pptx"), content)
            documents = {name: local for name, local in DOCUMENTS.items() if name in names}
            if manifest["version"] == 2:
                require(set(names) == set(DOCUMENTS) | {
                    "ProofFlow-deck.pptx", "ProofFlow-cover.png", "ProofFlow-demo.mp4",
                    "demo-edit-manifest.json", "SOURCE.zip", "MANIFEST.json"},
                    "PACKAGE_REQUIRED_FILES")
            source_bindings(archive, source, documents=documents)
        submission = json.loads(archive.read("submission.json"))
        public = (json.loads(archive.read("evidence/public-tls.json"))
                  if "evidence/public-tls.json" in names else None)
        release_gate(submission, public)
    return {"verified": True, "files": len(names), "source_commit": manifest["source_commit"],
            "package_sha256": digest, "bytes": len(package),
            "trusted_hash_checked": expected_sha256 is not None}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--verify", type=Path)
    parser.add_argument("--expected-sha256", help="Trusted ZIP hash from private checkpoint")
    parser.add_argument("--output", type=Path)
    parser.add_argument("--artifacts", type=Path)
    parser.add_argument("--evidence", type=Path)
    parser.add_argument("--check-claims", action="store_true")
    args = parser.parse_args()
    if args.verify:
        print(json.dumps(verify(args.verify, expected_sha256=args.expected_sha256)))
        return
    content = check_claims()
    if args.check_claims:
        print("RELEASE_CLAIMS_MATCH_FROZEN_EVIDENCE; no model call or candidate execution")
        return
    require(all((args.output, args.artifacts, args.evidence)), "PACKAGE_PATHS_REQUIRED")
    require(not args.output.resolve().is_relative_to(ROOT), "PACKAGE_MUST_STAY_OUTSIDE_GIT")
    require(git("status", "--porcelain").strip() == b"", "CLEAN_CHECKPOINT_REQUIRED")
    commit = git("rev-parse", "HEAD").decode().strip()
    pinned = json.loads((ROOT / "release/assets.json").read_bytes())
    require(set(pinned) == {"ProofFlow-deck.pptx", "ProofFlow-cover.png", "ProofFlow-demo.mp4",
                           "demo-edit-manifest.json"}, "PACKAGE_ASSET_SET")
    files = {name: git("show", commit + ":" + local) for name, local in DOCUMENTS.items()}
    for name, spec in pinned.items():
        require(spec["source"] in ("evidence", "artifacts")
                and Path(spec["filename"]).name == spec["filename"]
                and "/" not in spec["filename"] and "\\" not in spec["filename"],
                "PACKAGE_ASSET_PATH")
        base = args.evidence if spec["source"] == "evidence" else args.artifacts
        local = base / spec["filename"]
        raw = local.read_bytes()
        require(sha(raw) == spec["sha256"] and len(raw) == spec["bytes"], "REVIEWED_ASSET_CHANGED")
        files[name] = raw
    inspect_deck(files["ProofFlow-deck.pptx"], content)
    png = files["ProofFlow-cover.png"]
    require(png[:8] == b"\x89PNG\r\n\x1a\n"
            and struct.unpack(">II", png[16:24]) == (1920, 1080), "COVER_GEOMETRY")
    files["SOURCE.zip"] = git("archive", "--format=zip", commit)
    with zipfile.ZipFile(io.BytesIO(files["SOURCE.zip"])) as source:
        safe_entries(source)
    require(sum(map(len, files.values())) <= MAX_TOTAL, "PACKAGE_SIZE")
    manifest = {"version": 2, "status": "PRIVATE_REVIEW_NOT_RELEASED", "source_commit": commit,
                "runtime_evidence_checkpoint": content["source_checkpoint"],
                "created_at": datetime.now(UTC).isoformat(),
                "files": {name: {"sha256": sha(raw), "bytes": len(raw)}
                          for name, raw in sorted(files.items())},
                "no_new_cloud_or_provider_call": True,
                "hash_claim": "integrity only; compare ZIP hash to the private Git checkpoint"}
    args.output.parent.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(args.output, "x", compression=zipfile.ZIP_DEFLATED) as archive:
        for name, raw in files.items():
            archive.writestr(name, raw)
        archive.writestr("MANIFEST.json", json.dumps(manifest, sort_keys=True, indent=2))
    print(json.dumps(verify(args.output)))


if __name__ == "__main__":
    main()

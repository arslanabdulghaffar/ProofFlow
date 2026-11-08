"""Offline release-package guard probes; inert bytes only, no candidate execution."""

import io
import json
import stat
import zipfile

import pytest

from scripts.build_release_package import (
    release_gate,
    safe_entries,
    sha,
    source_bindings,
    verify,
    xml,
)


def test_public_demo_evidence_does_not_authorize_public_repository_or_license():
    submission = {"repository_visibility": "private", "release_allowed": False,
                  "license_issued": False, "public_demo_url": "https://192.0.2.1:8443"}
    evidence = {"origin": submission["public_demo_url"], "external_acceptance_passed": True,
                "owner_authorized_activation": True}
    release_gate(submission, evidence)
    for field, value in (("repository_visibility", "public"), ("release_allowed", True),
                         ("license_issued", True)):
        with pytest.raises(ValueError, match="UNAPPROVED_RELEASE_CLAIM"):
            release_gate(submission | {field: value}, evidence)
    for changed in (None, evidence | {"external_acceptance_passed": False},
                    evidence | {"owner_authorized_activation": False},
                    evidence | {"origin": "https://unrelated.invalid"}):
        with pytest.raises(ValueError, match="PUBLIC_URL_WITHOUT_EVIDENCE"):
            release_gate(submission, changed)


def test_historical_private_package_requires_no_public_evidence():
    release_gate({"repository_visibility": "private", "release_allowed": False,
                  "license_issued": False, "public_demo_url": None})


@pytest.mark.parametrize("name", [
    "../escape", "/absolute", "secrets/value.txt", "key.pem", ".env",
    "credentials.json", "C:/absolute", "nested\\escape", ".git/config",
])
def test_archive_rejects_paths_and_private_files(name):
    stream = io.BytesIO()
    with zipfile.ZipFile(stream, "w") as archive:
        archive.writestr(name, b"inert")
    raw = stream.getvalue()
    if "\\" in name:
        # Windows zipfile normalizes separators while writing and while reading.
        raw = raw.replace(name.replace("\\", "/").encode(), name.encode())
    with zipfile.ZipFile(io.BytesIO(raw)) as archive:
        with pytest.raises(ValueError):
            safe_entries(archive)


def test_archive_rejects_symlinks():
    stream = io.BytesIO()
    item = zipfile.ZipInfo("innocent.txt")
    item.create_system = 3
    item.external_attr = (stat.S_IFLNK | 0o777) << 16
    with zipfile.ZipFile(stream, "w") as archive:
        archive.writestr(item, b"/private/target")
    with zipfile.ZipFile(io.BytesIO(stream.getvalue())) as archive:
        with pytest.raises(ValueError, match="ARCHIVE_SYMLINK"):
            safe_entries(archive)


@pytest.mark.parametrize("raw", [
    b'<!DOCTYPE x [<!ENTITY e "bad">]><x>&e;</x>',
    b"<\x00x\x00/\x00>\x00",
    b" " * (2 * 1024 * 1024 + 1),
])
def test_xml_rejects_declarations_alternate_encoding_and_oversize(raw):
    with pytest.raises(ValueError, match="OOXML_DECLARATION_OR_SIZE"):
        xml(raw)


@pytest.mark.parametrize("change", [None, "document", "media"])
def test_self_consistent_outer_manifest_cannot_replace_source_bound_content(change):
    names = ["ProofFlow-deck.pptx", "ProofFlow-cover.png", "ProofFlow-demo.mp4",
             "demo-edit-manifest.json"]
    media = {name: b"original inert bytes" for name in names}
    pins = {name: {"sha256": sha(raw), "bytes": len(raw)} for name, raw in media.items()}
    outer, source_bytes = io.BytesIO(), io.BytesIO()
    with zipfile.ZipFile(source_bytes, "w") as source:
        source.writestr("release/assets.json", json.dumps(pins))
        source.writestr("release/README.md", b"original\n")
    with zipfile.ZipFile(outer, "w") as archive:
        archive.writestr("README.md", b"changed" if change == "document" else b"original\r\n")
        for name, raw in media.items():
            archive.writestr(name, b"replaced" if change == "media" else raw)
    with zipfile.ZipFile(outer) as archive, zipfile.ZipFile(source_bytes) as source:
        if change:
            with pytest.raises(ValueError, match="PACKAGE_(DOCUMENT|MEDIA)_DRIFT"):
                source_bindings(archive, source, documents={"README.md": "release/README.md"})
        else:
            source_bindings(archive, source, documents={"README.md": "release/README.md"})


def test_trusted_checkpoint_hash_is_checked_before_archive_parsing(tmp_path):
    package = tmp_path / "package.zip"
    package.write_bytes(b"replaced archive")
    with pytest.raises(ValueError, match="PACKAGE_CHECKPOINT_HASH_MISMATCH"):
        verify(package, expected_sha256="0" * 64)

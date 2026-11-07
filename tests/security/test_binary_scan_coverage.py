"""Synthetic scanner protocol fixtures; no runtime/candidate execution."""

import json

import pytest

from scripts.audit_gvisor_scan import summarize


def report(*extra):
    return b"\n".join(json.dumps(m).encode() for m in [{"config": {
        "scanner_name": "govulncheck", "scan_mode": "binary", "scan_level": "symbol",
        "db": "https://vuln.go.dev",
    }}, *extra])


SBOM = {"SBOM": {"go_version": "go1.27.3", "modules": [
    {"path": "example.test/synthetic", "version": "v1.0.0"}]}}
OSV = {"osv": {"id": "GO-SYNTHETIC", "summary": "Fixture only"}}


@pytest.mark.parametrize("code", [0, 1])
def test_missing_metadata_never_becomes_clean(code):
    result = summarize(report(), code)
    assert result["coverage"] == "NOT_ANALYZED"
    assert result["release_clearance"] is False


def test_zero_exit_with_finding_still_requires_review():
    frame = {"module": "example.test/synthetic", "version": "v1.0.0"}
    result = summarize(report(SBOM, OSV, {"finding": {
        "osv": "GO-SYNTHETIC", "trace": [frame]}}), 0)
    assert result["disposition"] == "REVIEW_REQUIRED"
    assert result["advisories"][0]["levels"] == {"module": 1}
    assert not result["release_clearance"]


def test_levels_and_repeated_frames_are_not_extra_vulnerabilities():
    frame = {"module": "example.test/synthetic", "package": "example.test/synthetic/p",
             "function": "Unsafe", "version": "v1.0.0"}
    finding = {"finding": {"osv": "GO-SYNTHETIC", "trace": [frame]}}
    result = summarize(report(SBOM, OSV, finding, finding), 0)
    assert len(result["advisories"]) == 1
    assert result["advisories"][0]["levels"] == {"symbol": 2}
    assert result["advisories"][0]["distinct_frames"] == 1


def test_absence_is_scoped_not_release_clearance():
    result = summarize(report(SBOM), 0)
    assert result["disposition"] == "NO_KNOWN_GO_MATCHES"
    assert not result["release_clearance"]


def test_scanner_warnings_survive_success():
    result = summarize(report(SBOM, {"progress": {
        "message": "warning: failed to extract build system specification"}}), 0)
    assert result["warnings"] == ["warning: failed to extract build system specification"]
    assert result["coverage"] == "GO_BINARY_ANALYSIS_COMPLETED"
    assert not result["release_clearance"]


def test_error_with_partial_output_is_uncovered():
    assert summarize(report(SBOM), 1)["coverage"] == "NOT_ANALYZED"


def test_missing_versions_is_incomplete():
    sbom = {"SBOM": {"go_version": "go1.27.3", "modules": [{"path": "example.test"}]}}
    assert summarize(report(sbom), 0)["coverage"] == "INCOMPLETE_BUILD_METADATA"


@pytest.mark.parametrize("raw", [b"", b"{}", b"[]", report(SBOM) + b"{",
                                  report(SBOM, {"finding": {"osv": "MISSING"}})])
def test_malformed_or_unattributed_output_fails(raw):
    with pytest.raises((ValueError, KeyError)):
        summarize(raw, 0)

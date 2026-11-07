"""Summarize static Go binary analysis; never equate process success with safety.

Input is local govulncheck -mode=binary -json output, not candidate code. The
caller binds the scanned file hash separately. This reports coverage and matched
advisories, not exploitability, release approval, or native C/kernel coverage.
"""

import json
from collections import Counter
from pathlib import Path


def summarize(raw: bytes, returncode: int) -> dict:
    if len(raw) > 8_000_000:
        raise ValueError("SCAN_REPORT_TOO_LARGE")
    text = raw.decode("utf-8")
    decoder = json.JSONDecoder()
    messages = []
    offset = 0
    while offset < len(text):
        if text[offset].isspace():
            offset += 1
            continue
        message, offset = decoder.raw_decode(text, offset)
        if not isinstance(message, dict) or len(message) != 1:
            raise ValueError("INVALID_SCAN_MESSAGE")
        messages.append(message)
    configs = [m["config"] for m in messages if "config" in m]
    sboms = [m["SBOM"] for m in messages if "SBOM" in m]
    findings = [m["finding"] for m in messages if "finding" in m]
    if len(configs) != 1:
        raise ValueError("SCAN_CONFIG_MISSING_OR_DUPLICATE")
    config = configs[0]
    if (config.get("scanner_name") != "govulncheck"
            or config.get("scan_mode") != "binary"
            or config.get("scan_level") != "symbol"
            or config.get("db") != "https://vuln.go.dev"):
        raise ValueError("UNEXPECTED_SCAN_MODE")
    warnings = [m["progress"]["message"] for m in messages if "progress" in m
                and "warning" in m["progress"].get("message", "").lower()]
    result = {"config": config, "exit": returncode, "release_clearance": False,
              "warnings": warnings}
    if returncode != 0 or len(sboms) != 1 or not sboms[0].get("modules"):
        return result | {"coverage": "NOT_ANALYZED", "finding_messages": len(findings)}
    sbom = sboms[0]
    if not sbom.get("go_version") or not all(
            isinstance(m, dict) and m.get("path") and m.get("version")
            for m in sbom["modules"]):
        return result | {"coverage": "INCOMPLETE_BUILD_METADATA",
                         "finding_messages": len(findings)}
    advisory_data = {m["osv"]["id"]: m["osv"] for m in messages if "osv" in m}
    groups = {}
    for finding in findings:
        identifier = finding["osv"]
        if identifier not in advisory_data or not finding.get("trace"):
            raise ValueError("FINDING_WITHOUT_ADVISORY_OR_TRACE")
        # Preserve distinct levels: a module match is not a vulnerable function.
        frame = finding["trace"][0]
        level = ("symbol" if frame.get("function") else
                 "package" if frame.get("package") else "module")
        if not frame.get("module"):
            raise ValueError("FINDING_MODULE_MISSING")
        group = groups.setdefault(identifier, {"levels": Counter(), "frames": set(),
                                               "fixed_versions": set()})
        group["levels"][level] += 1
        group["frames"].add(json.dumps(frame, sort_keys=True))
        if finding.get("fixed_version"):
            group["fixed_versions"].add(finding["fixed_version"])
    advisories = []
    for identifier, group in sorted(groups.items()):
        osv = advisory_data[identifier]
        advisories.append({
            "id": identifier, "aliases": osv.get("aliases", []),
            "summary": osv.get("summary", ""), "levels": dict(group["levels"]),
            "distinct_frames": len(group["frames"]),
            "fixed_versions": sorted(group["fixed_versions"]),
            "reference": "https://pkg.go.dev/vuln/" + identifier,
        })
    return result | {
        "coverage": "GO_BINARY_ANALYSIS_COMPLETED", "sbom": sbom,
        "finding_messages": len(findings), "advisories": advisories,
        "disposition": "REVIEW_REQUIRED" if findings else "NO_KNOWN_GO_MATCHES",
        "limitations": "Requested symbol analysis can fall back to module matches. Symbol "
                       "presence is not runtime reachability. Missing main-module versions, "
                       "native code and advisory database omissions are not cleared.",
    }


def main():
    import argparse

    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("report", type=Path)
    parser.add_argument("--exit-code", required=True, type=int)
    args = parser.parse_args()
    print(json.dumps(summarize(args.report.read_bytes(), args.exit_code), indent=2))


if __name__ == "__main__":
    main()

"""Offline edit of retained private recordings. No API, candidate execution or upload.

Run on Linux with FFmpeg against the private evidence directory. Original videos and
failed harness receipts remain unchanged. The manifest discloses every cut and hold.
"""

import argparse
import hashlib
import json
import subprocess
from pathlib import Path

AI = "page@f4ed291cae0bc0e795c0e5103886fb61.webm"
LOOP = "page@43817ee9a2577674c9752e90e8f7eecc.webm"
FONT = "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf"


def require(condition):
    if not condition:
        raise RuntimeError("RETAINED_DEMO_EVIDENCE_MISMATCH")


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("evidence", type=Path)
    options = parser.parse_args()
    evidence = options.evidence.resolve()
    record = json.loads(
        (evidence / "phase6-browser-9226e15095a441a48272c48e2ffe8f48.json").read_bytes()
    )
    loop = json.loads((evidence / "phase6-containment-recording.json").read_bytes())
    readback = json.loads((evidence / "phase6-containment-recording-readback.json").read_bytes())
    case = record["cases"][0]
    repair, batch = case["repair_result"], case["batch_result"]
    require(record["provider_calls"] == 1 and repair["mode"] == "ai_repair")
    require(repair["state"] == "AWAITING_APPROVAL" and batch["state"] == "COMPLETED")
    require(len(repair["checks"]) == 3)
    require(all(c["cleanup_confirmed"] and c["comparison"] == "match" for c in repair["checks"]))
    require(record["cleanup_confirmed"] and loop["cleanup_confirmed"])
    require(not record["completed"] and not loop["completed"])  # Preserve harness failures.
    require(record["reconciled_no_retry"] and loop["reconciled_no_retry"])
    require(readback["completed"] and readback["worker"]["state"] == "CLEANED")
    require(digest(evidence / LOOP) == loop["video_sha256"])
    output = evidence / "phase6-private-ai-demo-v2.mp4"
    if output.exists():
        raise RuntimeError("REVIEW_EXISTING_RECORDING_BEFORE_REBUILD")
    work = evidence / "phase6-demo-edit-v2"
    work.mkdir(exist_ok=False)
    scenes = []

    def run(args):
        return subprocess.run(  # noqa: S603 - fixed local FFmpeg operations, private own recordings
            args, cwd=work, check=True, capture_output=True, timeout=180
        )

    def render(kind, seconds, caption, *, source=None, start=0, title=None, body=None):
        index = len(scenes)
        name = f"scene-{index:02d}"
        label = work / (name + "-caption.txt")
        label.write_text(caption, encoding="utf-8")
        args = ["ffmpeg", "-hide_banner", "-loglevel", "error", "-n"]
        if kind == "card":
            args += ["-f", "lavfi", "-i", "color=c=0x102f36:s=1366x1000:r=25"]
            (work / (name + "-title.txt")).write_text(title, encoding="utf-8")
            (work / (name + "-body.txt")).write_text(body, encoding="utf-8")
            vf = (
                f"drawtext=fontfile={FONT}:textfile={name}-title.txt:expansion=none:"
                "fontsize=46:fontcolor=0x81e6cf:x=72:y=150,"
                f"drawtext=fontfile={FONT}:textfile={name}-body.txt:expansion=none:"
                "fontsize=26:line_spacing=18:fontcolor=white:x=72:y=285"
            )
        else:
            if kind == "hold":
                frame = work / (name + ".png")
                run(
                    [
                        "ffmpeg",
                        "-hide_banner",
                        "-loglevel",
                        "error",
                        "-n",
                        "-ss",
                        str(start),
                        "-i",
                        str(evidence / source),
                        "-frames:v",
                        "1",
                        str(frame),
                    ]
                )
                args += ["-loop", "1", "-framerate", "25", "-i", str(frame)]
            else:
                args += ["-ss", str(start), "-i", str(evidence / source)]
            vf = "fps=25,pad=1366:1000:0:0:color=0x102f36"
        vf += (
            f",drawtext=fontfile={FONT}:textfile={name}-caption.txt:expansion=none:"
            "fontsize=22:line_spacing=8:fontcolor=white:x=40:y=924,setsar=1"
        )
        args += [
            "-t",
            str(seconds),
            "-an",
            "-vf",
            vf,
            "-c:v",
            "libx264",
            "-preset",
            "fast",
            "-crf",
            "20",
            "-pix_fmt",
            "yuv420p",
            "-threads",
            "2",
            name + ".mp4",
        ]
        run(args)
        scenes.append(
            {
                "kind": kind,
                "duration_seconds": seconds,
                "source": source,
                "source_start_seconds": start,
                "caption": caption,
                "title": title,
                "body": body,
                "segment_sha256": digest(work / (name + ".mp4")),
            }
        )
        print(json.dumps({"rendered_scene": index, "kind": kind}), flush=True)

    render(
        "card",
        10,
        "PRIVATE REVIEW COPY | Nov 8, 2026 KST | No publication or submission",
        title="ProofFlow",
        body="Checked repairs before the next batch.\n\n"
        "A revenue import can run successfully and still assign the wrong owner.\n"
        "Approve the rules. Inspect the records. Check the repair.\n\n"
        "Actual private browser recording, synthetic inputs and real Vultr inference.\n"
        "Edited with labeled pauses, receipt summaries and a separate loop segment.\n"
        "Approvals are automated tests, not independent human sign-off.",
    )
    render(
        "clip",
        6.25,
        "1 / Exact contract, then isolated original execution. Browser time is unaccelerated.",
        source=AI,
    )
    render(
        "hold",
        10,
        "PAUSED FRAME / The owner witness differs. The original result is not accepted.",
        source=AI,
        start=6.25,
    )
    render(
        "clip",
        14.55,
        "2 / One actual Vultr request. Model explanations remain unverified; checks decide.",
        source=AI,
        start=6.25,
    )
    render(
        "hold",
        12,
        "PAUSED FRAME / Candidate + two protected checks match; cleanup confirmed. "
        "Still awaiting approval.",
        source=AI,
        start=20.8,
    )
    render(
        "clip",
        0.52,
        "3 / Exact-version test approval, then different inputs. No GitHub action is performed.",
        source=AI,
        start=20.8,
    )
    render(
        "hold",
        8,
        "PAUSED FRAME / Exact preview and deliberate test approval. "
        "This does not approve a GitHub write.",
        source=AI,
        start=21.32,
    )
    render(
        "clip",
        3.88,
        "3 / The approved version runs again on different input bytes.",
        source=AI,
        start=21.32,
    )
    render(
        "card",
        14,
        "RECEIPT SUMMARY / Read from the retained actual run; "
        "this is not a reconstructed product screen.",
        title="The fresh batch completed",
        body="Real Vultr repair: 1 call; 3 checks matched and cleaned up.\n"
        "Candidate source changed; the downloaded evidence ZIP is retained privately.\n"
        "An exact-version synthetic test approval enabled different input bytes.\n\n"
        f"Batch {case['batch']}\n"
        f"Recorded state: {batch['state']}\n\n"
        "$0.027853 was reserved for this repair. This is not an invoice.\n"
        "The raw clip moved on before a readable completed-batch frame was captured.",
    )
    render(
        "card",
        7,
        "SEPARATE RECORDING / Deliberate loop, not model output; zero additional inference calls.",
        title="What if uploaded code never stops?",
        body="A deliberately nonterminating Python upload runs only on the isolated worker.\n\n"
        "The following browser segment is a separate real containment test.\n"
        "It is not a rejected AI proposal or a continuous extension of the first run.",
    )
    render(
        "clip",
        24.88,
        "4 / Unaccelerated separate loop test. No accepted result is published.",
        source=LOOP,
    )
    render(
        "hold",
        10,
        "PAUSED FRAME + READBACK / Signal 9; no accepted output; "
        "cleanup confirmed; kernel writers absent.",
        source=LOOP,
        start=24.5,
    )
    render(
        "card",
        18,
        "Scope: synthetic merchant-revenue contract. "
        "No public service, security certification or customer ROI claim.",
        title="Evidence before confidence",
        body="Frozen synthetic evaluation: full ProofFlow repaired 15/18.\n"
        "Wrong acceptances: 0/15. The deterministic rebuild repaired 18/18.\n"
        "One repeat, shared templates, no independent human oracle review.\n\n"
        "Both recording harnesses stopped on later check errors; receipts stay failed.\n"
        "Read-only worker records confirm loop termination and cleanup.\n"
        "Live product states and the verifier were not changed to make tests pass.\n\n"
        "Original clips, exact bundle and edit manifest remain available privately.",
    )
    concat = work / "concat.txt"
    concat.write_text("".join(f"file 'scene-{i:02d}.mp4'\n" for i in range(len(scenes))))
    run(
        [
            "ffmpeg",
            "-hide_banner",
            "-loglevel",
            "error",
            "-n",
            "-f",
            "concat",
            "-safe",
            "1",
            "-i",
            str(concat),
            "-c",
            "copy",
            "-movflags",
            "+faststart",
            str(output),
        ]
    )
    probe = json.loads(
        run(
            ["ffprobe", "-v", "error", "-show_format", "-show_streams", "-of", "json", str(output)]
        ).stdout
    )
    manifest = {
        "scope": "private edited silent captioned demo, not public release",
        "raw_sources": {name: digest(evidence / name) for name in (AI, LOOP)},
        "scenes": scenes,
        "output_sha256": digest(output),
        "media": probe,
        "original_receipts_remain_failed": True,
        "edit_tool": "local WSL FFmpeg 6.1.1-3ubuntu5; no cloud render",
    }
    (evidence / "phase6-private-ai-demo-v2-manifest.json").write_text(
        json.dumps(manifest, indent=2)
    )
    print(
        json.dumps(
            {
                "file": output.name,
                "sha256": manifest["output_sha256"],
                "seconds": probe["format"]["duration"],
            }
        )
    )


if __name__ == "__main__":
    main()

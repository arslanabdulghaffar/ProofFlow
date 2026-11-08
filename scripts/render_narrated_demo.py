"""Offline guided edit of pinned real footage; no cloud calls or product actions.

Run with Linux FFmpeg. Narration WAVs and cursor PNGs are prepared locally.
The original recording and evidence remain unchanged. New output requires owner review.
"""

import argparse
import hashlib
import json
import math
import subprocess
from pathlib import Path


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def run(args, cwd):
    return subprocess.run(  # noqa: S603 - fixed local media commands, no candidate source
        args, cwd=cwd, check=True, capture_output=True, timeout=240)


def position(points, duration, axis):
    """Smooth acceleration/deceleration between explicit editorial guide positions."""
    result = str(points[-1][axis])
    for left, right in reversed(list(zip(points, points[1:], strict=False))):
        start, stop = left[0] * duration, right[0] * duration
        u = f"max(0,min(1,(t-{start:.6f})/{stop-start:.6f}))"
        ease = f"({u}*{u}*(3-2*{u}))"
        value = f"({left[axis]}+({right[axis]-left[axis]})*{ease})"
        result = f"if(lt(t,{stop:.6f}),{value},{result})"
    return result


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('evidence', type=Path)
    p.add_argument('work', type=Path)
    options = p.parse_args()
    evidence, work = options.evidence.resolve(), options.work.resolve()
    original = evidence / 'phase6-private-ai-demo-v2.mp4'
    plan = json.loads((work / 'voice-timing.json').read_bytes())
    if sha(original) != plan['source_video_sha256']:
        raise ValueError('SOURCE_VIDEO_CHANGED')
    source_manifest = json.loads(
        (evidence / 'phase6-private-ai-demo-v2-manifest.json').read_bytes())
    source = evidence / 'phase6-demo-edit-v2'
    final = work / 'ProofFlow-narrated-review-v3.mp4'
    if final.exists():
        raise ValueError('PRESERVE_EXISTING_REVIEW')
    offset = 0.0
    subtitles = []
    font = '/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf'
    for scene in plan['scenes']:
        n = scene['scene']
        video = source / f'scene-{n:02d}.mp4'
        if sha(video) != source_manifest['scenes'][n]['segment_sha256']:
            raise ValueError('SOURCE_SEGMENT_CHANGED')
        if sha(work / scene['audio']) != scene['audio_sha256']:
            raise ValueError('NARRATION_CHANGED')
        raw_duration = source_manifest['scenes'][n]['duration_seconds']
        lead = 3.0 if n == 1 else 0.0
        duration = math.ceil(max(scene['minimum_seconds'],
                                raw_duration / scene['speed'] + lead,
                                scene['audio_seconds'] + 1.1) * 25) / 25
        scene.update(start_seconds=offset, rendered_seconds=duration,
                     start_freeze_seconds=lead)
        label = work / f'label-{n:02d}.txt'
        label.write_text(scene['label'], encoding='utf-8')
        args = ['ffmpeg', '-hide_banner', '-loglevel', 'error', '-n', '-i', str(video),
                '-i', str(work / scene['audio'])]
        filters = [f"[0:v]setpts=(PTS-STARTPTS)/{scene['speed']},"
                   f"tpad=start_mode=clone:start_duration={lead}:stop_mode=clone:"
                   f"stop_duration={duration},trim=duration={duration},fps=25,"
                   "drawbox=x=0:y=900:w=1366:h=100:color=0x102f36:t=fill,"
                   f"drawtext=fontfile={font}:textfile={label.name}:expansion=none:"
                   "fontsize=21:fontcolor=white:x=30:y=925[v0]"]
        output = 'v0'
        points = scene['cursor']
        if points:
            args += ['-loop', '1', '-i', str(work / 'cursor.png'),
                     '-loop', '1', '-i', str(work / 'pulse.png')]
            x, y = position(points, duration, 1), position(points, duration, 2)
            pulses = scene.get('pulses', [])
            enabled = '+'.join(f'between(t,{t*duration:.5f},{t*duration+.35:.5f})'
                               for t in pulses) or '0'
            filters += [f"[v0][3:v]overlay=x='{x}-30':y='{y}-30':"
                        f"enable='{enabled}'[vp]",
                        f"[vp][2:v]overlay=x='{x}':y='{y}'[v1]"]
            output = 'v1'
        filters += [f'[1:a]adelay=500:all=1,apad,atrim=duration={duration}[a]']
        filter_path = work / f'filter-{n:02d}.txt'
        filter_path.write_text(';\n'.join(filters))
        args += ['-filter_complex_script', str(filter_path), '-map', f'[{output}]',
                 '-map', '[a]', '-t', str(duration), '-c:v', 'libx264', '-crf', '19',
                 '-preset', 'fast', '-pix_fmt', 'yuv420p', '-threads', '2',
                 '-filter_complex_threads', '2', '-c:a', 'aac', '-b:a', '160k',
                 '-ar', '48000', '-movflags', '+faststart', f'guided-{n:02d}.mp4']
        run(args, work)
        scene['rendered_sha256'] = sha(work / f'guided-{n:02d}.mp4')
        # Full spoken transcript, split into readable sentence-level timed cues.
        sentences = [s.strip() + '.' for s in scene['narration'].split('.') if s.strip()]
        total = sum(len(s) for s in sentences)
        at = offset + .5
        for sentence in sentences:
            stop = at + scene['audio_seconds'] * len(sentence) / total
            subtitles.append((at, stop, sentence))
            at = stop
        offset += duration
        print(json.dumps({'scene': n, 'duration': duration}), flush=True)
    (work / 'concat.txt').write_text(''.join(
        f"file 'guided-{n:02d}.mp4'\n" for n in range(len(plan['scenes']))))
    run(['ffmpeg', '-hide_banner', '-loglevel', 'error', '-n', '-f', 'concat',
         '-safe', '1', '-i', 'concat.txt', '-c:v', 'copy', '-c:a', 'aac', '-b:a', '160k',
         '-af', 'loudnorm=I=-16:TP=-1.5:LRA=11', '-ar', '48000', '-movflags', '+faststart',
         str(final)], work)
    def timestamp(seconds):
        milliseconds = round(seconds * 1000)
        seconds, ms = divmod(milliseconds, 1000)
        minutes, sec = divmod(seconds, 60)
        hours, minute = divmod(minutes, 60)
        return f'{hours:02d}:{minute:02d}:{sec:02d},{ms:03d}'
    (work / 'ProofFlow-narration-v3.srt').write_text('\n\n'.join(
        f'{i}\n{timestamp(a)} --> {timestamp(b)}\n{text}'
        for i, (a, b, text) in enumerate(subtitles, 1)) + '\n', encoding='utf-8')
    plan.update(output_sha256=sha(final), duration_seconds=offset,
                no_new_provider_calls=True, source_recording_unchanged=True,
                subtitles_note='Sentence cue timing estimated from spoken segment duration.')
    (work / 'ProofFlow-narrated-review-v3-manifest.json').write_text(
        json.dumps(plan, indent=2), encoding='utf-8')
    print(json.dumps({'output': str(final), 'seconds': offset,
                      'sha256': plan['output_sha256']}))


if __name__ == '__main__':
    main()

"""Local presentation narration, not an application agent/provider call.

Use an isolated media-tool environment with kokoro-onnx 0.6.1, onnxruntime 1.31.1
and soundfile 0.14.0. Models come from the documented upstream release and remain
outside Git. Never feed candidate code to this tool.
"""

import argparse
import hashlib
import json
from pathlib import Path

import onnxruntime as rt
import soundfile as sf
from kokoro_onnx import Kokoro

PINS = {
    'kokoro-v1.0.onnx': 'beb0d1848dee9a49da392cc3df26958d46cfa35d321edf434f52949153f0df3a',
    'voices-v1.0.bin': 'bca610b8308e8d99f32e6fe4197e7ec01679264efed0cac9140fe9c29f1fbf7d',
}


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('plan', type=Path)
    p.add_argument('models', type=Path)
    p.add_argument('output', type=Path)
    args = p.parse_args()
    for name, digest in PINS.items():
        if hashlib.sha256((args.models / name).read_bytes()).hexdigest() != digest:
            raise ValueError('NARRATION_MODEL_CHANGED')
    plan = json.loads(args.plan.read_bytes())
    args.output.mkdir(exist_ok=False)
    options = rt.SessionOptions()
    options.intra_op_num_threads, options.inter_op_num_threads = 4, 1
    session = rt.InferenceSession(str(args.models / 'kokoro-v1.0.onnx'),
                                  sess_options=options, providers=['CPUExecutionProvider'])
    voice = Kokoro.from_session(session, str(args.models / 'voices-v1.0.bin'))
    if plan['voice'] not in voice.voices:
        raise ValueError('UNKNOWN_NARRATION_VOICE')
    for scene in plan['scenes']:
        samples, rate = voice.create(scene['narration'], voice=plan['voice'],
                                     speed=1.0, lang='en-us')
        name = f"voice-{scene['scene']:02d}.wav"
        sf.write(str(args.output / name), samples, rate)
        scene.update(audio=name, audio_seconds=len(samples) / rate,
                     audio_sha256=hashlib.sha256((args.output / name).read_bytes()).hexdigest())
        print(json.dumps({'scene': scene['scene'], 'seconds': scene['audio_seconds']}),
              flush=True)
    (args.output / 'voice-timing.json').write_text(json.dumps(plan, indent=2), encoding='utf-8')


if __name__ == '__main__':
    main()

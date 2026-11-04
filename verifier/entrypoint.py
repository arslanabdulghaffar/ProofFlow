"""One bounded request over inherited pipes; unexpected failures produce no report."""

import sys

from verifier.protocol import MAX_REQUEST, process


def main():
    raw = sys.stdin.buffer.read(MAX_REQUEST + 1)
    if len(raw) > MAX_REQUEST:
        return 2
    try:
        response = process(raw)
    except Exception:
        # Never return native exception strings, uploaded bytes or a success fallback.
        return 3
    sys.stdout.buffer.write(response)
    sys.stdout.buffer.flush()
    return 0


if __name__ == "__main__":
    sys.exit(main())

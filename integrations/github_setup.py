"""Fixed dispatcher-only credentials; absent configuration disables integration."""

import json
import os
import stat

from integrations.github_app import GitHubApp, GitHubConfig, GitHubFailure, _pairs, app_jwt

DIRECTORY = "/etc/proofflow-github"


def load_github_app():
    descriptors = []
    try:
        root = os.open(DIRECTORY, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
        descriptors.append(root)
        info = os.fstat(root)
        if info.st_uid != os.geteuid() or stat.S_IMODE(info.st_mode) != 0o700:
            raise GitHubFailure("GITHUB_SECRET_DIRECTORY_UNSAFE")
        names = set(os.listdir(root))
        if not names:
            return None
        if names != {"configuration.json", "private-key.pem"}:
            raise GitHubFailure("GITHUB_SETUP_INCOMPLETE")
        values = {}
        for name, limit in (("configuration.json", 4096), ("private-key.pem", 32768)):
            pin = os.open(name, os.O_PATH | os.O_NOFOLLOW, dir_fd=root)
            descriptors.append(pin)
            before = os.fstat(pin)
            if (
                not stat.S_ISREG(before.st_mode)
                or before.st_uid != os.geteuid()
                or before.st_nlink != 1
                or stat.S_IMODE(before.st_mode) != 0o400
                or not 1 <= before.st_size <= limit
            ):
                raise GitHubFailure("GITHUB_SECRET_FILE_UNSAFE")
            reader = os.open(f"/proc/self/fd/{pin}", os.O_RDONLY | os.O_CLOEXEC)
            descriptors.append(reader)
            raw = os.read(reader, limit + 1)
            after = os.fstat(reader)

            def identity(s):
                return (s.st_dev, s.st_ino, s.st_size, s.st_mtime_ns, s.st_ctime_ns)

            if identity(before) != identity(after) or len(raw) != before.st_size:
                raise GitHubFailure("GITHUB_SECRET_CHANGED")
            values[name] = raw
        config = GitHubConfig(**json.loads(values["configuration.json"], object_pairs_hook=_pairs))
        app_jwt(values["private-key.pem"], config.client_id, 1)  # Validate RSA before network use.
        return GitHubApp(config, values["private-key.pem"])
    except FileNotFoundError:
        # An absent mount on pre-integration images is intentionally disabled.
        if not descriptors:
            return None
        raise GitHubFailure("GITHUB_SETUP_UNAVAILABLE") from None
    except (OSError, ValueError, TypeError):
        raise GitHubFailure("GITHUB_SETUP_UNAVAILABLE") from None
    finally:
        for descriptor in reversed(descriptors):
            os.close(descriptor)

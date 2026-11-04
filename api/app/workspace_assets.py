"""Private Linux workspace directories selected solely by DB-authorized UUIDs."""

import os
import stat
from contextlib import contextmanager
from uuid import UUID

from api.app.assets import AssetError, put_asset, read_asset
from api.app.product_store import ProductFailure


class WorkspaceAssets:
    def __init__(self, directory_fd):
        self.root = directory_fd
        info = os.fstat(self.root)
        if (not stat.S_ISDIR(info.st_mode) or info.st_uid != os.geteuid()
                or stat.S_IMODE(info.st_mode) != 0o700):
            raise ProductFailure("ASSET_ROOT_INVALID")

    def _directory(self, workspace, *, create):
        if type(workspace) is not UUID:
            raise ProductFailure("ASSET_WORKSPACE_INVALID")
        if create:
            try:
                os.mkdir(workspace.hex, 0o700, dir_fd=self.root)
                os.fsync(self.root)
            except FileExistsError:
                pass
        fd = os.open(workspace.hex, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW, dir_fd=self.root)
        info = os.fstat(fd)
        if (info.st_uid != os.geteuid() or stat.S_IMODE(info.st_mode) != 0o700
                or info.st_dev != os.fstat(self.root).st_dev):
            os.close(fd)
            raise ProductFailure("ASSET_WORKSPACE_UNSAFE")
        return fd

    @contextmanager
    def lease(self, workspace):
        import fcntl
        if type(workspace) is not UUID:
            raise ProductFailure("ASSET_WORKSPACE_INVALID")
        root = os.open(".", os.O_RDONLY | os.O_DIRECTORY, dir_fd=self.root)
        try:
            fcntl.flock(root, fcntl.LOCK_SH)
            try:
                os.stat(".deleted-" + workspace.hex, dir_fd=root, follow_symlinks=False)
            except FileNotFoundError:
                yield
            else:
                raise ProductFailure("ACCESS_DENIED")
        finally:
            os.close(root)

    def assert_live(self, workspace):
        with self.lease(workspace):
            pass

    def put(self, workspace, raw):
        fd = None
        try:
            with self.lease(workspace):
                fd = self._directory(workspace, create=True)
                return put_asset(fd, raw)
        except (OSError, AssetError):
            raise ProductFailure("ASSET_PUBLICATION_UNCERTAIN") from None
        finally:
            if fd is not None:
                os.close(fd)

    def read(self, workspace, digest):
        fd = None
        try:
            with self.lease(workspace):
                fd = self._directory(workspace, create=False)
                return read_asset(fd, digest)
        except (OSError, AssetError):
            raise ProductFailure("ASSET_READ_FAILED") from None
        finally:
            if fd is not None:
                os.close(fd)

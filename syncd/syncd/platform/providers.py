from __future__ import annotations

import os
import stat
import sys

from syncd.platform.paths import data_dir

_IS_WINDOWS = sys.platform == "win32"


def providers_dir() -> str:
    return os.path.join(data_dir(), "providers")


def resolve_provider_binary(name: str) -> str:
    directory = providers_dir()
    if not name or name in (".", "..") or "/" in name or "\\" in name:
        raise RuntimeError(f"external provider must be a file name inside {directory}, got {name!r}")
    path = os.path.join(directory, name)
    if not os.path.isfile(path):
        raise RuntimeError(f"external provider {name!r} not found in {directory}")
    if not _IS_WINDOWS:
        for p in (directory, path):
            st = os.stat(p)
            if st.st_uid != os.getuid() or st.st_mode & (stat.S_IWGRP | stat.S_IWOTH):
                raise RuntimeError(f"{p} must be owned by the current user and not writable by others")
    return path

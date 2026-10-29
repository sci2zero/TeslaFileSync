from __future__ import annotations

import os
import sys

_IS_WINDOWS = sys.platform == "win32"


def data_dir() -> str:
    if _IS_WINDOWS:
        base = os.environ.get("LOCALAPPDATA") or os.path.expanduser("~/AppData/Local")
    else:
        base = os.environ.get("XDG_DATA_HOME") or os.path.expanduser("~/.local/share")
    return os.path.join(base, "syncd")

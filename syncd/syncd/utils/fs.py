import asyncio
import os
import stat
import sys


def hide_path(path: str) -> None:
    """Set the hidden attribute on Windows. No-op on other platforms."""
    if sys.platform == "win32":
        import ctypes
        FILE_ATTRIBUTE_HIDDEN = 0x2
        ctypes.windll.kernel32.SetFileAttributesW(path, FILE_ATTRIBUTE_HIDDEN)  # type: ignore[attr-defined]


async def remove_socket(path: str) -> None:
    def _remove() -> None:
        try:
            st = os.stat(path)
        except FileNotFoundError:
            return
        if stat.S_ISSOCK(st.st_mode):
            os.remove(path)

    await asyncio.to_thread(_remove)

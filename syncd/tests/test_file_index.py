import os

import pytest

from syncd.sync.file_index import FileEntry, is_safe_rel_path


@pytest.mark.parametrize("path", ["a.txt", "dir/b.txt", "dir\\c.txt", "..hidden"])
def test_safe_paths_are_accepted(path):
    assert is_safe_rel_path(path)


@pytest.mark.parametrize("path", [
    "", "/etc/passwd", "../x", "dir/../../x", "dir\\..\\x",
    "C:\\x", "C:x", "\\\\server\\share\\x", ".synak/index.json",
])
def test_unsafe_paths_are_rejected(path):
    assert not is_safe_rel_path(path)


def test_from_dict_rejects_unsafe_path():
    with pytest.raises(ValueError):
        FileEntry.from_dict({"path": "../x", "checksum": "", "modified_time": 0.0, "vector_clock_data": {}})


def test_size_change_is_detected_when_mtime_is_restored(tmp_path):
    from syncd.sync.file_index import FileIndex
    f = tmp_path / "a.txt"
    f.write_text("one")
    index = FileIndex(str(tmp_path), "n1")
    index.scan()
    st = f.stat()
    f.write_text("longer")
    os.utime(f, ns=(st.st_atime_ns, st.st_mtime_ns))
    assert index.scan_one("a.txt")
    assert index.get("a.txt").size == len("longer")

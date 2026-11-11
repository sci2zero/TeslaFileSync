import os
import sys

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


def test_apply_remote_merges_concurrent_vectors(tmp_path):
    from syncd.sync.file_index import FileIndex
    from syncd.sync.vector_clock import VectorClock
    (tmp_path / "a.txt").write_text("local")
    index = FileIndex(str(tmp_path), "n1")
    index.scan()
    remote_clock = VectorClock("n2", {"n2": 1}).to_dict()
    remote = FileEntry(path="a.txt", checksum="x", modified_time=0.0, vector_clock_data=remote_clock)
    index.apply_remote(remote, b"remote")
    merged = index.get("a.txt").get_clock("n1")
    assert merged.equals(VectorClock("n1", {"n1": 1, "n2": 1}))


def test_save_while_entries_are_added_from_another_thread(tmp_path):
    import threading
    from syncd.sync.file_index import FileIndex
    index = FileIndex(str(tmp_path), "n1")
    for i in range(2000):
        index.update(FileEntry(path=f"f{i}", checksum="x", modified_time=0.0, vector_clock_data={}))

    def add():
        for i in range(2000, 6000):
            index.update(FileEntry(path=f"f{i}", checksum="x", modified_time=0.0, vector_clock_data={}))

    old_interval = sys.getswitchinterval()
    sys.setswitchinterval(1e-6)
    try:
        writer = threading.Thread(target=add)
        writer.start()
        while writer.is_alive():
            index.save()
        writer.join()
    finally:
        sys.setswitchinterval(old_interval)
    index.save()
    reloaded = FileIndex(str(tmp_path), "n1")
    reloaded.load()
    assert len(reloaded.all_entries()) == 6000


def test_local_edit_clears_corruption_mark(tmp_path):
    from syncd.sync.file_index import FileIndex
    f = tmp_path / "a.txt"
    f.write_text("one")
    index = FileIndex(str(tmp_path), "n1")
    index.scan()
    index.mark_corrupted("a.txt")
    f.write_text("edited")
    assert index.scan_one("a.txt")
    assert not index.is_corrupted("a.txt")

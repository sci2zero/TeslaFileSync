from syncd.sync.file_index import FileEntry
from syncd.sync.sync_engine import Action, remote_wins, resolve_keep_both


def entry(checksum, mtime):
    return FileEntry(path="f.txt", checksum=checksum, modified_time=mtime, vector_clock_data={})


def test_both_nodes_pick_the_same_winner():
    a, b = entry("aaa", 10.0), entry("bbb", 10.0)
    assert remote_wins(a, b) != remote_wins(b, a)


def test_keep_both_keeps_newer_local_version(tmp_path):
    (tmp_path / "f.txt").write_text("local")
    action = resolve_keep_both(entry("aaa", 20.0), entry("bbb", 10.0), "n1", str(tmp_path))
    assert action == Action.KEEP_LOCAL
    assert not (tmp_path / "f.txt.syncd-conflict.n1").exists()


def test_keep_both_saves_older_local_version(tmp_path):
    (tmp_path / "f.txt").write_text("local")
    action = resolve_keep_both(entry("aaa", 10.0), entry("bbb", 20.0), "n1", str(tmp_path))
    assert action == Action.ACCEPT_REMOTE
    assert (tmp_path / "f.txt.syncd-conflict.n1").read_text() == "local"

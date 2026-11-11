from syncd.sync.file_index import FileEntry, FileIndex
from syncd.sync.providers.p2p import P2PProvider
from syncd.sync.vector_clock import VectorClock


def make_provider(tmp_path):
    (tmp_path / "f.txt").write_text("local")
    p = P2PProvider()
    p._node_id = "n1"
    p._index = FileIndex(str(tmp_path), "n1")
    p._index.scan()
    return p


def incoming(checksum, clock):
    return FileEntry(path="f.txt", checksum=checksum, modified_time=0.0,
                     vector_clock_data=VectorClock("n2", clock).to_dict())


def test_pulled_file_is_rejected_when_local_changed_meanwhile(tmp_path):
    p = make_provider(tmp_path)
    (tmp_path / "f.txt").write_text("edited during session")
    p._index.scan_one("f.txt")
    assert not p._should_accept(incoming("x", {"n1": 1}))


def test_corrupted_file_accepts_same_version(tmp_path):
    p = make_provider(tmp_path)
    local = p._index.get("f.txt")
    p._index.mark_corrupted("f.txt")
    assert p._should_accept(incoming(local.checksum, {"n1": 1}))

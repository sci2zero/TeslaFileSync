import os
import socket

from syncd.utils.fs import remove_socket


async def test_remove_socket_removes(tmp_path):
    sock_path = str(tmp_path / "test.sock")
    s = socket.socket(socket.AF_UNIX)
    s.bind(sock_path)
    s.close()
    assert os.path.exists(sock_path)
    await remove_socket(sock_path)
    assert not os.path.exists(sock_path)


async def test_remove_socket_nonexistent_is_noop(tmp_path):
    await remove_socket(str(tmp_path / "missing.sock"))


async def test_remove_socket_does_not_remove_regular_file(tmp_path):
    p = tmp_path / "not_a_socket.txt"
    p.write_bytes(b"data")
    await remove_socket(str(p))
    assert p.exists()

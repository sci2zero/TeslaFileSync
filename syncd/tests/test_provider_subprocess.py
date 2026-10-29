import asyncio
import sys

import pytest

from syncd.sync.base import SyncContext
from syncd.sync.providers.subprocess import SubprocessProvider


def make_binary(tmp_path, body: str) -> str:
    directory = tmp_path / "syncd" / "providers"
    directory.mkdir(parents=True, exist_ok=True)
    script = directory / "provider"
    script.write_text(f"#!{sys.executable}\nimport json, os, sys, time\n{body}")
    script.chmod(0o755)
    return script.name


@pytest.fixture(autouse=True)
def providers_home(tmp_path, monkeypatch):
    monkeypatch.setenv("XDG_DATA_HOME", str(tmp_path))


def make_context(binary: str) -> SyncContext:
    return SyncContext(pair_id="p", local="/tmp/x", interval=0,
                       provider_config={"binary": binary})


CRASHES_ONCE = """
marker = os.path.join(os.path.dirname(sys.argv[0]), "crashed")
first_run = not os.path.exists(marker)
open(marker, "a").close()
log = open(os.path.join(os.path.dirname(sys.argv[0]), "commands"), "a")
for line in sys.stdin:
    cmd = json.loads(line)["cmd"]
    print(cmd, file=log, flush=True)
    if first_run and cmd == "status":
        sys.exit(1)
    if cmd == "status":
        print(json.dumps({"ok": True, "data": {"state": "idle"}}), flush=True)
    else:
        print(json.dumps({"ok": True}), flush=True)
    if cmd == "stop":
        break
"""


async def test_unresponsive_binary_times_out(tmp_path, monkeypatch):
    monkeypatch.setattr(SubprocessProvider, "RESPONSE_TIMEOUT", 0.2)
    monkeypatch.setattr(SubprocessProvider, "RESTART_DELAY", 60)
    binary = make_binary(tmp_path, 'print(\'{"ok": true}\', flush=True)\nsys.stdin.readline()\ntime.sleep(60)\n')
    provider = SubprocessProvider()
    await provider.start(make_context(binary))

    with pytest.raises(RuntimeError, match="did not respond"):
        await provider.status()

    status = await provider.status()
    assert status.state == "error"
    assert "restarting" in status.error
    await provider.stop()


async def test_crashed_binary_is_restarted_and_stays_paused(tmp_path, monkeypatch):
    monkeypatch.setattr(SubprocessProvider, "RESTART_DELAY", 0.05)
    provider = SubprocessProvider()
    await provider.start(make_context(make_binary(tmp_path, CRASHES_ONCE)))
    await provider.pause()

    with pytest.raises(RuntimeError, match="exited unexpectedly"):
        await provider.status()

    for _ in range(50):
        if (await provider.status()).state == "idle":
            break
        await asyncio.sleep(0.05)
    assert (await provider.status()).state == "idle"
    commands = (tmp_path / "syncd" / "providers" / "commands").read_text().split()
    assert commands[:3] == ["start", "pause", "status"]
    assert commands[3:5] == ["start", "pause"]
    await provider.stop()

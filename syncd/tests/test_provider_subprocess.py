import sys

import pytest

from syncd.sync.base import SyncContext
from syncd.sync.providers.subprocess import SubprocessProvider


def make_binary(tmp_path, body: str) -> str:
    script = tmp_path / "provider"
    script.write_text(f"#!{sys.executable}\nimport sys, time\n{body}")
    script.chmod(0o755)
    return str(script)


def make_context(binary: str) -> SyncContext:
    return SyncContext(pair_id="p", local="/tmp/x", direction="bidirectional", interval=0,
                       provider_config={"binary": binary})


async def test_unresponsive_binary_times_out(tmp_path, monkeypatch):
    monkeypatch.setattr(SubprocessProvider, "RESPONSE_TIMEOUT", 0.2)
    binary = make_binary(tmp_path, 'print(\'{"ok": true}\', flush=True)\nsys.stdin.readline()\ntime.sleep(60)\n')
    provider = SubprocessProvider()
    await provider.start(make_context(binary))

    with pytest.raises(RuntimeError, match="did not respond"):
        await provider.status()

    with pytest.raises(RuntimeError, match="not running"):
        await provider.status()
    await provider.stop()

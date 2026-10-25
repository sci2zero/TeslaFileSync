"""Generic subprocess sync provider — delegates all work to an external binary via stdin/stdout JSON IPC."""

from __future__ import annotations

import asyncio
import dataclasses
import json
import logging
from asyncio.subprocess import PIPE
from typing import Any, ClassVar, NoReturn

from syncd.sync.base import SyncContext, SyncProvider, ProviderStatus

logger = logging.getLogger(__name__)


class SubprocessProvider(SyncProvider):
    """
    Wraps any external binary that speaks the stdin/stdout newline-delimited JSON IPC protocol.

    Commands sent to binary stdin (one JSON line each):
        {"cmd": "start",   "context": <SyncContext dict>}
        {"cmd": "stop"}
        {"cmd": "pause"}
        {"cmd": "resume"}
        {"cmd": "trigger"}
        {"cmd": "status"}

    Each command expects exactly one response line:
        {"ok": true}
        {"ok": true, "data": <ProviderStatus dict>}   # status only
        {"ok": false, "error": "<message>"}

    Binary stderr is forwarded to the Python logger at DEBUG level.
    """

    NAME = "external"
    SCHEMA: dict[str, Any] = {
        "type": "object",
        "properties": {
            "binary": {"type": "string", "description": "Path to the external provider binary"},
        },
        "required": ["binary"],
        "additionalProperties": True,
    }

    _BINARY_KEY: ClassVar[str] = "binary"
    RESPONSE_TIMEOUT: ClassVar[float] = 10.0
    RESTART_DELAY: ClassVar[float] = 5.0
    MAX_RESTART_DELAY: ClassVar[float] = 300.0

    def __init__(self) -> None:
        self._proc: asyncio.subprocess.Process | None = None
        self._stderr_task: asyncio.Task | None = None
        self._restart_task: asyncio.Task | None = None
        self._lock = asyncio.Lock()
        self._context: SyncContext | None = None
        self._paused = False
        self._started = False
        self._stopping = False
        self._failures = 0
        self._last_error = ""

    async def _send(self, cmd: dict[str, Any]) -> dict[str, Any]:
        async with self._lock:
            if self._proc is None:
                raise RuntimeError(f"{self.NAME!r} subprocess is not running")
            try:
                self._proc.stdin.write((json.dumps(cmd) + "\n").encode())
                await self._proc.stdin.drain()
                line = await asyncio.wait_for(self._proc.stdout.readline(), self.RESPONSE_TIMEOUT)
            except TimeoutError:
                await self._fail(f"{self.NAME!r} subprocess did not respond within {self.RESPONSE_TIMEOUT}s")
            except (BrokenPipeError, ConnectionResetError):
                await self._fail(f"{self.NAME!r} subprocess exited unexpectedly")
            if not line:
                await self._fail(f"{self.NAME!r} subprocess exited unexpectedly")
            return json.loads(line)

    async def _fail(self, error: str) -> NoReturn:
        proc, self._proc = self._proc, None
        if proc.returncode is None:
            proc.kill()
        await proc.wait()
        self._last_error = error
        restart_idle = self._restart_task is None or self._restart_task.done()
        if self._started and not self._stopping and restart_idle:
            self._restart_task = asyncio.create_task(self._restart_loop())
        raise RuntimeError(error)

    async def _spawn(self) -> None:
        assert self._context is not None
        self._proc = await asyncio.create_subprocess_exec(
            self._context.provider_config[self._BINARY_KEY], stdin=PIPE, stdout=PIPE, stderr=PIPE
        )
        self._stderr_task = asyncio.create_task(self._drain_stderr(self._proc.stderr))
        resp = await self._send({"cmd": "start", "context": dataclasses.asdict(self._context)})
        if not resp.get("ok"):
            raise RuntimeError(resp.get("error", "subprocess start failed"))

    async def _restart_loop(self) -> None:
        while self._proc is None:
            delay = min(self.RESTART_DELAY * 2 ** self._failures, self.MAX_RESTART_DELAY)
            self._failures += 1
            logger.warning("[%s] %s; restarting in %.0fs", self.NAME, self._last_error, delay)
            await asyncio.sleep(delay)
            try:
                await self._spawn()
                if self._paused:
                    await self._send({"cmd": "pause"})
            except Exception as e:
                self._last_error = str(e)
                if self._proc is not None:
                    self._proc.kill()
                    await self._proc.wait()
                    self._proc = None
        self._failures = 0

    async def start(self, context: SyncContext) -> None:
        self._context = context
        await self._spawn()
        self._started = True

    async def stop(self) -> None:
        self._stopping = True
        if self._restart_task is not None:
            self._restart_task.cancel()
            try:
                await self._restart_task
            except asyncio.CancelledError:
                pass
        proc = self._proc
        if proc is None:
            return
        try:
            await self._send({"cmd": "stop"})
            await asyncio.wait_for(proc.wait(), self.RESPONSE_TIMEOUT)
        except Exception:
            if proc.returncode is None:
                proc.kill()
                await proc.wait()
        finally:
            if self._stderr_task:
                self._stderr_task.cancel()
                try:
                    await self._stderr_task
                except asyncio.CancelledError:
                    pass
            self._proc = None

    async def pause(self) -> None:
        self._paused = True
        await self._send({"cmd": "pause"})

    async def resume(self) -> None:
        self._paused = False
        await self._send({"cmd": "resume"})

    async def trigger(self) -> None:
        await self._send({"cmd": "trigger"})

    async def status(self) -> ProviderStatus:
        assert self._context is not None
        if self._proc is None and self._restart_task is not None and not self._restart_task.done():
            return ProviderStatus(pair_id=self._context.pair_id, state="error", last_sync=0.0,
                                  error=f"{self._last_error}; restarting")
        resp = await self._send({"cmd": "status"})
        data = resp.get("data") or {}
        return ProviderStatus(
            pair_id=data.get("pair_id", self._context.pair_id),
            state=data.get("state", "unknown"),
            last_sync=data.get("last_sync", 0.0),
            error=data.get("error", ""),
            extra=data.get("extra", {}),
        )

    async def _drain_stderr(self, stream: asyncio.StreamReader) -> None:
        while line := await stream.readline():
            logger.debug("[%s] %s", self.NAME, line.decode().rstrip())

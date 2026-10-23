import dataclasses
import time
from typing import Any

import aiohttp.web as web

from syncd.api.control import ConfigError, DaemonControl

VERSION = "0.1.0"
_START_TIME = time.time()


def build_routes() -> list[web.RouteDef]:
    return [
        web.get("/status", handle_status),
        web.get("/config", handle_config),
        web.post("/config/reload", handle_config_reload),
        web.post("/config/save", handle_config_save),
        web.post("/config/apply", handle_config_apply),
        web.get("/pairs", handle_pairs),
        web.post("/pairs/{id}/sync", handle_pair_sync),
        web.post("/pairs/{id}/pause", handle_pair_pause),
        web.post("/pairs/{id}/resume", handle_pair_resume),
        web.get("/peers", handle_peers),
        web.post("/shutdown", handle_shutdown),
    ]


def _json(data: Any, status: int = 200) -> web.Response:
    return web.Response(
        status=status,
        content_type="application/json",
        text=__import__("json").dumps(data),
    )


def _error(message: str, status: int) -> web.Response:
    return _json({"error": message}, status=status)


def _daemon(request: web.Request) -> DaemonControl:
    return request.app["daemon"]


async def handle_status(request: web.Request) -> web.Response:
    statuses = [dataclasses.asdict(s) for s in await _daemon(request).statuses()]
    return _json({
        "version": VERSION,
        "uptime": round(time.time() - _START_TIME, 1),
        "pairs": statuses,
    })


async def handle_config(request: web.Request) -> web.Response:
    return _json(dataclasses.asdict(_daemon(request).config))


async def handle_config_reload(request: web.Request) -> web.Response:
    import asyncio
    asyncio.get_running_loop().create_task(_daemon(request).reload_config())
    return _json({})


async def handle_config_save(request: web.Request) -> web.Response:
    try:
        await _daemon(request).save_config()
    except RuntimeError as e:
        return _error(str(e), status=409)
    except Exception as e:
        return _error(str(e), status=500)
    return _json({})


async def handle_config_apply(request: web.Request) -> web.Response:
    try:
        body = await request.json()
    except Exception:
        return _error("request body must be valid JSON", status=400)
    daemon = _daemon(request)
    try:
        await daemon.apply_config(body)
    except ConfigError as e:
        return _error(str(e), status=422)
    except Exception as e:
        return _error(str(e), status=500)
    return _json(dataclasses.asdict(daemon.config))


async def handle_pairs(request: web.Request) -> web.Response:
    daemon = _daemon(request)
    result = []
    for pair in daemon.config.pairs:
        entry: dict = dataclasses.asdict(pair)
        try:
            entry["status"] = dataclasses.asdict(await daemon.pair_status(pair.id))
        except Exception:
            entry["status"] = None
        result.append(entry)
    return _json(result)


async def _pair_action(request: web.Request, action: str) -> web.Response:
    pair_id = request.match_info["id"]
    try:
        await getattr(_daemon(request), action)(pair_id)
    except Exception as e:
        name = type(e).__name__
        if "NotFound" in name:
            return _error(f"pair not found: {pair_id}", status=404)
        return _error(str(e), status=500)
    return _json({})


async def handle_pair_sync(request: web.Request) -> web.Response:
    return await _pair_action(request, "trigger")


async def handle_pair_pause(request: web.Request) -> web.Response:
    return await _pair_action(request, "pause")


async def handle_pair_resume(request: web.Request) -> web.Response:
    return await _pair_action(request, "resume")


async def handle_peers(request: web.Request) -> web.Response:
    return _json(dataclasses.asdict(_daemon(request).config.peers))


async def handle_shutdown(request: web.Request) -> web.Response:
    _daemon(request).shutdown()
    return _json({})

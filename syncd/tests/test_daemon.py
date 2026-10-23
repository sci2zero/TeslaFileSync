import asyncio
import signal
import pytest

import syncd.sync.providers  # noqa: F401 — registers built-in providers
from syncd.config import AppConfig, ConfigError, DaemonConfig, PeersConfig
from syncd.daemon import Daemon


def make_config() -> AppConfig:
    return AppConfig(
        daemon=DaemonConfig(api_socket="/tmp/test.sock", log_level="info"),
        pairs=[],
        peers=PeersConfig(discovery="static", static=[]),
    )


async def test_run_starts_and_stops():
    daemon = Daemon(make_config())

    async def trigger_shutdown():
        await asyncio.sleep(0)
        daemon.shutdown()

    await asyncio.gather(daemon.run(), trigger_shutdown())


async def test_sigterm_sets_shutdown_event():
    daemon = Daemon(make_config())
    daemon._shutdown_event = asyncio.Event()
    daemon.shutdown()
    assert daemon._shutdown_event.is_set()


async def test_reload_config_no_path_logs_warning(caplog):
    import logging
    daemon = Daemon(make_config(), config_path="")
    with caplog.at_level(logging.WARNING, logger="syncd.daemon"):
        await daemon.reload_config()
    assert "No config path" in caplog.text


async def test_reload_config_bad_path_logs_error(caplog, tmp_path):
    import logging
    daemon = Daemon(make_config(), config_path=str(tmp_path / "missing.toml"))
    with caplog.at_level(logging.ERROR, logger="syncd.daemon"):
        await daemon.reload_config()
    assert "reload failed" in caplog.text


async def test_reload_config_success(tmp_path):
    config_file = tmp_path / "config.toml"
    config_file.write_text('[daemon]\nlog_level = "debug"\n')
    daemon = Daemon(make_config(), config_path=str(config_file))
    await daemon.reload_config()
    assert daemon._config.daemon.log_level == "debug"


async def test_startup_and_shutdown_stubs_do_not_raise():
    daemon = Daemon(make_config())
    await daemon._startup()
    await daemon._shutdown()


# The built-in p2p provider's schema requires "peers".
INVALID_P2P_PAIR = {"id": "p", "mode": "p2p", "local": "/tmp/x", "direction": "bidirectional"}


async def test_apply_config_invalid_provider_config_keeps_running_pairs():
    daemon = Daemon(make_config())
    running = daemon._manager
    with pytest.raises(ConfigError):
        await daemon.apply_config({"pairs": [INVALID_P2P_PAIR]})
    assert daemon._manager is running
    assert daemon._config.pairs == []


async def test_reload_config_invalid_provider_config_logs_error(caplog, tmp_path):
    import logging
    config_file = tmp_path / "config.toml"
    config_file.write_text('[[pairs]]\nid = "p"\nmode = "p2p"\nlocal = "/tmp/x"\ndirection = "bidirectional"\n')
    daemon = Daemon(make_config(), config_path=str(config_file))
    with caplog.at_level(logging.ERROR, logger="syncd.daemon"):
        await daemon.reload_config()
    assert "keeping previous config" in caplog.text
    assert daemon._config.pairs == []

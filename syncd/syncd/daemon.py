import asyncio
import dataclasses
import logging
from typing import Any

from syncd.config import AppConfig, ConfigError, load_config, parse_config_from_dict, save_config
from syncd.platform.signals import register_signal_handlers
from syncd.sync.base import ProviderStatus
from syncd.sync.manager import ProviderConfigError, SyncManager
from syncd.api.server import ApiServer

logger = logging.getLogger(__name__)


class Daemon:
    def __init__(self, config: AppConfig, config_path: str = "") -> None:
        self._config = config
        self._config_path = config_path
        self._shutdown_event: asyncio.Event | None = None
        self._api: ApiServer | None = None
        self._manager = SyncManager()

    async def run(self) -> None:
        self._shutdown_event = asyncio.Event()
        loop = asyncio.get_running_loop()
        register_signal_handlers(loop, self.shutdown, self.reload_config)

        logger.info("syncd starting")
        try:
            await self._startup()
            await self._shutdown_event.wait()
        finally:
            await self._shutdown()
            logger.info("syncd stopped")

    async def _startup(self) -> None:
        import syncd.sync.providers  # noqa: F401 — triggers provider auto-registration

        await self._manager.start_all(self._config.pairs)

        self._api = ApiServer(self._config.daemon.api_socket)
        await self._api.start(self)

    async def _shutdown(self) -> None:
        if self._api is not None:
            await self._api.stop()
        await self._manager.stop_all()

    @property
    def config(self) -> AppConfig:
        return self._config

    async def statuses(self) -> list[ProviderStatus]:
        return await self._manager.all_statuses()

    async def pair_status(self, pair_id: str) -> ProviderStatus:
        return await self._manager.status(pair_id)

    async def trigger(self, pair_id: str) -> None:
        await self._manager.trigger(pair_id)

    async def pause(self, pair_id: str) -> None:
        await self._manager.pause(pair_id)

    async def resume(self, pair_id: str) -> None:
        await self._manager.resume(pair_id)

    def shutdown(self) -> None:
        logger.info("Shutdown requested")
        if self._shutdown_event:
            self._shutdown_event.set()

    async def apply_config(self, raw: dict[str, Any]) -> None:
        await self._apply(parse_config_from_dict(raw))

    async def _apply(self, new_config: AppConfig) -> None:
        """Apply a new config in memory. api_socket is preserved — it cannot change at runtime."""
        # Preserve the running socket address; the UI cannot move the socket while connected.
        new_config = dataclasses.replace(
            new_config,
            daemon=dataclasses.replace(new_config.daemon, api_socket=self._config.daemon.api_socket),
        )
        old_log_level = self._config.daemon.log_level

        # Reject invalid provider config before stopping the running pairs.
        try:
            SyncManager.validate(new_config.pairs)
        except ProviderConfigError as e:
            raise ConfigError(str(e)) from e

        await self._manager.apply(new_config.pairs)

        self._config = new_config

        if new_config.daemon.log_level != old_log_level:
            logging.getLogger().setLevel(new_config.daemon.log_level.upper())
            logger.info("Log level changed to %s", new_config.daemon.log_level)

        logger.info("Config applied via API")

    async def save_config(self) -> None:
        """Serialize the current in-memory config back to the config file on disk."""
        if not self._config_path:
            raise RuntimeError("No config file path set — daemon was started without -c")
        save_config(self._config, self._config_path)
        logger.info("Config saved to %s", self._config_path)

    async def reload_config(self) -> None:
        if not self._config_path:
            logger.warning("No config path set, cannot reload")
            return
        try:
            await self._apply(load_config(self._config_path))
        except ConfigError as e:
            logger.error("Config reload failed, keeping previous config: %s", e)
            return
        logger.info("Config reloaded from %s", self._config_path)

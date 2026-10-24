import logging
from typing import Any, Type

import jsonschema

from syncd.config import PairConfig
from syncd.sync.base import SyncContext, SyncProvider, ProviderStatus
from syncd.sync.providers.subprocess import SubprocessProvider
from syncd.sync.registry import registry, UnknownProviderError

logger = logging.getLogger(__name__)


class PairNotFoundError(Exception):
    pass


class ProviderConfigError(Exception):
    pass


def _validate_schema(pair: PairConfig, provider_cls: Type[SyncProvider]) -> None:
    if hasattr(provider_cls, "SCHEMA"):
        try:
            jsonschema.validate(pair.provider, provider_cls.SCHEMA)
        except jsonschema.ValidationError as e:
            raise ProviderConfigError(
                f"Invalid provider config for pair {pair.id!r}: {e.message}"
            ) from e


class SyncManager:
    def __init__(self) -> None:
        self._providers: dict[str, SyncProvider] = {}
        self._configs: dict[str, PairConfig] = {}

    async def start_all(self, pairs: list[PairConfig]) -> None:
        for pair in pairs:
            await self._start_pair(pair)

    async def stop_all(self) -> None:
        for pair_id in list(self._providers):
            await self._stop_pair(pair_id)

    async def apply(self, pairs: list[PairConfig]) -> None:
        """Restart only the pairs whose config changed; unchanged pairs keep their state (e.g. paused)."""
        wanted = {pair.id: pair for pair in pairs}
        for pair_id in list(self._providers):
            if self._configs[pair_id] != wanted.get(pair_id):
                await self._stop_pair(pair_id)
        for pair in pairs:
            if pair.id not in self._providers:
                await self._start_pair(pair)

    async def _stop_pair(self, pair_id: str) -> None:
        provider = self._providers.pop(pair_id)
        del self._configs[pair_id]
        try:
            await provider.stop()
        except Exception:
            logger.exception("Error stopping provider for pair %s", pair_id)

    async def trigger(self, pair_id: str) -> None:
        await self._get(pair_id).trigger()

    async def pause(self, pair_id: str) -> None:
        await self._get(pair_id).pause()

    async def resume(self, pair_id: str) -> None:
        await self._get(pair_id).resume()

    async def status(self, pair_id: str) -> ProviderStatus:
        return await self._get(pair_id).status()

    async def all_statuses(self) -> list[ProviderStatus]:
        return [await p.status() for p in self._providers.values()]

    def _get(self, pair_id: str) -> SyncProvider:
        if pair_id not in self._providers:
            raise PairNotFoundError(pair_id)
        return self._providers[pair_id]

    @staticmethod
    def schemas() -> dict[str, dict[str, Any]]:
        return {name: registry.get(name).SCHEMA for name in registry.list_names()}

    @staticmethod
    def validate(pairs: list[PairConfig]) -> None:
        """Raise ProviderConfigError if any built-in provider config fails its schema."""
        for pair in pairs:
            try:
                provider_cls = registry.get(pair.mode)
            except UnknownProviderError:
                continue  # start_all() logs and skips these
            _validate_schema(pair, provider_cls)

    async def _start_pair(self, pair: PairConfig) -> None:
        provider_cls: Type[SyncProvider]
        try:
            provider_cls = registry.get(pair.mode)
        except UnknownProviderError:
            if not pair.provider.get("binary"):
                logger.error(
                    "Unknown provider mode %r for pair %r (no 'binary' key) — skipping",
                    pair.mode, pair.id,
                )
                return
            # Any external binary that speaks the subprocess IPC protocol can be used
            # without a dedicated Python wrapper — just set binary = "..." in config.
            provider_cls = SubprocessProvider

        _validate_schema(pair, provider_cls)

        context = SyncContext(
            pair_id=pair.id,
            local=pair.local,
            direction=pair.direction,
            interval=pair.interval,
            provider_config=pair.provider,
            exclude=list(pair.exclude),
        )
        provider = provider_cls()
        try:
            await provider.start(context)
        except ValueError as e:
            raise ProviderConfigError(str(e)) from e
        except Exception as e:
            logger.error("Failed to start provider for pair %r: %s", pair.id, e)
            return
        self._providers[pair.id] = provider
        self._configs[pair.id] = pair
        logger.info("Started provider %r for pair %r", pair.mode, pair.id)

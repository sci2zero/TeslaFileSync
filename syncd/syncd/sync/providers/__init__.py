from syncd.sync.registry import registry
from syncd.sync.providers.p2p import P2PProvider
from syncd.sync.providers.client_server import ClientServerProvider
from syncd.sync.providers.subprocess import SubprocessProvider

registry.register(P2PProvider)
registry.register(ClientServerProvider)
registry.register(SubprocessProvider)
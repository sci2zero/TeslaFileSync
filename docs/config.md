# Configuration Reference

Format: **TOML**. Default location: `~/.config/syncd/config.toml`.

Override with `syncd -c /path/to/config.toml`.

---

## `[daemon]`

```toml
[daemon]
api_socket = "/run/user/1000/syncd.sock"
log_level  = "info"
```

| Field | Default | Description |
|-------|---------|-------------|
| `api_socket` | Linux/macOS: `/run/user/<uid>/syncd.sock`<br>Windows: `127.0.0.1:24017` | Address of the management API used by `synctl` and `syncui`. A value starting with `/` is a Unix socket path, anything else is `host:port` over TCP. Cannot be changed while the daemon is running. |
| `log_level` | `info` | `debug`, `info`, `warning`, `error` or `critical` |

---

## `[[pairs]]`

Repeat this block for each directory you want to sync. Each pair runs its own provider instance.

```toml
[[pairs]]
id        = "work-docs"
mode      = "client-server"
local     = "~/Documents/Work"
interval  = 300
exclude   = ["*.log", "*.pdf", "build/*"]

[pairs.provider]
# provider-specific fields — see below
```

| Field | Required | Description |
|-------|----------|-------------|
| `id` | yes | Unique name of the pair, used in `synctl sync trigger <id>`. Two pairs with the same id are rejected. |
| `mode` | yes | Provider: `client-server`, `p2p` or `external` |
| `local` | yes | Local directory to sync. `~` is expanded. |
| `interval` | no | Seconds between sync cycles with other nodes. `0` (default) means the provider default of 30 s. Local changes are always watched; the interval only controls how often they are exchanged. |
| `exclude` | no | fnmatch patterns to skip, matched against the file name and the relative path. Added to the built-in excludes (`*.swp`, `*-swp`, `*.swpx`, `*.swn`, `.DS_Store`, `Thumbs.db`, `*.tmp`, `*.temp`, `*~`). |

`[pairs.provider]` is validated against the schema of the chosen provider before the pair is started.

---

## `[pairs.provider]` — client-server

```toml
[pairs.provider]
mode              = "server"
host              = "0.0.0.0"
port              = 5000
node_id           = "my-node"
conflict_strategy = "keep-both"
sync_deletes      = true
```

| Field | Required | Description |
|-------|----------|-------------|
| `mode` | yes | `server` listens for connections, `client` connects to the server |
| `port` | yes | TCP port |
| `host` | no | Server: interface to bind (default `0.0.0.0`). Client: server hostname (default `127.0.0.1`). |
| `node_id` | no | Name of this node. If omitted, a random id is generated on every start, so setting it is recommended. |
| `conflict_strategy` | no | `last-write-wins` (default) keeps the newer file; `keep-both` renames the local copy to `file.conflict.<node_id>` |
| `sync_deletes` | no | `true` (default). If `false`, deletions made on other nodes are not applied locally. |
| `verify_interval` | no | Seconds between integrity checks that re-hash files and compare them with the index. `0` (default) disables them. |
| `verify_sleep` | no | Seconds to wait between hashing two files during an integrity check. Default `0.1`. |

---

## `[pairs.provider]` — p2p

```toml
[pairs.provider]
peers             = ["192.168.1.10:5000", "192.168.1.11"]
port              = 5000
node_id           = "node-a"
conflict_strategy = "keep-both"
```

| Field | Required | Description |
|-------|----------|-------------|
| `peers` | yes | Other nodes as `host` or `host:port`. A bare host uses the pair-derived port. |
| `port` | no | Port this node listens on. If omitted, it is derived from the pair `id`, so nodes using the same `id` find each other without setting it. |
| `node_id` | no | Same as client-server |
| `conflict_strategy` | no | Same as client-server |
| `sync_deletes` | no | Same as client-server |
| `verify_interval` | no | Same as client-server |
| `verify_sleep` | no | Same as client-server |

Each node must list the others in its `peers`. For two nodes A and B: A lists B, B lists A.

---

## `[pairs.provider]` — external

```toml
[pairs.provider]
binary = "my-provider"
```

| Field | Required | Description |
|-------|----------|-------------|
| `binary` | yes | File name of the provider program in the providers directory. Paths are rejected. |

Any other fields are passed to the program unchanged. See [provider-interface.md](provider-interface.md) for where to install the program and the protocol it must speak.

---

## Full example

```toml
[daemon]
api_socket = "/run/user/1000/syncd.sock"
log_level  = "info"

# Client-server pair — this node is the client
[[pairs]]
id        = "work-docs"
mode      = "client-server"
local     = "~/Documents/Work"
interval  = 60

[pairs.provider]
mode              = "client"
host              = "myserver.example.com"
port              = 5000
node_id           = "laptop"
conflict_strategy = "keep-both"
sync_deletes      = false

# P2P pair — syncs photos with two other machines
[[pairs]]
id        = "photos"
mode      = "p2p"
local     = "~/Pictures"
interval  = 30

[pairs.provider]
peers    = ["192.168.1.10", "192.168.1.11"]
node_id  = "laptop"
```

---

## Reload without restart

```bash
synctl config reload
# or, on Linux and macOS
kill -HUP <syncd-pid>
```

An invalid config is rejected and the daemon keeps running with the previous one. Only pairs whose settings changed are restarted.

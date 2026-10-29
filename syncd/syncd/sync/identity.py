from __future__ import annotations

import os
import uuid

from syncd.platform.paths import data_dir

NODE_ID_FILE = "node_id"


def load_or_create_node_id() -> str:
    path = os.path.join(data_dir(), NODE_ID_FILE)
    try:
        with open(path) as f:
            node_id = f.read().strip()
        if node_id:
            return node_id
    except FileNotFoundError:
        pass
    node_id = uuid.uuid4().hex[:8]
    os.makedirs(data_dir(), exist_ok=True)
    with open(path, "w") as f:
        f.write(node_id + "\n")
    return node_id

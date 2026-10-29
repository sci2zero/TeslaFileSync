from __future__ import annotations

import os
import uuid

from syncd.sync.file_index import METADATA_DIR
from syncd.utils.fs import hide_path

NODE_ID_FILE = "node_id"


def load_or_create_node_id(local: str) -> str:
    meta_dir = os.path.join(local, METADATA_DIR)
    path = os.path.join(meta_dir, NODE_ID_FILE)
    try:
        with open(path) as f:
            node_id = f.read().strip()
        if node_id:
            return node_id
    except FileNotFoundError:
        pass
    node_id = uuid.uuid4().hex[:8]
    os.makedirs(meta_dir, exist_ok=True)
    hide_path(meta_dir)
    with open(path, "w") as f:
        f.write(node_id + "\n")
    return node_id

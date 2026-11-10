"""Health Auto Export (HAE) remote config helper.

Reads connection settings from environment variables, with an optional JSON
fallback file for local installs:

```
APPLE_HEALTH_REMOTE_BASE_URL=https://hae.example.com
APPLE_HEALTH_REMOTE_READ_TOKEN=sk-...
```

Optional JSON path via ``HEALTH_CORPUS_HAE_CONFIG`` (default
``~/.health-corpus/apple_health_remote.json``)::

    {"base_url": "...", "read_token": "..."}
"""
from __future__ import annotations

import json
import os
from pathlib import Path


def default_config_path() -> Path:
    override = os.environ.get("HEALTH_CORPUS_HAE_CONFIG", "").strip()
    if override:
        return Path(override).expanduser()
    return Path.home() / ".health-corpus" / "apple_health_remote.json"


def load_hae_config() -> dict[str, str]:
    """Return ``base_url`` and ``read_token`` for the HAE companion server."""
    base_url = os.environ.get("APPLE_HEALTH_REMOTE_BASE_URL", "").strip()
    token = os.environ.get("APPLE_HEALTH_REMOTE_READ_TOKEN", "").strip()
    if base_url and token:
        return {"base_url": base_url.rstrip("/"), "read_token": token}

    path = default_config_path()
    if not path.is_file():
        raise FileNotFoundError(
            "HAE config missing: set APPLE_HEALTH_REMOTE_BASE_URL and "
            f"APPLE_HEALTH_REMOTE_READ_TOKEN, or create {path}"
        )
    data = json.loads(path.read_text())
    base = str(data.get("base_url") or "").rstrip("/")
    read_token = str(data.get("read_token") or data.get("token") or "")
    if not base or not read_token:
        raise ValueError(f"HAE config at {path} needs base_url and read_token")
    return {"base_url": base, "read_token": read_token}

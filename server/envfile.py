"""Loads .env into os.environ. Import this before any other project module."""

import os

_path = os.path.join(os.path.dirname(__file__), ".env")
if os.path.exists(_path):
    with open(_path) as f:
        for line in f:
            line = line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            key, value = line.split("=", 1)
            os.environ.setdefault(key.strip(), value.strip())

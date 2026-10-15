"""Shared helpers: config loading, logging, and ID hashing."""
import hashlib
import logging
import os
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[1]

logging.basicConfig(level=logging.INFO, format="%(asctime)s | %(levelname)s | %(message)s")
log = logging.getLogger("pipeline")


def load_config(path=None):
    with open(path or ROOT / "config.yaml") as f:
        cfg = yaml.safe_load(f)
    for key in ("raw_dir", "store_dir", "output_dir"):
        p = ROOT / cfg["data"][key]
        p.mkdir(parents=True, exist_ok=True)
        cfg["data"][key] = p
    return cfg


_SALT = None


def _salt():
    global _SALT
    if _SALT is None:
        _SALT = os.environ.get("PRIVATE_SALT")
        if not _SALT:
            log.warning("PRIVATE_SALT not set, using a dev salt. Set it as a GitHub secret before going public.")
            _SALT = "dev-salt-change-me"
    return _SALT


def hash_id(value):
    """One-way hash so nothing in the repo or dashboards names a real doctor."""
    if value is None:
        return None
    s = str(value).strip().upper()
    if not s or s in {"NAN", "NONE"}:
        return None
    return hashlib.sha256((_salt() + "|" + s).encode()).hexdigest()[:16]


def name_key(last, first, state):
    """Backup match key for exclusions that have no NPI."""
    parts = [str(x).strip().upper() for x in (last, first, state)]
    if any(p in {"", "NAN", "NONE"} for p in parts):
        return None
    return "|".join(parts)

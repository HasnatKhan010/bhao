"""Registry store — versioned artefacts + the champion pointer.

The pointer is plain JSON so the API never needs MLflow (03-CONTRACTS.md)."""

from __future__ import annotations

import hashlib
import json
import shutil
from pathlib import Path

from models.global_gbm import GlobalGBM

DEFAULT_DIR = Path("data/registry")


def artefact_dir(registry_dir: Path, version: str) -> Path:
    return registry_dir / "artefacts" / version


def store_model(gbm: GlobalGBM, version: str, registry_dir: Path = DEFAULT_DIR) -> str:
    """Persist the model and return its artefact sha256."""
    path = artefact_dir(registry_dir, version)
    if path.exists():
        shutil.rmtree(path)
    gbm.save(path)
    hasher = hashlib.sha256()
    for f in sorted(path.rglob("*")):
        if f.is_file():
            hasher.update(f.read_bytes())
    return hasher.hexdigest()


def load_model(version: str, registry_dir: Path = DEFAULT_DIR) -> GlobalGBM:
    return GlobalGBM.load(artefact_dir(registry_dir, version))

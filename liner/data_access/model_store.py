"""Layer 4, Model store: versioned model files on local disk (Simplified: version is in the file name)."""
from __future__ import annotations

import json
import os
import re
from pathlib import Path

_NAME = re.compile(r"^[a-z0-9_-]+$")


class LocalModelStore:
    def __init__(self, directory: Path):
        self._dir = Path(directory)
        self._dir.mkdir(parents=True, exist_ok=True)

    def save(self, name: str, payload: dict) -> int:
        self._check(name)
        version = max((v for v, _ in self._versions(name)), default=0) + 1
        path = self._dir / f"{name}-v{version:03d}.json"
        tmp = path.with_suffix(".tmp")
        tmp.write_text(json.dumps(payload), encoding="utf-8")
        os.replace(tmp, path)
        return version

    def load_latest(self, name: str) -> tuple[int, dict] | None:
        self._check(name)
        versions = self._versions(name)
        if not versions:
            return None
        version, path = max(versions)
        return version, json.loads(path.read_text(encoding="utf-8"))

    def _versions(self, name: str) -> list[tuple[int, Path]]:
        pat = re.compile(rf"^{re.escape(name)}-v(\d+)\.json$")
        out = []
        for p in self._dir.iterdir():
            m = pat.match(p.name)
            if m:
                out.append((int(m.group(1)), p))
        return out

    @staticmethod
    def _check(name: str) -> None:
        if not _NAME.match(name):
            raise ValueError("invalid model name")

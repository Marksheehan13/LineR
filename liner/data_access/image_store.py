"""Layer 4, Image store: uploaded page images on local disk (Simplified; the target uses managed
storage with a retention limit, risk R9)."""
from __future__ import annotations

import os
import re
import uuid
from pathlib import Path

_REF = re.compile(r"^[0-9a-f]{32}\.(png|jpg|jpeg)$")


class LocalImageStore:
    def __init__(self, directory: Path):
        self._dir = Path(directory)
        self._dir.mkdir(parents=True, exist_ok=True)

    def save(self, user_id: str, data: bytes, ext: str) -> str:
        ext = ext.lower().lstrip(".")
        if ext not in ("png", "jpg", "jpeg"):
            raise ValueError(f"unsupported image type: {ext!r}")
        ref = f"{uuid.uuid4().hex}.{ext}"
        tmp = self._dir / f".{ref}.tmp"
        tmp.write_bytes(data)
        os.replace(tmp, self._dir / ref)  # atomic: a half-written file is never visible
        return ref

    def load(self, ref: str) -> bytes:
        return self._path(ref).read_bytes()

    def delete(self, ref: str) -> None:
        self._path(ref).unlink(missing_ok=True)

    def _path(self, ref: str) -> Path:
        # refs come from our own database, but the check keeps '../' out whatever the source
        if not _REF.match(ref):
            raise ValueError("invalid image reference")
        return self._dir / ref

"""Layer 6, Accounting package export: Deferred. The interface exists; nothing is implemented,
because it needs a partner's system and an agreement (Deliverable 1, section 1.4)."""
from __future__ import annotations

from typing import Sequence

from ..models import BandRow


class DeferredAccountingPackage:
    def export_rows(self, rows: Sequence[BandRow]) -> None:
        raise NotImplementedError("Accounting package export is deferred (not in the prototype).")

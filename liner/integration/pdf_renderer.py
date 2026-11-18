"""Layer 6, Document renderer: turns an upload into one page image (added in D2, deviation log D-03).

A PDF's first page is rasterised with poppler (via pdf2image). Images are re-encoded, which drops
EXIF data and anything appended to the file, and are capped in size."""
from __future__ import annotations

import io

from PIL import Image, ImageOps, UnidentifiedImageError

from ..models import OcrError, Upload

_MAX_SIDE = 3000


class PillowPopplerRenderer:
    def __init__(self, dpi: int = 200, timeout_seconds: int = 30, max_pixels: int = 25_000_000):
        self._dpi = dpi
        self._timeout = timeout_seconds
        self._max_pixels = max_pixels

    def to_image(self, upload: Upload) -> bytes:
        Image.MAX_IMAGE_PIXELS = self._max_pixels
        try:
            if upload.kind == "pdf":
                from pdf2image import convert_from_bytes
                pages = convert_from_bytes(upload.data, dpi=self._dpi, first_page=1, last_page=1,
                                           fmt="png", timeout=self._timeout)
                if not pages:
                    raise OcrError("The PDF has no pages.")
                im = pages[0]
            else:
                with Image.open(io.BytesIO(upload.data)) as src:
                    im = ImageOps.exif_transpose(src)
                    im.load()
            im = im.convert("RGB")
            im.thumbnail((_MAX_SIDE, _MAX_SIDE))
            out = io.BytesIO()
            im.save(out, format="PNG")
            return out.getvalue()
        except OcrError:
            raise
        except (UnidentifiedImageError, OSError, Image.DecompressionBombError, ValueError) as exc:
            raise OcrError("The file could not be opened as a page image.") from exc
        except Exception as exc:  # pdf2image raises several poppler-specific errors
            raise OcrError("The PDF could not be rendered.") from exc

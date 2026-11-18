"""Layer 6, OCR service (the essential AI component): Tesseract behind ``read_text(image)``.

Tesseract is an open-source, pre-trained OCR engine. It runs in-process here; a managed
document-AI service could replace this class without changing any caller.
Everything that can go wrong (undecodable file, engine missing, timeout) is turned into an
``OcrError`` so the application never crashes on a bad read (risk R4)."""
from __future__ import annotations

import io

from PIL import Image, ImageOps, UnidentifiedImageError

from ..models import OcrError, OcrResult, Word

_MIN_WIDTH = 1600   # small images are scaled up first; Tesseract reads small text poorly


class TesseractOcrEngine:
    def __init__(self, timeout_seconds: int = 30, psm: int = 6, max_pixels: int = 25_000_000):
        self._timeout = timeout_seconds
        self._psm = psm
        self._max_pixels = max_pixels

    def read_text(self, image: bytes) -> OcrResult:
        try:
            import pytesseract
        except ImportError as exc:  # pragma: no cover - depends on the machine
            raise OcrError("The OCR library (pytesseract) is not installed.") from exc

        img = self._prepare(image)
        try:
            data = pytesseract.image_to_data(
                img, lang="eng", config=f"--psm {self._psm}", output_type=pytesseract.Output.DICT,
                timeout=self._timeout)
            version = str(pytesseract.get_tesseract_version())
        except pytesseract.TesseractNotFoundError as exc:
            raise OcrError("The OCR engine (Tesseract) is not installed.") from exc
        except RuntimeError as exc:  # pytesseract raises RuntimeError("Tesseract process timeout")
            raise OcrError("Reading the document took too long.") from exc
        except pytesseract.TesseractError as exc:
            raise OcrError("The OCR engine could not read this file.") from exc

        words: list[Word] = []
        for i, text in enumerate(data["text"]):
            text = (text or "").strip()
            try:
                conf = float(data["conf"][i])
            except (TypeError, ValueError):
                continue
            if not text or conf < 0:
                continue
            words.append(Word(text, float(data["left"][i]), float(data["top"][i]),
                              float(data["width"][i]), float(data["height"][i]), conf))
        return OcrResult(words=words, width=img.width, height=img.height,
                         engine="tesseract", engine_version=version)

    def _prepare(self, image: bytes) -> Image.Image:
        try:
            Image.MAX_IMAGE_PIXELS = self._max_pixels
            with Image.open(io.BytesIO(image)) as im:
                im = ImageOps.exif_transpose(im)
                im = ImageOps.autocontrast(im.convert("L"))
                if im.width < _MIN_WIDTH:
                    scale = _MIN_WIDTH / im.width
                    im = im.resize((_MIN_WIDTH, int(im.height * scale)), Image.LANCZOS)
                return im.copy()
        except (UnidentifiedImageError, OSError, Image.DecompressionBombError, ValueError) as exc:
            raise OcrError("The file is not a readable image.") from exc

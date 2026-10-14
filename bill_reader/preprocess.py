"""Turn a stored original (PDF or image) into normalised page images for extraction."""

import io
from dataclasses import dataclass, field
from pathlib import Path

import pypdfium2 as pdfium
from PIL import Image, ImageOps, ImageSequence
from pillow_heif import register_heif_opener

from bill_reader.config import Settings

register_heif_opener()


@dataclass
class PreparedDocument:
    pages: list[Image.Image]
    page_jpegs: list[bytes]
    text_layer: str = ""
    page_paths: list[Path] = field(default_factory=list)


def is_pdf(path: Path) -> bool:
    with open(path, "rb") as f:
        return f.read(5) == b"%PDF-"


def page_count(path: Path) -> int:
    """Number of pages; raises if the file cannot be decoded."""
    if is_pdf(path):
        pdf = pdfium.PdfDocument(str(path))
        try:
            return len(pdf)
        finally:
            pdf.close()
    with Image.open(path) as im:
        return getattr(im, "n_frames", 1)


def page_image_path(settings: Settings, sha: str, n: int) -> Path:
    """Cached JPEG for page `n` (0-based) of the document with hash `sha`."""
    return settings.documents_dir / sha / f"page-{n}.jpg"


def normalise(img: Image.Image, max_px: int) -> Image.Image:
    """Downscale so the long edge is at most `max_px` (never upscales)."""
    long_edge = max(img.size)
    if long_edge <= max_px:
        return img
    scale = max_px / long_edge
    size = (max(1, round(img.width * scale)), max(1, round(img.height * scale)))
    return img.resize(size, Image.Resampling.LANCZOS)


def _to_rgb(img: Image.Image) -> Image.Image:
    if img.mode == "RGB":
        return img
    if img.mode in ("RGBA", "LA", "P"):
        img = img.convert("RGBA")
        bg = Image.new("RGB", img.size, (255, 255, 255))
        bg.paste(img, mask=img.getchannel("A"))
        return bg
    return img.convert("RGB")


def render_pages(path: Path, settings: Settings) -> list[Image.Image]:
    """Render every page as an upright RGB image, long edge <= settings.max_image_px."""
    if is_pdf(path):
        pdf = pdfium.PdfDocument(str(path))
        try:
            scale = settings.pdf_dpi / 72
            pages = [_to_rgb(pdf[i].render(scale=scale).to_pil()) for i in range(len(pdf))]
        finally:
            pdf.close()
    else:
        with Image.open(path) as im:
            pages = [
                _to_rgb(ImageOps.exif_transpose(frame))
                for frame in ImageSequence.Iterator(im)
            ]
    return [normalise(p, settings.max_image_px) for p in pages]


def to_jpeg_bytes(img: Image.Image, quality: int = 90) -> bytes:
    buf = io.BytesIO()
    _to_rgb(img).save(buf, "JPEG", quality=quality)
    return buf.getvalue()


def pdf_text(path: Path) -> str:
    """Embedded text layer of a PDF; "" for images and scanned PDFs."""
    if not is_pdf(path):
        return ""
    pdf = pdfium.PdfDocument(str(path))
    try:
        texts = []
        for i in range(len(pdf)):
            tp = pdf[i].get_textpage()
            texts.append(tp.get_text_range())
            tp.close()
    finally:
        pdf.close()
    return "\n\n".join(t.strip() for t in texts).strip()


def prepare(path: Path, settings: Settings, sha: str | None = None) -> PreparedDocument:
    """Render pages and JPEG-encode them. If `sha` is given, cache JPEGs for the UI."""
    pages = render_pages(path, settings)
    jpegs = [to_jpeg_bytes(p) for p in pages]
    paths: list[Path] = []
    if sha:
        for n, data in enumerate(jpegs):
            p = page_image_path(settings, sha, n)
            p.parent.mkdir(parents=True, exist_ok=True)
            p.write_bytes(data)
            paths.append(p)
    return PreparedDocument(pages=pages, page_jpegs=jpegs, text_layer=pdf_text(path), page_paths=paths)

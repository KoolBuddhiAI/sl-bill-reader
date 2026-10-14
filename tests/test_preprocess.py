from pathlib import Path

import pytest
from PIL import Image

from bill_reader.preprocess import (
    normalise,
    page_image_path,
    pdf_text,
    prepare,
    render_pages,
    to_jpeg_bytes,
)


@pytest.fixture
def png_sample(samples_dir: Path) -> Path:
    return next((samples_dir / "bills").glob("02-*.png"))


def test_render_png_resized_and_rgb(settings, png_sample):
    pages = render_pages(png_sample, settings)
    assert len(pages) == 1
    assert pages[0].mode == "RGB"
    assert max(pages[0].size) <= settings.max_image_px


def test_normalise_downscales_long_edge_only():
    img = Image.new("RGB", (4000, 1000))
    out = normalise(img, 2000)
    assert out.size == (2000, 500)
    small = Image.new("RGB", (100, 50))
    assert normalise(small, 2000).size == (100, 50)


def test_exif_orientation_applied(settings, tmp_path):
    img = Image.new("RGB", (300, 100), "white")
    exif = img.getexif()
    exif[0x0112] = 6  # rotate 90 CW
    path = tmp_path / "rotated.jpg"
    img.save(path, "JPEG", exif=exif)
    (page,) = render_pages(path, settings)
    assert page.size == (100, 300)


def test_pdf_rendered_at_dpi(settings, tmp_path, png_sample):
    pdf = tmp_path / "bill.pdf"
    with Image.open(png_sample) as im:
        im.convert("RGB").save(pdf, "PDF", resolution=100)
    settings.max_image_px = 10_000
    pages = render_pages(pdf, settings)
    assert len(pages) == 1
    with Image.open(png_sample) as im:
        expected_w = im.width * settings.pdf_dpi / 100
    assert abs(pages[0].width - expected_w) <= 2
    assert pdf_text(pdf) == ""  # image-only PDF has no text layer
    assert pdf_text(png_sample) == ""


def test_multiframe_tiff_pages(settings, tmp_path):
    path = tmp_path / "two.tiff"
    a, b = Image.new("RGB", (50, 50), "red"), Image.new("RGB", (60, 40), "blue")
    a.save(path, save_all=True, append_images=[b])
    pages = render_pages(path, settings)
    assert [p.size for p in pages] == [(50, 50), (60, 40)]


def test_rgba_converted(settings, tmp_path):
    path = tmp_path / "alpha.png"
    Image.new("RGBA", (20, 20), (255, 0, 0, 0)).save(path)
    (page,) = render_pages(path, settings)
    assert page.mode == "RGB"
    assert page.getpixel((0, 0)) == (255, 255, 255)


def test_prepare_caches_page_jpegs(settings, png_sample):
    doc = prepare(png_sample, settings, sha="abc")
    assert len(doc.pages) == len(doc.page_jpegs) == 1
    assert doc.page_jpegs[0][:2] == b"\xff\xd8"
    cached = page_image_path(settings, "abc", 0)
    assert cached.read_bytes() == doc.page_jpegs[0]
    assert doc.text_layer == ""
    assert to_jpeg_bytes(doc.pages[0])[:2] == b"\xff\xd8"

"""Browser smoke test of the review UI (upload → review → approve → export). Skipped without Playwright."""

import glob
import os
import socket
import threading
import time
from pathlib import Path

import pytest

playwright_api = pytest.importorskip("playwright.sync_api", reason="playwright not installed")
uvicorn = pytest.importorskip("uvicorn")

from bill_reader.app import create_app  # noqa: E402
from tests.test_api import _keys, make_client  # noqa: E402,F401  (_keys is an autouse fixture)

SCREENSHOT = os.environ.get("BILL_READER_UI_SCREENSHOT")  # optional path for a review-page screenshot


def _free_port() -> int:
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


def _launch(p):
    try:
        return p.chromium.launch()
    except Exception:
        # Pre-installed browsers may be a different build than the pip package expects.
        root = os.environ.get("PLAYWRIGHT_BROWSERS_PATH", "/opt/pw-browsers")
        for exe in sorted(glob.glob(f"{root}/chromium-*/chrome-linux*/chrome"), reverse=True):
            return p.chromium.launch(executable_path=exe)
        pytest.skip("no Chromium available for Playwright")


@pytest.fixture
def server(settings):
    app = create_app(settings, worker_threads=0, client_factory=make_client(), ocr=None)
    port = _free_port()
    srv = uvicorn.Server(uvicorn.Config(app, host="127.0.0.1", port=port, log_level="warning"))
    thread = threading.Thread(target=srv.run, daemon=True)
    thread.start()
    deadline = time.time() + 10
    while not srv.started and time.time() < deadline:
        time.sleep(0.05)
    assert srv.started, "uvicorn did not start"
    yield f"http://127.0.0.1:{port}"
    srv.should_exit = True
    thread.join(5)


def test_upload_review_approve_export(server, samples_dir, tmp_path):
    sample = samples_dir / "bills" / "02-vat-company-en-printed-tax-invoice.png"
    with playwright_api.sync_playwright() as p:
        browser = _launch(p)
        page = browser.new_page(viewport={"width": 1440, "height": 900}, accept_downloads=True)
        # keep the test offline: web fonts fall back to local fonts
        page.route("https://fonts.googleapis.com/**", lambda route: route.abort())
        page.route("https://fonts.gstatic.com/**", lambda route: route.abort())
        expect = playwright_api.expect

        page.goto(server + "/")
        page.set_input_files("#file-input", str(sample))
        ok = page.locator("#upload-results li.ok")
        expect(ok).to_contain_text("uploaded as")
        expect(page.locator("#bills-body tr[data-id]")).to_have_count(1)
        expect(page.locator("#bills-body")).to_contain_text("Vat Company")

        # duplicate is reported
        page.set_input_files("#file-input", str(sample))
        expect(page.locator("#upload-results li.dup")).to_contain_text("duplicate")

        page.locator("#bills-body tr[data-id] a").first.click()
        page.wait_for_url("**/bills/*")
        total = page.locator("#f-total")
        expect(total).to_have_value("2719900.00")
        expect(page.locator(".fld[data-name=total]")).to_have_class("field fld level-high has-box")
        expect(page.locator("#extraction-info")).to_contain_text("Extracted by")
        page.wait_for_function("document.getElementById('page-img').naturalWidth > 0")

        highlight = page.locator("#highlight")
        expect(highlight).to_have_attribute("visibility", "hidden")
        page.locator(".fld[data-name=total]").hover()
        expect(highlight).to_have_attribute("visibility", "visible")
        assert float(highlight.get_attribute("x")) == pytest.approx(0.75)
        box = highlight.bounding_box()
        assert box and box["width"] > 10 and box["height"] > 2
        if SCREENSHOT:
            page.screenshot(path=SCREENSHOT)

        page.click("#approve-btn")
        expect(page.locator("#status-badge")).to_have_text("approved")
        expect(page.locator("#problems-banner")).to_be_hidden()

        page.click("nav >> text=Export")
        expect(page.locator("#approved-count")).to_have_text("1")
        with page.expect_download() as dl:
            page.click("#export-btn")
        path = tmp_path / dl.value.suggested_filename
        dl.value.save_as(path)
        assert path.suffix == ".zip" and Path(path).stat().st_size > 0
        expect(page.locator("#batches-body tr")).to_have_count(1)
        expect(page.locator("#approved-count")).to_have_text("0")
        browser.close()

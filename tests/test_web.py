from fastapi.testclient import TestClient

from bill_reader.app import create_app
from tests.test_api import _keys, make_client, upload  # noqa: F401  (_keys is an autouse fixture)


def _client(settings):
    return TestClient(create_app(settings, worker_threads=0, client_factory=make_client(), ocr=None))


def test_pages_render(settings, samples_dir):
    with _client(settings) as c:
        bill_id = upload(c, samples_dir)["bill_id"]
        pages = {
            "/": ['id="dropzone"', 'id="bills-table"', 'id="status-filter"', "needs_review"],
            f"/bills/{bill_id}": ['data-bill-id="%d"' % bill_id, 'id="overlay"', 'id="approve-btn"',
                                  'id="account-input"', 'id="reextract-profile"', "review.js"],
            "/export": ['id="export-btn"', 'id="batches-body"'],
            "/settings": ['id="extraction-select"', 'id="accounts-form"', 'id="ocr-status"'],
        }
        for path, markers in pages.items():
            resp = c.get(path)
            assert resp.status_code == 200, path
            assert "Noto+Sans+Sinhala" in resp.text and 'href="/export"' in resp.text
            for m in markers:
                assert m in resp.text, (path, m)


def test_review_page_404_and_static(settings):
    with _client(settings) as c:
        assert c.get("/bills/999").status_code == 404
        for name in ("app.css", "app.js", "review.js"):
            assert c.get(f"/static/{name}").status_code == 200

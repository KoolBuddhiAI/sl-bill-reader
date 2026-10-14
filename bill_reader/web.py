"""HTML pages. Each page is a Jinja2 shell; the data comes from /api via fetch (static/*.js)."""

from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates
from sqlmodel import Session

from bill_reader.api import get_session
from bill_reader.models import Bill, BillStatus

HERE = Path(__file__).parent
STATIC_DIR = HERE / "static"
templates = Jinja2Templates(directory=HERE / "templates")

router = APIRouter(include_in_schema=False)


def _page(request: Request, name: str, active: str, **context) -> HTMLResponse:
    return templates.TemplateResponse(request, name, {"active": active, **context})


@router.get("/", response_class=HTMLResponse)
def bills_page(request: Request):
    return _page(request, "bills_list.html", "bills", statuses=[s.value for s in BillStatus])


@router.get("/bills/{bill_id}", response_class=HTMLResponse)
def review_page(request: Request, bill_id: int, session: Session = Depends(get_session)):
    bill = session.get(Bill, bill_id)
    if bill is None:
        raise HTTPException(404, "Bill not found")
    return _page(request, "bill_review.html", "bills", bill=bill)


@router.get("/export", response_class=HTMLResponse)
def export_page(request: Request):
    return _page(request, "export.html", "export")


@router.get("/settings", response_class=HTMLResponse)
def settings_page(request: Request):
    return _page(request, "settings.html", "settings")

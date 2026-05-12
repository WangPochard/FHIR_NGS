from fastapi import APIRouter, Depends, Form, HTTPException
from fastapi.requests import Request
from fastapi.responses import RedirectResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_session
from app.models import Code, ValueSet

router = APIRouter()
templates = Jinja2Templates(directory="app/templates")


@router.get("/")
async def index(request: Request, session: AsyncSession = Depends(get_session)):
    valuesets = (await session.scalars(select(ValueSet).order_by(ValueSet.title))).all()
    return templates.TemplateResponse("loinc/index.html", {"request": request, "valuesets": valuesets})


@router.get("/{resource_id}")
async def detail(resource_id: str, request: Request, session: AsyncSession = Depends(get_session)):
    vs = await session.scalar(select(ValueSet).where(ValueSet.resource_id == resource_id))
    if not vs:
        raise HTTPException(status_code=404)
    return templates.TemplateResponse("loinc/detail.html", {"request": request, "vs": vs})


@router.post("/{resource_id}/codes/{code_id}")
async def update_display(
    resource_id: str,
    code_id: int,
    display: str = Form(""),
    session: AsyncSession = Depends(get_session),
):
    code = await session.get(Code, code_id)
    if not code:
        raise HTTPException(status_code=404)
    code.display = display.strip() or None
    await session.commit()
    return RedirectResponse(url=f"/loinc/{resource_id}", status_code=303)

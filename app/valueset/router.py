from fastapi import APIRouter, Depends, HTTPException
from fastapi.requests import Request
from fastapi.templating import Jinja2Templates
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_session
from app.valueset.models import ValueSet

router = APIRouter()
templates = Jinja2Templates(directory="app/templates")


@router.get("/")
async def index(request: Request, session: AsyncSession = Depends(get_session)):
    valuesets = (await session.scalars(select(ValueSet).order_by(ValueSet.title))).all()
    return templates.TemplateResponse("valueset/index.html", {"request": request, "valuesets": valuesets})


@router.get("/{resource_id}")
async def detail(resource_id: str, request: Request, session: AsyncSession = Depends(get_session)):
    vs = await session.scalar(select(ValueSet).where(ValueSet.resource_id == resource_id))
    if not vs:
        raise HTTPException(status_code=404)
    return templates.TemplateResponse("valueset/detail.html", {"request": request, "vs": vs})



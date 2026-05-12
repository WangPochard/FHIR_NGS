import json
from pathlib import Path

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import Code, ValueSet

VALUESET_DIR = Path(__file__).parent.parent / "template" / "valuesets"


def _parse(path: Path) -> tuple[dict, list[dict]]:
    data = json.loads(path.read_text(encoding="utf-8"))
    resource_type = data["resourceType"]

    info = {
        "resource_id": data["id"],
        "name": data["name"],
        "title": data["title"],
        "url": data["url"],
        "resource_type": resource_type,
        "description": data.get("description"),
        "code_system": None,
    }

    codes: list[dict] = []
    if resource_type == "ValueSet":
        for include in data.get("compose", {}).get("include", []):
            if not info["code_system"]:
                info["code_system"] = include.get("system")
            for concept in include.get("concept", []):
                codes.append({"code": concept["code"], "display": concept.get("display")})
    elif resource_type == "CodeSystem":
        info["code_system"] = data.get("url")
        for concept in data.get("concept", []):
            codes.append({"code": concept["code"], "display": concept.get("display")})

    return info, codes


async def seed(session: AsyncSession) -> None:
    for path in sorted(VALUESET_DIR.glob("*.json")):
        info, codes = _parse(path)
        exists = await session.scalar(
            select(ValueSet).where(ValueSet.resource_id == info["resource_id"])
        )
        if exists:
            continue
        vs = ValueSet(**info)
        session.add(vs)
        await session.flush()
        for c in codes:
            session.add(Code(valueset_id=vs.id, **c))

    await session.commit()

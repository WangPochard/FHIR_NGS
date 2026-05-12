import json
import tempfile
from pathlib import Path

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile
from fastapi.requests import Request
from fastapi.responses import JSONResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.converter.vcf_to_fhir import (
    CLINVAR_SIG,
    VcfRecord,
    VcfToFhirConverter,
    build_single_variant_resources,
    parse_vcf_records,
)
from app.database import get_session
from app.ui.models import ConversionJob, VariantDraft
from app.valueset.models import ValueSet

router = APIRouter()
templates = Jinja2Templates(directory="app/templates")


@router.get("/")
async def upload_page(request: Request, session: AsyncSession = Depends(get_session)):
    vs = await session.scalar(select(ValueSet).where(ValueSet.resource_id == "specime-type"))
    return templates.TemplateResponse("ui/upload.html", {
        "request": request,
        "specimen_types": vs.codes if vs else [],
    })


@router.post("/upload")
async def upload(
    file: UploadFile = File(...),
    patient_id: str = Form(...),
    specimen_id: str = Form(...),
    specimen_type: str = Form(""),   # "code|display"
    session: AsyncSession = Depends(get_session),
):
    with tempfile.NamedTemporaryFile(suffix=".vcf", delete=False) as tmp:
        tmp.write(await file.read())
        tmp_path = tmp.name

    try:
        records = parse_vcf_records(tmp_path)
    finally:
        Path(tmp_path).unlink(missing_ok=True)

    if not records:
        raise HTTPException(status_code=400, detail="VCF 檔案中沒有找到變異資料")

    sp_code, sp_display = (specimen_type.split("|", 1) + [""])[:2] if specimen_type else ("", "")

    job = ConversionJob(
        filename=file.filename or "upload.vcf",
        patient_id=patient_id,
        specimen_id=specimen_id,
        specimen_type_code=sp_code or None,
        specimen_type_display=sp_display or None,
    )
    session.add(job)
    await session.flush()

    for i, rec in enumerate(records):
        session.add(VariantDraft(
            job_id=job.id,
            index=i,
            chrom=rec.chrom,
            pos=rec.pos_0based + 1,
            ref=rec.ref,
            alt=rec.alt,
            qual=rec.qual,
            rs_id=rec.rs_id or None,
            ref_genome=rec.ref_genome,
            gene=rec.gene or None,
            hgvs_c=rec.hgvs_c or None,
            hgvs_p=rec.hgvs_p or None,
            consequence=rec.consequence or None,
            af=rec.af,
            dp=rec.dp,
            gt=rec.gt or None,
        ))

    await session.commit()
    return RedirectResponse(url=f"/ui/jobs/{job.id}/variants/0", status_code=303)


@router.get("/jobs/{job_id}/variants/{idx}")
async def review_variant(
    job_id: int,
    idx: int,
    request: Request,
    session: AsyncSession = Depends(get_session),
):
    job = await session.get(ConversionJob, job_id)
    if not job:
        raise HTTPException(status_code=404)

    draft = await session.scalar(
        select(VariantDraft).where(VariantDraft.job_id == job_id, VariantDraft.index == idx)
    )
    if not draft:
        raise HTTPException(status_code=404)

    vs = await session.scalar(select(ValueSet).where(ValueSet.resource_id == "dna-change-type"))
    total = await session.scalar(
        select(func.count()).select_from(VariantDraft).where(VariantDraft.job_id == job_id)
    )

    return templates.TemplateResponse("ui/review.html", {
        "request": request,
        "job": job,
        "draft": draft,
        "dna_change_types": vs.codes if vs else [],
        "clinical_sigs": list(CLINVAR_SIG.items()),
        "idx": idx,
        "total": total,
        "is_last": idx == total - 1,
    })


@router.post("/jobs/{job_id}/variants/{idx}")
async def save_variant(
    job_id: int,
    idx: int,
    dna_change_type: str = Form(""),   # "code|display"
    clinical_sig_key: str = Form(""),
    session: AsyncSession = Depends(get_session),
):
    job = await session.get(ConversionJob, job_id)
    draft = await session.scalar(
        select(VariantDraft).where(VariantDraft.job_id == job_id, VariantDraft.index == idx)
    )
    if not job or not draft:
        raise HTTPException(status_code=404)

    if dna_change_type:
        parts = dna_change_type.split("|", 1)
        draft.dna_change_type_code = parts[0] or None
        draft.dna_change_type_display = parts[1] if len(parts) > 1 else None

    draft.clinical_sig_key = clinical_sig_key or None
    draft.status = "done"
    await session.commit()

    total = await session.scalar(
        select(func.count()).select_from(VariantDraft).where(VariantDraft.job_id == job_id)
    )
    next_idx = idx + 1
    if next_idx < total:
        return RedirectResponse(url=f"/ui/jobs/{job_id}/variants/{next_idx}", status_code=303)
    return RedirectResponse(url=f"/ui/jobs/{job_id}/result", status_code=303)


@router.get("/jobs/{job_id}/result")
async def result(job_id: int, request: Request, session: AsyncSession = Depends(get_session)):
    job = await session.get(ConversionJob, job_id)
    if not job:
        raise HTTPException(status_code=404)

    bundle = _build_bundle(job)
    return templates.TemplateResponse("ui/result.html", {
        "request": request,
        "job": job,
        "bundle_json": json.dumps(bundle, ensure_ascii=False, indent=2),
    })


@router.get("/jobs/{job_id}/result/download")
async def download(job_id: int, session: AsyncSession = Depends(get_session)):
    job = await session.get(ConversionJob, job_id)
    if not job:
        raise HTTPException(status_code=404)

    bundle = _build_bundle(job)
    return JSONResponse(
        content=bundle,
        headers={"Content-Disposition": f"attachment; filename=bundle_{job_id}.json"},
    )


def _build_bundle(job: ConversionJob) -> dict:
    all_resources: list[dict] = []
    for draft in job.variants:
        record = VcfRecord(
            chrom=draft.chrom,
            pos_0based=draft.pos - 1,
            ref=draft.ref,
            alt=draft.alt,
            qual=draft.qual,
            filter_status="PASS",
            rs_id=draft.rs_id or "",
            ref_genome=draft.ref_genome,
            gene=draft.gene or "",
            hgvs_c=draft.hgvs_c or "",
            hgvs_p=draft.hgvs_p or "",
            consequence=draft.consequence or "",
            af=draft.af,
            dp=draft.dp,
            gt=draft.gt or "",
        )
        all_resources.extend(build_single_variant_resources(
            record=record,
            patient_id=job.patient_id,
            specimen_id=job.specimen_id,
            dna_change_type_code=draft.dna_change_type_code,
            dna_change_type_display=draft.dna_change_type_display,
            clinical_sig_key=draft.clinical_sig_key,
        ))
    return VcfToFhirConverter._assemble_bundle(all_resources)

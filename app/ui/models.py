from datetime import datetime

from sqlalchemy import DateTime, Float, ForeignKey, Integer, String, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base


class ConversionJob(Base):
    __tablename__ = "conversion_job"

    id: Mapped[int] = mapped_column(primary_key=True)
    filename: Mapped[str] = mapped_column(String(200))
    patient_id: Mapped[str] = mapped_column(String(100))
    specimen_id: Mapped[str] = mapped_column(String(100))
    specimen_type_code: Mapped[str | None] = mapped_column(String(50))
    specimen_type_display: Mapped[str | None] = mapped_column(String(200))
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())

    variants: Mapped[list["VariantDraft"]] = relationship(
        back_populates="job",
        order_by="VariantDraft.index",
        cascade="all, delete-orphan",
        lazy="selectin",
    )


class VariantDraft(Base):
    __tablename__ = "variant_draft"

    id: Mapped[int] = mapped_column(primary_key=True)
    job_id: Mapped[int] = mapped_column(ForeignKey("conversion_job.id"))
    index: Mapped[int] = mapped_column(Integer)
    source_type: Mapped[str] = mapped_column(String(10), default="vcf")   # "vcf" | "pdf" | "txt"
    chrom: Mapped[str | None] = mapped_column(String(20))
    pos: Mapped[int | None] = mapped_column(Integer)
    ref: Mapped[str | None] = mapped_column(String(500))
    alt: Mapped[str | None] = mapped_column(String(500))
    qual: Mapped[float | None] = mapped_column(Float)
    rs_id: Mapped[str | None] = mapped_column(String(50))
    ref_genome: Mapped[str] = mapped_column(String(20), default="GRCh38")
    gene: Mapped[str | None] = mapped_column(String(100))
    hgvs_c: Mapped[str | None] = mapped_column(String(500))
    hgvs_p: Mapped[str | None] = mapped_column(String(500))
    consequence: Mapped[str | None] = mapped_column(String(200))
    af: Mapped[float | None] = mapped_column(Float)
    dp: Mapped[int | None] = mapped_column(Integer)
    gt: Mapped[str | None] = mapped_column(String(20))
    dna_change_type_code: Mapped[str | None] = mapped_column(String(50))
    dna_change_type_display: Mapped[str | None] = mapped_column(String(200))
    clinical_sig_key: Mapped[str | None] = mapped_column(String(50))
    status: Mapped[str] = mapped_column(String(20), default="pending")

    job: Mapped["ConversionJob"] = relationship(back_populates="variants")

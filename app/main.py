from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.config import get_settings
from app.database import init_db, session_factory
from app.logger import setup_logging, get_logger
from app.routers import converter, pdf, loinc
from app.seed import seed

settings = get_settings()
setup_logging(log_level=settings.log_level, retention_days=settings.log_retention_days)
logger = get_logger("main")

_TAGS_METADATA = [
    {
        "name": "converter",
        "description": (
            "將 **VCF** 檔案轉換為 FHIR R4 `transaction` Bundle。\n\n"
            "每個變異位點產生一組 `MolecularSequence` + `Observation` 資源，"
            "Observation 包含 LOINC 標準化的基因名稱、HGVS c./p. notation、"
            "VAF（等位基因頻率）及雜合/純合狀態。"
        ),
    },
    {
        "name": "pdf",
        "description": (
            "解析 NGS 機構出具的 **PDF 報告**，抽取結構化變異資料。\n\n"
            "支援表格模式（大多數機構）與純文字 regex 模式（備援）。"
            "回傳原始解析結果，不含 FHIR 轉換。"
        ),
    },
]


@asynccontextmanager
async def lifespan(app: FastAPI):
    await init_db()
    async with session_factory() as session:
        await seed(session)
    logger.info("FHIR NGS Converter started | hapi=%s", settings.hapi_fhir_url)
    yield
    logger.info("FHIR NGS Converter stopped")


app = FastAPI(
    title=settings.app_title,
    version=settings.app_version,
    description=settings.app_description,
    openapi_tags=_TAGS_METADATA,
    contact={
        "name": "FHIR NGS Converter",
        "url": "https://github.com/your-org/fhir-ngs",
    },
    license_info={"name": "MIT"},
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(converter.router, prefix="/convert", tags=["converter"])
app.include_router(pdf.router, prefix="/pdf", tags=["pdf"])
app.include_router(loinc.router, prefix="/loinc", tags=["loinc"])


@app.get("/health", summary="Health check", tags=["system"])
def health():
    """回傳服務狀態，供 load balancer / CI 探測使用。"""
    return {"status": "ok", "version": settings.app_version}

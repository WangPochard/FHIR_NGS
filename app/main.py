from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.config import get_settings
from app.database import init_db, session_factory
from app.logger import setup_logging, get_logger
import app.valueset.models  # noqa: F401 — register tables with Base
import app.ui.models         # noqa: F401 — register tables with Base
from app.converter.router import router as converter_router
from app.valueset.router import router as valueset_router
from app.valueset.seed import seed
from app.ui.router import router as ui_router

settings = get_settings()
setup_logging(log_level=settings.log_level, retention_days=settings.log_retention_days)
logger = get_logger("main")

_TAGS_METADATA = [
    {
        "name": "converter",
        "description": (
            "VCF → FHIR R4 `transaction` Bundle，以及 NGS PDF 報告解析。\n\n"
            "- `POST /convert/vcf`：VCF 轉換，每個變異產生 `MolecularSequence` + `Observation`\n"
            "- `POST /convert/pdf`：PDF 解析，回傳結構化變異資料（不含 FHIR 轉換）"
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

app.include_router(converter_router, prefix="/convert", tags=["converter"])
app.include_router(valueset_router, prefix="/valueset", tags=["valueset"])
app.include_router(ui_router, prefix="/ui", tags=["ui"])


@app.get("/health", summary="Health check", tags=["system"])
def health():
    """回傳服務狀態，供 load balancer / CI 探測使用。"""
    return {"status": "ok", "version": settings.app_version}

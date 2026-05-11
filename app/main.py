from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.logger import setup_logging, get_logger
from app.routers import converter, pdf

setup_logging(log_level="INFO", retention_days=90)
logger = get_logger("main")

app = FastAPI(title="FHIR NGS Converter", version="0.1.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(converter.router, prefix="/convert", tags=["converter"])
app.include_router(pdf.router, prefix="/pdf", tags=["pdf"])


@app.on_event("startup")
async def startup():
    logger.info("FHIR NGS Converter started")


@app.on_event("shutdown")
async def shutdown():
    logger.info("FHIR NGS Converter stopped")


@app.get("/health")
def health():
    return {"status": "ok"}

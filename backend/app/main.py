"""
Aplicação FastAPI - Billing Control
"""
import logging

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
from fastapi.middleware.cors import CORSMiddleware

from app.config import settings
from app.api.v1 import router as v1_router
from app.core import BusinessError

logger = logging.getLogger(__name__)

# Criar aplicação FastAPI
app = FastAPI(
    title=settings.app_name,
    description="API de gestão odontológica",
    version="0.1.0",
)

# Configurar CORS
origins = [item.strip() for item in settings.cors_origins.split(",") if item.strip()]
app.add_middleware(
    CORSMiddleware,
    allow_origins=origins,
    allow_credentials=bool(origins),
    allow_methods=["*"],
    allow_headers=["*"],
)

# Incluir routers
app.include_router(v1_router)

@app.exception_handler(BusinessError)
async def business_error_handler(_: Request, exc: BusinessError):
    return JSONResponse(
        status_code=exc.status_code,
        content={"error": {"code": exc.code, "message": exc.message, "context": exc.context}},
    )


@app.exception_handler(Exception)
async def unexpected_error_handler(_: Request, exc: Exception):
    logger.exception("Erro inesperado ao processar requisição", exc_info=exc)
    return JSONResponse(
        status_code=500,
        content={"error": {"code": "INTERNAL_ERROR", "message": "Não foi possível concluir a operação. Tente novamente."}},
    )


@app.get("/health")
async def health():
    """Endpoint de health check"""
    return {"status": "ok", "app": settings.app_name}

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from app.api.routes import router
from app.api.exact_report_routes import router as exact_report_router
from app.api.marathi_register_routes import router as marathi_register_router
from app.api.workbook_parity_routes import router as workbook_parity_router
from app.core.config import settings
from app.db.session import Base, engine
import app.models  # noqa: F401

app = FastAPI(title=settings.app_name, version="0.1.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=[x.strip() for x in settings.cors_origins.split(",")],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

@app.on_event("startup")
def startup():
    Base.metadata.create_all(bind=engine)

app.include_router(router, prefix="/api/v1")
app.include_router(exact_report_router, prefix="/api/v1")
app.include_router(marathi_register_router, prefix='/api/v1')
app.include_router(workbook_parity_router, prefix="/api/v1")



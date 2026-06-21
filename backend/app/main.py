import asyncio
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from app.config import settings
from app.database import init_db
from app.routers import auth, projects, documents, rag, credits, account, support, chapters, billing, admin
from app.services.embedding_pool import embedding_pool
from app.services.export_service import start_export_worker

app = FastAPI(title="ResearcherHQ API", version="1.0.0")


@app.on_event("startup")
async def startup():
    init_db()
    await embedding_pool.start()
    asyncio.create_task(start_export_worker())

@app.on_event("shutdown")
async def shutdown():
    await embedding_pool.stop()

_www = settings.frontend_url.replace("https://", "https://www.", 1)
app.add_middleware(
    CORSMiddleware,
    allow_origins=[settings.frontend_url, _www],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

@app.get("/health")
def health():
    return {"status": "ok", "version": "1.0.0"}

app.include_router(auth.router, prefix="/auth", tags=["auth"])
app.include_router(projects.router, prefix="/projects", tags=["projects"])
app.include_router(documents.router, prefix="/documents", tags=["documents"])
# RAG router shares /projects prefix — RAG routes are POST /{id}/query and GET /{id}/messages,
# no path collision with projects CRUD routes
app.include_router(rag.router, prefix="/projects", tags=["rag"])
app.include_router(credits.router, prefix="/credits", tags=["credits"])
app.include_router(account.router, prefix="/account", tags=["account"])
app.include_router(support.router, prefix="/support", tags=["support"])
app.include_router(chapters.router, tags=["chapters"])
app.include_router(billing.router, prefix="/billing", tags=["billing"])
app.include_router(admin.router, prefix="/admin", tags=["admin"])

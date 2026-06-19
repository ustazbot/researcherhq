from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from app.config import settings
from app.routers import auth, projects, documents, rag, credits, account, support

app = FastAPI(title="ResearcherHQ API", version="1.0.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=[settings.frontend_url],
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

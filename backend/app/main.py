import asyncio
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from apscheduler.schedulers.background import BackgroundScheduler
from app.config import settings
from app.database import init_db
from app.routers import auth, projects, documents, rag, credits, account, support, chapters, billing, admin, voice_profile, search, sv_feedback, chat_sessions, surveys, public_surveys, survey_analysis
from app.services.embedding_pool import embedding_pool
from app.services.export_service import start_export_worker
from app.services.credit_reset import reset_expired_credits

app = FastAPI(title="ResearcherHQ API", version="1.0.0")

_scheduler = BackgroundScheduler()


@app.on_event("startup")
async def startup():
    init_db()
    await embedding_pool.start()
    asyncio.create_task(start_export_worker())
    _scheduler.add_job(reset_expired_credits, "cron", hour=2, minute=0)
    _scheduler.start()


@app.on_event("shutdown")
async def shutdown():
    _scheduler.shutdown(wait=False)
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
app.include_router(voice_profile.router, prefix="/voice-profile", tags=["voice-profile"])
app.include_router(search.router, prefix="/search", tags=["search"])
app.include_router(sv_feedback.router, tags=["sv_feedback"])
app.include_router(chat_sessions.router, prefix="/projects", tags=["chat-sessions"])
app.include_router(surveys.router, tags=["surveys"])
app.include_router(public_surveys.router, prefix="/public", tags=["public-surveys"])
app.include_router(survey_analysis.router, tags=["survey-analysis"])

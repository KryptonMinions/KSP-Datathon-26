from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.config import get_settings
from app.routers import ask, auth, export, voice

app = FastAPI(title="KSP Datathon Backend")

app.add_middleware(
    CORSMiddleware,
    allow_origins=get_settings().frontend_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(auth.router)
app.include_router(voice.router)
app.include_router(ask.router)
app.include_router(export.router)


@app.get("/healthz")
def healthz() -> dict:
    return {"status": "ok"}

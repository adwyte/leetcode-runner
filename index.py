# index.py
import os
from pathlib import Path
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import RedirectResponse, FileResponse
from routers.generate import router as generate_router

app = FastAPI(title="LeetCode Class → Runnable C++")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(generate_router, prefix="/api", tags=["generate"])

PUBLIC = Path("public")
INDEX = PUBLIC / "index.html"

# Local dev: serve the actual file if it exists.
# Vercel: static files are served by the platform, so we just redirect.
@app.get("/", include_in_schema=False)
def home():
    if INDEX.exists():
        return FileResponse(INDEX)
    return RedirectResponse("/index.html", status_code=307)

if PUBLIC.exists() and not os.environ.get("VERCEL_REGION"):
    from fastapi.staticfiles import StaticFiles
    app.mount("/", StaticFiles(directory="public", html=True), name="frontend")

@app.get("/health")
def health():
    return {"ok": True}

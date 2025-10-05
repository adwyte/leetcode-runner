from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from starlette.responses import RedirectResponse

from routers.generate import router as generate_router

app = FastAPI(title="LeetCode Class → Runnable C++")

# CORS (adjust origins as needed)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # lock down to your domain(s) in prod
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Mount routers here (easy to add more later)
app.include_router(generate_router, prefix="/api", tags=["generate"])

# Serve the frontend
app.mount("/", StaticFiles(directory="public", html=True), name="frontend")

# Optional: root redirects to /
@app.get("/health")
def health():
    return {"ok": True}

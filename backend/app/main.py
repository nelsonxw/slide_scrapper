"""
FastAPI Main Application Entry Point for Slide Scrapper.
"""
from __future__ import annotations

import uvicorn
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from pathlib import Path

from app.config import settings
from app.routes import scrape, slides


def create_app() -> FastAPI:
    app = FastAPI(
        title="PowerPoint Web Scraper & Slide Studio",
        description="Scrapes websites for PowerPoint downloads, splits presentations into individual slides, and uploads to Firebase Storage.",
        version="1.0.0",
    )

    # Enable CORS for frontend development
    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    # Register API routers
    app.include_router(scrape.router)
    app.include_router(slides.router)

    @app.get("/api/health")
    def health_check():
        return {
            "status": "online",
            "storage_bucket": settings.storage_bucket,
            "version": "1.0.0",
        }

    # Mount static frontend build if it exists
    frontend_dist = Path(__file__).resolve().parent.parent.parent / "frontend" / "dist"
    if frontend_dist.exists() and frontend_dist.is_dir():
        app.mount("/", StaticFiles(directory=str(frontend_dist), html=True), name="frontend")

    return app


app = create_app()


def run():
    uvicorn.run("app.main:app", host=settings.host, port=settings.port, reload=True)


if __name__ == "__main__":
    run()

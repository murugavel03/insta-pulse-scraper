"""
main.py — FastAPI backend server for the IG Reel Business Lead Scraper.
"""

import asyncio
import os
import sys
import uuid
from typing import Dict

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import Response
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

sys.path.insert(0, os.path.dirname(__file__))

from detector import ExtractedLead
from exporter import export_to_excel
from scraper import InstagramScraper


app = FastAPI(title="IG Lead Scraper API", version="3.0.0")
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"])

_sessions: Dict[str, InstagramScraper] = {}
_results:  Dict[str, dict] = {}
_progress: Dict[str, dict] = {}


class SessionLoginRequest(BaseModel):
    sessionid: str

class ScrapeRequest(BaseModel):
    session_id: str
    reel_url: str
    max_comments: int = 500
    min_confidence: int = 25


@app.post("/api/login")
async def login(req: SessionLoginRequest):
    """Log in using the Instagram sessionid cookie from the browser."""
    scraper = InstagramScraper()
    loop = asyncio.get_event_loop()
    result = await loop.run_in_executor(None, lambda: scraper.login_by_session(req.sessionid))

    if result["success"]:
        session_id = str(uuid.uuid4())
        _sessions[session_id] = scraper
        _progress[session_id] = {"message": "Ready", "percent": 0}
        return {"session_id": session_id, "status": "success", **result}

    raise HTTPException(status_code=401, detail=result["message"])


@app.post("/api/scrape")
async def scrape(req: ScrapeRequest):
    scraper = _sessions.get(req.session_id)
    if not scraper:
        raise HTTPException(status_code=404, detail="Session not found. Please log in again.")

    _progress[req.session_id] = {"message": "Starting…", "percent": 0, "done": False, "error": None}

    def progress_callback(message: str, percent: int):
        _progress[req.session_id] = {"message": message, "percent": percent, "done": percent >= 100, "error": None}

    async def run_scrape():
        loop = asyncio.get_event_loop()
        result = await loop.run_in_executor(
            None,
            lambda: scraper.scrape_reel(req.reel_url, req.max_comments, req.min_confidence, progress_callback),
        )
        _results[req.session_id] = result
        if not result["success"]:
            _progress[req.session_id] = {"message": result["message"], "percent": 100, "done": True, "error": result["message"]}
        else:
            _progress[req.session_id] = {"message": result["message"], "percent": 100, "done": True, "error": None}

    asyncio.create_task(run_scrape())
    return {"status": "started"}


@app.get("/api/progress/{session_id}")
async def get_progress(session_id: str):
    if session_id not in _progress:
        raise HTTPException(status_code=404, detail="Session not found.")
    return _progress[session_id]


@app.get("/api/results/{session_id}")
async def get_results(session_id: str):
    result = _results.get(session_id)
    if not result:
        raise HTTPException(status_code=404, detail="No results yet.")
    return result


@app.get("/api/download/{session_id}")
async def download_excel(session_id: str, reel_url: str = ""):
    result = _results.get(session_id)
    if not result or not result.get("leads"):
        raise HTTPException(status_code=404, detail="No leads to export.")

    leads = [ExtractedLead(
        instagram_handle=d["instagram_handle"], commenter_name=d["commenter_name"],
        comment_text=d["comment_text"], phones=d["phones"], emails=d["emails"],
        websites=d["websites"], confidence_score=d["confidence_score"],
        detection_reasons=d["detection_reasons"], is_business=d["is_business"],
    ) for d in result["leads"]]

    xlsx_bytes = export_to_excel(leads, reel_url or "Instagram Reel")
    return Response(
        content=xlsx_bytes,
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={"Content-Disposition": "attachment; filename=business_leads.xlsx"},
    )


@app.get("/api/logout/{session_id}")
async def logout(session_id: str):
    _sessions.pop(session_id, None)
    _results.pop(session_id, None)
    _progress.pop(session_id, None)
    return {"status": "logged out"}


@app.get("/api/health")
async def health():
    return {"status": "ok"}


frontend_dir = os.path.join(os.path.dirname(__file__), "..", "frontend")
if os.path.isdir(frontend_dir):
    app.mount("/", StaticFiles(directory=frontend_dir, html=True), name="frontend")

if __name__ == "__main__":
    import uvicorn
    uvicorn.run("main:app", host="127.0.0.1", port=8000, reload=False)

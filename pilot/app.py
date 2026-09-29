"""FastAPI app: dashboard + a handful of endpoints. Run with `python -m pilot`."""
from __future__ import annotations

import shutil
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, HTTPException, UploadFile
from fastapi.responses import FileResponse, JSONResponse

from . import config, db, extract, pipeline, watcher

STATIC = Path(__file__).parent / "static"


@asynccontextmanager
async def lifespan(app: FastAPI):
    db.connect()
    stop = watcher.start()
    db.log(f"pilot started; extractor = {extract.extractor_name()}; watching {config.INBOX}")
    yield
    stop.set()


app = FastAPI(title="Workflow Automation Pilot", lifespan=lifespan)


@app.get("/")
def index():
    return FileResponse(STATIC / "index.html")


@app.get("/api/state")
def state():
    s = db.state()
    s["extractor"] = extract.extractor_name()
    s["inbox"] = str(config.INBOX)
    return s


@app.post("/api/upload")
async def upload(file: UploadFile):
    if not file.filename or not file.filename.lower().endswith(".pdf"):
        raise HTTPException(400, "PDF only")
    config.INBOX.mkdir(parents=True, exist_ok=True)
    target = config.INBOX / Path(file.filename).name
    target.write_bytes(await file.read())
    return {"queued": target.name}


@app.post("/api/invoices/{invoice_id}/approve")
@app.get("/api/invoices/{invoice_id}/approve")  # GET so the link in the approval email works
def approve(invoice_id: int):
    try:
        pipeline.approve(invoice_id)
    except ValueError as e:
        raise HTTPException(409, str(e))
    return {"ok": True}


@app.post("/api/invoices/{invoice_id}/reject")
@app.get("/api/invoices/{invoice_id}/reject")
def reject(invoice_id: int):
    try:
        pipeline.reject(invoice_id)
    except ValueError as e:
        raise HTTPException(409, str(e))
    return {"ok": True}


@app.post("/api/demo/load")
def demo_load():
    """Drop the 20 sample invoices into the inbox (the watcher picks them up)."""
    config.INBOX.mkdir(parents=True, exist_ok=True)
    n = 0
    for pdf in sorted(config.SAMPLE_INVOICES.glob("*.pdf")):
        if not (config.INBOX / pdf.name).exists() and not (config.PROCESSED / pdf.name).exists():
            shutil.copy(pdf, config.INBOX / pdf.name)
            n += 1
    return {"queued": n}


@app.post("/api/demo/reset")
def demo_reset():
    db.reset()
    for d in (config.INBOX, config.PROCESSED):
        for f in d.glob("*.pdf"):
            f.unlink()
    if config.LEDGER.exists():
        config.LEDGER.unlink()
    db.log("demo reset")
    return {"ok": True}


@app.get("/api/ledger")
def ledger_csv():
    if not config.LEDGER.exists():
        return JSONResponse({"error": "no ledger yet"}, status_code=404)
    return FileResponse(config.LEDGER, media_type="text/csv", filename="ledger.csv")

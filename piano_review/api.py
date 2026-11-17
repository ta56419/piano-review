"""Thin loopback API. Model jobs run serially outside the request thread."""
from concurrent.futures import ThreadPoolExecutor
import json
import logging
from pathlib import Path
from threading import Lock
from typing import Literal
from uuid import uuid4

from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

from .pipeline import ROOT, run_analysis

app = FastAPI(title="Piano Review", docs_url="/api/docs")
executor = ThreadPoolExecutor(max_workers=1)
jobs = {}
job_lock = Lock()


class AnalysisRequest(BaseModel):
    sample: Literal["real", "controlled"]


@app.get("/api/health")
def health():
    return {"status": "ok", "app": "piano-review"}


@app.get("/api/report")
def report(sample: Literal["real", "controlled"] = "real"):
    path = ROOT / "reports" / f"{sample}.json"
    if not path.is_file():
        raise HTTPException(404, "Отчёт ещё не рассчитан. Нажмите «Пересчитать».")
    return json.loads(path.read_text(encoding="utf-8"))


@app.get("/api/raw")
def raw_detections(sample: Literal["real", "controlled"] = "real"):
    return FileResponse(ROOT / "reports" / f"{sample}-notes.json", media_type="application/json",
                        filename=f"{sample}-notes.json")


@app.get("/api/decoder-comparison")
def decoder_comparison():
    return FileResponse(ROOT / "reports/decoder-comparison.json", media_type="application/json")


def analyze_job(job_id, sample):
    jobs[job_id] = {"status": "running", "message": "Анализируем звук…"}
    try:
        result = run_analysis(sample)
        jobs[job_id] = {"status": "completed", "message": "Анализ завершён", "report": result}
    except Exception:
        logging.exception("Analysis failed for %s", sample)
        jobs[job_id] = {"status": "failed", "message": "Не удалось разобрать звук. Попробуйте ещё раз. Подробности — в консоли приложения."}


@app.post("/api/analyze", status_code=202)
def analyze(body: AnalysisRequest, request: Request):
    # This app is local. Do not allow a foreign website to start expensive jobs.
    origin = request.headers.get("origin")
    if origin and origin not in {"http://127.0.0.1:8765", "http://localhost:8765"}:
        raise HTTPException(403, "Local requests only")
    with job_lock:
        if any(job["status"] in {"queued", "running"} for job in jobs.values()):
            raise HTTPException(409, "Анализ уже запущен. Дождитесь результата.")
        job_id = uuid4().hex
        jobs[job_id] = {"status": "queued", "message": "Подготовка аудио…"}
        executor.submit(analyze_job, job_id, body.sample)
    return {"job_id": job_id}


@app.get("/api/jobs/{job_id}")
def job_status(job_id: str):
    if job_id not in jobs:
        raise HTTPException(404, "Job not found")
    return jobs[job_id]


@app.get("/media/{name}")
def media(name: str):
    if name not in {"real.mp4", "controlled.wav"}:
        raise HTTPException(404, "Media not found")
    return FileResponse(ROOT / "data" / name)


@app.get("/reference.pdf")
def reference_score():
    return FileResponse(ROOT / "data" / "reference.pdf", media_type="application/pdf")


@app.get("/demo.mp4")
def demo_recording():
    return FileResponse(ROOT / "recording" / "Piano-Review-Demo.mp4", media_type="video/mp4")


app.mount("/", StaticFiles(directory=ROOT / "web", html=True), name="web")

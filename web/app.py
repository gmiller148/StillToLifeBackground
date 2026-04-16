from __future__ import annotations

import asyncio
import json
import logging
from pathlib import Path

from fastapi import FastAPI, File, Form, HTTPException, UploadFile
from fastapi.responses import FileResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles
from PIL import Image

from web.jobs import JobConfig, JobStore
from web.processing import progress_queues, run_pipeline
from web.wallpaper import install_as_wallpaper

logger = logging.getLogger(__name__)

PROJECT_DIR = Path(__file__).resolve().parent.parent
DATA_DIR = PROJECT_DIR / "data"
UPLOADS_DIR = DATA_DIR / "uploads"
VIDEOS_DIR = DATA_DIR / "videos"

ALLOWED_EXTENSIONS = {".jpg", ".jpeg", ".png", ".heic", ".webp", ".tiff", ".tif", ".bmp"}

app = FastAPI(title="StillToLife")
job_store = JobStore(DATA_DIR)


@app.on_event("startup")
async def startup():
    UPLOADS_DIR.mkdir(parents=True, exist_ok=True)
    VIDEOS_DIR.mkdir(parents=True, exist_ok=True)


# --- API Routes ---

@app.get("/api/jobs")
async def list_jobs():
    jobs = job_store.list_jobs()
    return [j.model_dump() for j in reversed(jobs)]


@app.get("/api/jobs/{job_id}")
async def get_job(job_id: str):
    job = job_store.get_job(job_id)
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")
    return job.model_dump()


@app.post("/api/jobs", status_code=201)
async def create_job(
    image: UploadFile = File(...),
    config: str = Form("{}"),
):
    # Validate file extension
    filename = image.filename or "upload"
    ext = Path(filename).suffix.lower()
    if ext not in ALLOWED_EXTENSIONS:
        raise HTTPException(
            status_code=400,
            detail=f"Unsupported file type '{ext}'. Allowed: {', '.join(sorted(ALLOWED_EXTENSIONS))}",
        )

    # Parse config JSON
    try:
        config_data = json.loads(config)
    except json.JSONDecodeError:
        raise HTTPException(status_code=400, detail="Invalid config JSON")

    try:
        job_config = JobConfig(**config_data)
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"Invalid config: {e}")

    job = job_store.create_job(original_filename=filename, config=job_config)

    # Save uploaded file
    image_path = UPLOADS_DIR / f"{job.id}{ext}"
    content = await image.read()
    image_path.write_bytes(content)

    # Generate thumbnail
    try:
        _generate_thumbnail(image_path, UPLOADS_DIR / f"{job.id}_thumb.jpg")
    except Exception:
        logger.warning("Could not generate thumbnail for %s, will use original", filename)

    # Start processing in background
    asyncio.create_task(run_pipeline(job.id, image_path, job_config, job_store, PROJECT_DIR))

    return job.model_dump()


@app.get("/api/jobs/{job_id}/progress")
async def job_progress(job_id: str):
    job = job_store.get_job(job_id)
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")

    async def event_stream():
        queue = progress_queues.get(job_id)

        if queue is None:
            # Job already finished -- send terminal event
            if job.status == "completed":
                yield f"event: complete\ndata: {json.dumps({'job_id': job_id, 'video_url': f'/api/jobs/{job_id}/video'})}\n\n"
            elif job.status == "failed":
                yield f"event: error\ndata: {json.dumps({'message': job.error or 'Unknown error'})}\n\n"
            else:
                # Job is pending (waiting for semaphore) -- poll until queue appears or status changes
                for _ in range(300):  # up to 5 minutes
                    await asyncio.sleep(1)
                    queue = progress_queues.get(job_id)
                    if queue:
                        break
                    current = job_store.get_job(job_id)
                    if current and current.status in ("completed", "failed"):
                        if current.status == "completed":
                            yield f"event: complete\ndata: {json.dumps({'job_id': job_id, 'video_url': f'/api/jobs/{job_id}/video'})}\n\n"
                        else:
                            yield f"event: error\ndata: {json.dumps({'message': current.error or 'Unknown error'})}\n\n"
                        return
                if not queue:
                    return

        # Stream from queue
        while True:
            try:
                event = await asyncio.wait_for(queue.get(), timeout=120)
            except asyncio.TimeoutError:
                yield f"event: progress\ndata: {json.dumps({'stage': 'processing', 'message': 'Still processing...', 'percent': -1})}\n\n"
                continue

            event_type = event.get("type", "progress")
            yield f"event: {event_type}\ndata: {json.dumps(event)}\n\n"

            if event_type in ("complete", "error"):
                break

    return StreamingResponse(
        event_stream(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


@app.get("/api/jobs/{job_id}/video")
async def download_video(job_id: str):
    job = job_store.get_job(job_id)
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")
    if job.status != "completed":
        raise HTTPException(status_code=400, detail="Video not ready")

    video_path = VIDEOS_DIR / f"{job_id}.mov"
    if not video_path.exists():
        raise HTTPException(status_code=404, detail="Video file not found")

    download_name = Path(job.original_filename).stem + "_wallpaper.mov"
    return FileResponse(
        video_path,
        media_type="video/quicktime",
        filename=download_name,
    )


@app.get("/api/jobs/{job_id}/preview")
async def preview_video(job_id: str):
    job = job_store.get_job(job_id)
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")
    if job.status != "completed":
        raise HTTPException(status_code=400, detail="Video not ready")

    video_path = VIDEOS_DIR / f"{job_id}.mov"
    if not video_path.exists():
        raise HTTPException(status_code=404, detail="Video file not found")

    return FileResponse(
        video_path,
        media_type="video/mp4",
        headers={"Content-Disposition": "inline"},
    )


@app.get("/api/jobs/{job_id}/thumbnail")
async def get_thumbnail(job_id: str):
    thumb = UPLOADS_DIR / f"{job_id}_thumb.jpg"
    if thumb.exists():
        return FileResponse(thumb, media_type="image/jpeg")

    # Fall back to original upload
    for ext in ALLOWED_EXTENSIONS:
        original = UPLOADS_DIR / f"{job_id}{ext}"
        if original.exists():
            return FileResponse(original)

    raise HTTPException(status_code=404, detail="Thumbnail not found")


@app.post("/api/jobs/{job_id}/install")
async def install_wallpaper_endpoint(job_id: str):
    job = job_store.get_job(job_id)
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")
    if job.status != "completed":
        raise HTTPException(status_code=400, detail="Video not ready")

    video_path = VIDEOS_DIR / f"{job_id}.mov"
    if not video_path.exists():
        raise HTTPException(status_code=404, detail="Video file not found")

    display_name = Path(job.original_filename).stem
    success, message = await install_as_wallpaper(video_path, display_name, PROJECT_DIR)

    if success:
        job_store.update_job(job_id, installed_as_wallpaper=True)
        return {"success": True, "message": message}
    else:
        raise HTTPException(status_code=500, detail=message)


@app.delete("/api/jobs/{job_id}")
async def delete_job(job_id: str):
    job = job_store.get_job(job_id)
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")

    # Delete files
    for ext in ALLOWED_EXTENSIONS:
        (UPLOADS_DIR / f"{job_id}{ext}").unlink(missing_ok=True)
    (UPLOADS_DIR / f"{job_id}_thumb.jpg").unlink(missing_ok=True)
    (VIDEOS_DIR / f"{job_id}.mov").unlink(missing_ok=True)

    job_store.delete_job(job_id)
    return {"success": True}


# --- Static Files & Frontend ---

app.mount("/static", StaticFiles(directory=str(PROJECT_DIR / "web" / "static")), name="static")


@app.get("/")
async def index():
    return FileResponse(str(PROJECT_DIR / "web" / "static" / "index.html"))


# --- Helpers ---

def _generate_thumbnail(image_path: Path, thumb_path: Path, max_width: int = 400):
    """Generate a JPEG thumbnail from an image file."""
    img = Image.open(image_path)
    img.thumbnail((max_width, max_width))
    if img.mode in ("RGBA", "P"):
        img = img.convert("RGB")
    img.save(thumb_path, "JPEG", quality=85)

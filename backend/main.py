from fastapi import FastAPI, UploadFile, File, HTTPException, BackgroundTasks
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
import shutil
from pathlib import Path
from threading import Thread, Lock
import uuid
from typing import Any, Dict
from video_processing import VideoProcessor
import uvicorn

app = FastAPI(title="Surgical Video De-identification", version="1.0.0")

BASE_DIR = Path(__file__).resolve().parent.parent
FRONTEND_BUILD_DIR = BASE_DIR / "frontend" / "build"

# CORS for frontend (development only; production serves same origin)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Initialize processor
processor = VideoProcessor(upload_dir=str(BASE_DIR / "backend" / "uploads"), frames_dir=str(BASE_DIR / "backend" / "frames"))

task_store: Dict[str, Dict[str, Any]] = {}
task_lock = Lock()

# Request models
class ExtractFramesRequest(BaseModel):
    video_path: str

class ExportVideoRequest(BaseModel):
    original_video: str
    frame_timestamps: list[float]
    output_filename: str = "deidentified_video.mp4"

class CleanupRequest(BaseModel):
    video_path: str = ""


def create_task(task_type: str, message: str) -> str:
    task_id = uuid.uuid4().hex
    with task_lock:
        task_store[task_id] = {
            "task_id": task_id,
            "task_type": task_type,
            "status": "running",
            "progress": 0,
            "message": message,
            "result": None,
            "error": None,
        }
    return task_id


def update_task(task_id: str, **kwargs: Any) -> None:
    with task_lock:
        if task_id in task_store:
            task_store[task_id].update(kwargs)


def run_extract_frames(task_id: str, video_path: str) -> None:
    try:
        metadata = processor.get_video_metadata(video_path)
        update_task(task_id, message="Extracting frames...", progress=0)

        def progress_callback(percent: int) -> None:
            update_task(task_id, progress=percent, message=f"Extracting frames... {percent}%")

        frames = processor.extract_frames_at_fps(video_path, fps=5.0, progress_callback=progress_callback)
        update_task(
            task_id,
            status="completed",
            progress=100,
            message="Frame extraction complete.",
            result={"metadata": metadata, "frames": frames},
        )
    except Exception as e:
        update_task(task_id, status="failed", message=str(e), error=str(e), progress=0)


def run_export_video(task_id: str, original_video: str, frame_timestamps: list[float], output_filename: str) -> None:
    try:
        output_path = processor.upload_dir / output_filename
        update_task(task_id, message="Exporting video...", progress=0)

        def progress_callback(percent: int, phase: str = "Processing") -> None:
            update_task(task_id, progress=percent, message=f"{phase}: {percent}%")

        processor.create_blurred_video(original_video, frame_timestamps, str(output_path), progress_callback=progress_callback)

        original_path = Path(original_video)
        if original_path.exists() and original_path.resolve() != output_path.resolve():
            original_path.unlink()

        for f in processor.frames_dir.glob("*"):
            if f.is_file():
                f.unlink()

        update_task(
            task_id,
            status="completed",
            progress=100,
            message="Export complete.",
            result={"output_path": str(output_path)},
        )
    except Exception as e:
        update_task(task_id, status="failed", message=str(e), error=str(e), progress=0)

# Mount static files for serving frames only; frontend build mounts after API routes
app.mount("/frames", StaticFiles(directory=str(processor.frames_dir)), name="frames")

@app.get("/health")
async def health_check():
    return {"status": "ok"}

@app.post("/upload")
async def upload_video(file: UploadFile = File(...)):
    """Upload a video file."""
    if not file.filename.lower().endswith(('.mp4', '.mov', '.avi', '.mkv', '.webm')):
        raise HTTPException(status_code=400, detail="Unsupported file type")

    # Save uploaded file
    upload_path = processor.upload_dir / file.filename
    with open(upload_path, "wb") as buffer:
        shutil.copyfileobj(file.file, buffer)

    return {"filename": file.filename, "path": str(upload_path)}

@app.post("/extract-frames")
async def extract_frames(request: ExtractFramesRequest):
    """Start frame extraction in the background."""
    video_path = request.video_path
    if not Path(video_path).exists():
        raise HTTPException(status_code=404, detail="Video file not found")

    task_id = create_task("extract_frames", "Starting frame extraction")
    thread = Thread(target=run_extract_frames, args=(task_id, video_path), daemon=True)
    thread.start()
    return {"task_id": task_id}

@app.post("/cleanup")
async def cleanup_session(request: CleanupRequest):
    """Delete the uploaded source video and all preview frames for an abandoned session."""
    if request.video_path:
        video_path = Path(request.video_path).resolve()
        uploads_dir = processor.upload_dir.resolve()
        if video_path.exists() and uploads_dir in video_path.parents:
            video_path.unlink(missing_ok=True)

    for f in processor.frames_dir.glob("*"):
        if f.is_file():
            f.unlink()

    return {"status": "ok"}

@app.post("/export-video")
async def export_video(request: ExportVideoRequest):
    """Start export in the background."""
    original_video = request.original_video
    frame_timestamps = request.frame_timestamps
    output_filename = request.output_filename

    if not Path(original_video).exists():
        raise HTTPException(status_code=404, detail="Original video not found")

    task_id = create_task("export_video", "Starting export")
    thread = Thread(target=run_export_video, args=(task_id, original_video, frame_timestamps, output_filename), daemon=True)
    thread.start()
    return {"task_id": task_id}

@app.get("/download/{filename}")
async def download_file(filename: str, background_tasks: BackgroundTasks):
    file_path = processor.upload_dir / filename
    if not file_path.exists():
        raise HTTPException(status_code=404, detail="File not found")
    background_tasks.add_task(file_path.unlink, missing_ok=True)
    return FileResponse(path=str(file_path), media_type="video/mp4", filename=filename)

@app.get("/tasks/{task_id}")
async def get_task_status(task_id: str):
    with task_lock:
        task = task_store.get(task_id)
        if not task:
            raise HTTPException(status_code=404, detail="Task not found")
        return task

# Mount frontend build after API routes so the API endpoints are not shadowed
if FRONTEND_BUILD_DIR.exists():
    app.mount("/", StaticFiles(directory=str(FRONTEND_BUILD_DIR), html=True), name="frontend")

if __name__ == "__main__":
    uvicorn.run(app, host="0.0.0.0", port=8000)
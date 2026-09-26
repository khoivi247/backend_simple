import os
import json
import uuid
import shutil
from datetime import datetime
from pathlib import Path
from typing import Optional, List

from fastapi import FastAPI, File, UploadFile, Form, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel
from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    PORT: int = 3000
    FRONTEND_URL: str = "http://localhost:5173"
    VIDEO_DIR: str = "./videos"
    MAX_FILE_SIZE: int = 500 * 1024 * 1024  # 500MB
    
    class Config:
        env_file = ".env"


settings = Settings()

# Ensure video directory exists
VIDEO_DIR = Path(settings.VIDEO_DIR)
VIDEO_DIR.mkdir(exist_ok=True)

app = FastAPI(title="Video Class System - Simple")

app.add_middleware(
    CORSMiddleware,
    allow_origins=[settings.FRONTEND_URL],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Serve uploaded videos
app.mount("/files", StaticFiles(directory=VIDEO_DIR), name="files")


class VideoMeta(BaseModel):
    id: str
    title: str
    description: Optional[str] = None
    filename: str
    class_name: str
    student_name: str
    file_size: int
    created_at: str
    url: str


META_FILE = VIDEO_DIR / "videos.json"


def load_videos() -> List[dict]:
    if META_FILE.exists():
        with open(META_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    return []


def save_videos(videos: List[dict]):
    with open(META_FILE, "w", encoding="utf-8") as f:
        json.dump(videos, f, ensure_ascii=False, indent=2)


@app.get("/api/health")
async def health():
    return {"status": "ok", "timestamp": datetime.utcnow().isoformat()}


@app.post("/api/videos/upload")
async def upload_video(
    file: UploadFile = File(...),
    title: str = Form(...),
    description: str = Form(""),
    class_name: str = Form(...),
    student_name: str = Form(...),
):
    # Validate file type
    if not file.content_type or not file.content_type.startswith("video/"):
        raise HTTPException(400, "File must be a video")
    
    # Validate file size
    content = await file.read()
    if len(content) > settings.MAX_FILE_SIZE:
        raise HTTPException(400, f"File too large (max {settings.MAX_FILE_SIZE // (1024*1024)}MB)")
    
    # Generate unique ID and save file
    video_id = str(uuid.uuid4())[:8]
    ext = Path(file.filename).suffix or ".mp4"
    filename = f"{video_id}{ext}"
    filepath = VIDEO_DIR / filename
    
    with open(filepath, "wb") as f:
        f.write(content)
    
    # Save metadata
    video_meta = {
        "id": video_id,
        "title": title,
        "description": description,
        "filename": filename,
        "class_name": class_name,
        "student_name": student_name,
        "file_size": len(content),
        "created_at": datetime.utcnow().isoformat(),
        "url": f"/files/{filename}",
    }
    
    videos = load_videos()
    videos.insert(0, video_meta)  # newest first
    save_videos(videos)
    
    return {"video": video_meta}


@app.get("/api/videos")
async def list_videos(
    class_name: Optional[str] = Query(None),
    student_name: Optional[str] = Query(None),
    page: int = Query(1, ge=1),
    limit: int = Query(20, ge=1, le=50),
):
    videos = load_videos()
    
    if class_name:
        videos = [v for v in videos if v["class_name"] == class_name]
    if student_name:
        videos = [v for v in videos if v["student_name"] == student_name]
    
    total = len(videos)
    start = (page - 1) * limit
    end = start + limit
    
    return {
        "videos": videos[start:end],
        "pagination": {
            "page": page,
            "limit": limit,
            "total": total,
            "total_pages": (total + limit - 1) // limit,
        },
    }


@app.get("/api/videos/{video_id}")
async def get_video(video_id: str):
    videos = load_videos()
    video = next((v for v in videos if v["id"] == video_id), None)
    if not video:
        raise HTTPException(404, "Video not found")
    return {"video": video}


@app.delete("/api/videos/{video_id}")
async def delete_video(video_id: str):
    videos = load_videos()
    video = next((v for v in videos if v["id"] == video_id), None)
    if not video:
        raise HTTPException(404, "Video not found")
    
    # Delete file
    filepath = VIDEO_DIR / video["filename"]
    if filepath.exists():
        filepath.unlink()
    
    # Remove from metadata
    videos = [v for v in videos if v["id"] != video_id]
    save_videos(videos)
    
    return {"message": "Video deleted"}


@app.get("/api/classes")
async def list_classes():
    videos = load_videos()
    classes = sorted(set(v["class_name"] for v in videos))
    return {"classes": classes}


@app.get("/api/students")
async def list_students(class_name: Optional[str] = None):
    videos = load_videos()
    if class_name:
        videos = [v for v in videos if v["class_name"] == class_name]
    students = sorted(set(v["student_name"] for v in videos))
    return {"students": students}


if __name__ == "__main__":
    import uvicorn
    uvicorn.run("app.main:app", host="0.0.0.0", port=settings.PORT, reload=True)
from __future__ import annotations

import json
import threading
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

from pydantic import BaseModel, Field


class JobConfig(BaseModel):
    # --- Animation Preset ---
    style: str = "dolly"
    intensity: float = 1.2
    preset_reverse: bool = False
    preset_smooth: Optional[bool] = None
    preset_loop: Optional[bool] = None
    preset_depth: Optional[float] = None
    preset_phase: Optional[float] = None
    preset_zoom: Optional[float] = None
    preset_steady: Optional[float] = None
    preset_isometric: Optional[float] = None
    # Circle-specific (3-component vectors)
    circle_amp_x: Optional[float] = None
    circle_amp_y: Optional[float] = None
    circle_amp_z: Optional[float] = None
    circle_phase_x: Optional[float] = None
    circle_phase_y: Optional[float] = None
    circle_phase_z: Optional[float] = None

    # --- Base Depth/Camera State ---
    state_height: Optional[float] = None
    state_steady: Optional[float] = None
    state_focus: Optional[float] = None
    state_zoom: Optional[float] = None
    state_isometric: Optional[float] = None
    state_dolly: Optional[float] = None
    state_invert: Optional[float] = None
    state_mirror: Optional[bool] = None
    state_offset_x: Optional[float] = None
    state_offset_y: Optional[float] = None
    state_center_x: Optional[float] = None
    state_center_y: Optional[float] = None
    state_origin_x: Optional[float] = None
    state_origin_y: Optional[float] = None

    # --- Post-Processing: Vignette ---
    vignette_enable: bool = False
    vignette_intensity: float = 0.2
    vignette_decay: float = 20.0

    # --- Post-Processing: Lens Distortion ---
    lens_enable: bool = False
    lens_intensity: float = 0.1
    lens_decay: float = 0.4
    lens_quality: int = 30

    # --- Post-Processing: Depth of Field (Blur) ---
    blur_enable: bool = False
    blur_intensity: float = 1.0
    blur_start: float = 0.6
    blur_end: float = 1.0
    blur_exponent: float = 2.0
    blur_quality: int = 4
    blur_directions: int = 16

    # --- Post-Processing: Inpaint ---
    inpaint_enable: bool = False
    inpaint_black: bool = False
    inpaint_limit: float = 1.0

    # --- Post-Processing: Colors ---
    colors_enable: bool = False
    colors_saturation: float = 100.0
    colors_contrast: float = 100.0
    colors_brightness: float = 100.0
    colors_gamma: float = 100.0
    colors_grayscale: float = 0.0
    colors_sepia: float = 0.0

    # --- Custom Oscillators (JSON array) ---
    oscillators: Optional[str] = None

    # --- Output ---
    width: int = 3840
    height: int = 2160
    fps: int = 30
    duration: int = 22
    crf: int = 18
    render_quality: float = 60.0
    ssaa: Optional[float] = None
    speed: Optional[float] = None


class Job(BaseModel):
    id: str
    status: str = "pending"  # pending | processing | completed | failed
    created_at: str = ""
    completed_at: Optional[str] = None
    original_filename: str = ""
    config: JobConfig = Field(default_factory=JobConfig)
    error: Optional[str] = None
    installed_as_wallpaper: bool = False
    video_size_bytes: Optional[int] = None
    video_duration_seconds: Optional[float] = None


class JobStore:
    def __init__(self, data_dir: Path):
        self.data_dir = data_dir
        self.jobs_file = data_dir / "jobs.json"
        self._lock = threading.Lock()

    def _read(self) -> list[dict]:
        if not self.jobs_file.exists():
            return []
        with open(self.jobs_file) as f:
            return json.load(f)

    def _write(self, jobs: list[dict]) -> None:
        with open(self.jobs_file, "w") as f:
            json.dump(jobs, f, indent=2)

    def create_job(self, original_filename: str, config: JobConfig) -> Job:
        job = Job(
            id=uuid.uuid4().hex[:8],
            status="pending",
            created_at=datetime.now(timezone.utc).isoformat(),
            original_filename=original_filename,
            config=config,
        )
        with self._lock:
            jobs = self._read()
            jobs.append(job.model_dump())
            self._write(jobs)
        return job

    def get_job(self, job_id: str) -> Optional[Job]:
        with self._lock:
            jobs = self._read()
        for j in jobs:
            if j["id"] == job_id:
                return Job(**j)
        return None

    def list_jobs(self) -> list[Job]:
        with self._lock:
            jobs = self._read()
        return [Job(**j) for j in jobs]

    def update_job(self, job_id: str, **kwargs) -> Optional[Job]:
        with self._lock:
            jobs = self._read()
            for j in jobs:
                if j["id"] == job_id:
                    j.update(kwargs)
                    self._write(jobs)
                    return Job(**j)
        return None

    def delete_job(self, job_id: str) -> bool:
        with self._lock:
            jobs = self._read()
            original_len = len(jobs)
            jobs = [j for j in jobs if j["id"] != job_id]
            if len(jobs) < original_len:
                self._write(jobs)
                return True
        return False
